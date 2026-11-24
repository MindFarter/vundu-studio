"""Turns a project + output format into build steps, and runs them locally or over SSH."""
import glob
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile

from . import detect, icon as icongen, jobs, signing
from . import library as lib
from . import setup as tools

FORMATS = {"deb": "linux", "exe": "windows", "pkg": "macos", "pi": "linux"}
# "pi" = .deb for Raspberry Pi OS (Trixie). Node.js (pure JS, arch "all") and Electron (arm64) are built on
# this computer. Python and CMake must be built by the same kind of CPU, so they go to a Raspberry Pi over SSH.
LOCAL_PI = ("node", "electron")


def machine_for(p, fmt):
    """Which build-machine entry builds this format for this project."""
    return "pi" if fmt == "pi" and p["framework"] not in LOCAL_PI else FORMATS[fmt]
META = ".vundu"  # generated packaging files travel inside the workspace (also to remote machines)


def _q(s):
    return shlex.quote(str(s))


def _line(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def deb_version(v):
    v = re.sub(r"[^A-Za-z0-9.+~-]", ".", str(v or "0.0.1"))
    return v if re.match(r"\d", v) else "0." + v


def stage_workspace(p):
    ws = os.path.join(lib.WORK, p["id"])
    shutil.rmtree(ws, ignore_errors=True)
    src = p["source"]
    pats = detect.load_ignore(src)

    def ign(d, names):
        skip = set(shutil.ignore_patterns(*detect.SKIP, "*.pyc")(d, names))
        rel_dir = os.path.relpath(d, src)
        for n in names:
            if n not in skip and pats and detect.ignored(os.path.normpath(os.path.join(rel_dir, n)), pats):
                skip.add(n)
        return skip

    shutil.copytree(src, ws, ignore=ign, symlinks=True)  # links stay links: no loops, no huge copies
    meta = os.path.join(ws, META)
    os.makedirs(meta, exist_ok=True)
    safe = lib.slug(p["name"])
    icon = lib.icon_path(p)
    icon_ext = os.path.splitext(icon)[1].lower() if icon else ""
    if icon:
        shutil.copyfile(icon, os.path.join(meta, "icon" + icon_ext))
    if icon_ext not in (".png", ".svg"):  # Linux menus need PNG/SVG: generate a clean default
        with open(os.path.join(meta, "menu-icon.png"), "wb") as f:
            f.write(icongen.make_png(safe))
        menu_icon = "menu-icon.png"
    else:
        menu_icon = "icon" + icon_ext
    open(os.path.join(meta, "menu-icon.name"), "w").write(menu_icon)
    for lic in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):  # shipped in .deb files as /usr/share/doc/<pkg>/copyright
        if os.path.isfile(os.path.join(src, lic)):
            shutil.copyfile(os.path.join(src, lic), os.path.join(meta, "copyright"))
            break
    ms = signing.mac_options(p)
    if ms:
        with open(os.path.join(meta, "pycodesign.ini"), "w") as f:
            f.write(signing.mac_ini(ms, safe, p["version"]))
        with open(os.path.join(meta, "entitlements.plist"), "w") as f:
            f.write(signing.ENTITLEMENTS)
    desc = _line(p.get("description")) or _line(p["name"])
    maint = _line(p.get("publisher")) or "Unknown <unknown@example.com>"
    is_node = p["framework"] == "node"
    entry = p.get("entry") or "server.js"
    url = _line(p.get("launcher_url"))
    if url and not lib.URL_RE.fullmatch(url):
        raise ValueError(f"The web address {url!r} is not allowed. Use something like http://localhost:3000")
    depends = "Depends: nodejs\n" if is_node else ""
    with open(os.path.join(meta, "control"), "w") as f:
        f.write(f"Package: {safe}\nVersion: {deb_version(p['version'])}\nSection: utils\nPriority: optional\n"
                f"Architecture: @ARCH@\nMaintainer: {maint}\n{depends}Description: {desc}\n")
    with open(os.path.join(meta, "launcher"), "w") as f:
        f.write(f'#!/bin/sh\nexec /usr/bin/env node {_q(f"/opt/{safe}/{entry}")} "$@"\n')
    os.chmod(os.path.join(meta, "launcher"), 0o755)

    # --- app-menu entry
    name = _line(p["name"])
    if is_node and url:
        if p.get("service") and p.get("autostart"):
            exec_line, term = f"xdg-open {url}", "false"
        elif p.get("service"):
            exec_line = f"sh -c 'systemctl is-active --quiet {safe} || pkexec systemctl start {safe}; sleep 1; xdg-open {url}'"
            term = "false"
        else:
            exec_line = f"sh -c '({safe} >/dev/null 2>&1 &); sleep 2; xdg-open {url}'"
            term = "false"
    elif is_node:
        exec_line, term = safe, "true"
    else:
        exec_line, term = safe, "false"
    with open(os.path.join(meta, "app.desktop"), "w") as f:
        f.write(f"[Desktop Entry]\nVersion=1.0\nType=Application\nName={name}\nComment={desc}\n"
                f"Exec={exec_line}\nIcon={safe}\nTerminal={term}\nCategories=Utility;\nStartupNotify=true\n")
    user = _line(p.get("service_user"))
    with open(os.path.join(meta, "app.service"), "w") as f:
        f.write(f"[Unit]\nDescription={name}\nAfter=network.target\n\n[Service]\nType=simple\n"
                f"WorkingDirectory=/opt/{safe}\nExecStart=/usr/bin/{safe}\nRestart=on-failure\n"
                f"{'User=' + user if user else 'DynamicUser=yes'}\n\n[Install]\nWantedBy=multi-user.target\n")
    post = "#!/bin/sh\nset -e\n"
    if p.get("service"):
        post += "systemctl daemon-reload >/dev/null 2>&1 || true\n"
        if p.get("autostart"):
            post += f"systemctl enable --now {safe} >/dev/null 2>&1 || true\n"
    post += "command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true\n"
    post += "command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true\nexit 0\n"
    with open(os.path.join(meta, "postinst"), "w") as f:
        f.write(post)
    os.chmod(os.path.join(meta, "postinst"), 0o755)
    with open(os.path.join(meta, "prerm"), "w") as f:
        f.write(f"#!/bin/sh\nset -e\nif [ \"$1\" = remove ] || [ \"$1\" = purge ]; then\n"
                f"  systemctl stop {safe} >/dev/null 2>&1 || true\n  systemctl disable {safe} >/dev/null 2>&1 || true\nfi\nexit 0\n")
    os.chmod(os.path.join(meta, "prerm"), 0o755)
    return ws


def plan(p, fmt, py="python3", eb="npx electron-builder", pkgbin="npx --yes @yao-pkg/pkg", remote_os=None, mac_sign=None):
    """Shell commands (run inside the workspace) producing artifacts into ./vundu-out.
    remote_os ("windows"/"macos"/"linux") means an SSH machine: it has no private tools, so Python
    builds create a throw-away venv in the workspace and install the builder there."""
    name, ver = p["name"], p["version"]
    safe = lib.slug(name)
    out = "vundu-out"
    steps = [f"mkdir -p {out}"]
    fw = p["framework"]
    pi = fmt == "pi"
    if pi and fw not in LOCAL_PI:  # built natively on the Pi: same recipe as a normal .deb
        fmt = "deb"
    icon_ext = {"exe": ".ico", "pkg": ".icns"}.get(fmt)

    if fw == "electron":
        target = "--linux deb --arm64" if pi else {"deb": "--linux deb", "exe": "--win nsis", "pkg": "--mac pkg"}[fmt]
        steps += ["npm install",
                  f"{eb} {target} -c.productName={_q(name)} -c.extraMetadata.version={_q(ver)} "
                  f"-c.directories.output={out}"]
    elif fw in ("pyinstaller", "nuitka"):
        entry = p.get("entry") or "main.py"
        ico = f"$(ls {META}/icon{icon_ext} 2>/dev/null | sed 's/^/--icon=/')" if icon_ext else ""
        if remote_os:
            vpy = ".vundu-venv/Scripts/python.exe" if remote_os == "windows" else ".vundu-venv/bin/python"
            steps += [f"{_q(py)} -m venv .vundu-venv",
                      f"{vpy} -m pip install --upgrade {'nuitka' if p.get('engine') == 'nuitka' else 'pyinstaller'}"]
            py = vpy
        # a failing pip must fail the build; only a missing requirements.txt is skipped
        steps.append(f"if [ -f requirements.txt ]; then {_q(py)} -m pip install -r requirements.txt; fi")
        if p.get("engine") == "nuitka":
            steps.append(f"{_q(py)} -m nuitka --onefile --output-filename={_q(safe)} --output-dir=dist {_q(entry)}")
        else:
            steps.append(f"{_q(py)} -m PyInstaller --noconfirm --onefile --name {_q(safe)} {ico} {_q(entry)}")
        if fmt == "deb":
            steps += _deb_steps(p, safe, out, "python")
        elif fmt == "exe":
            steps.append(f"cp dist/{safe}.exe {out}/{_q(safe)}-{_q(ver)}.exe")
        else:
            steps += _mac_steps(p, safe, out, mac_sign)
    elif fw == "node":
        entry = p.get("entry") or "server.js"
        steps.append("npm install --omit=dev")
        if pi:  # compiled add-ons (.node files) are built for this PC's CPU and would not run on a Pi
            steps.append("if [ -n \"$(find node_modules -name '*.node' -print -quit)\" ]; then echo 'ERROR: this app "
                         "has compiled add-ons (.node files) that only work on this PC. Build it on a Raspberry Pi instead.'; "
                         "exit 1; fi")
            steps += _deb_steps(p, safe, out, "node", arch="all")
        elif fmt == "deb":
            steps += _deb_steps(p, safe, out, "node")
        elif fmt == "exe":
            steps.append(f"{pkgbin} {_q(entry)} --targets node20-win-x64 --output dist/{_q(safe)}.exe")
            steps.append(f"cp dist/{safe}.exe {out}/{_q(safe)}-{_q(ver)}.exe")
        else:
            steps.append(f"{pkgbin} {_q(entry)} --targets node20-macos-x64 --output dist/{_q(safe)}")
            steps += _mac_steps(p, safe, out, mac_sign)
    elif fw == "cmake":
        gen = {"deb": "DEB", "exe": "NSIS", "pkg": "productbuild"}[fmt]
        steps += ["cmake -S . -B build-cmake -DCMAKE_BUILD_TYPE=Release",
                  "cmake --build build-cmake --config Release",
                  f"cpack --config build-cmake/CPackConfig.cmake -G {gen} -B {out}"]
    else:
        raise ValueError(f"No build recipe for project type {p['kind']!r}/{fw!r}")
    return steps


def _mac_steps(p, safe, out, ms):
    if not ms:
        return [_mac_pkg(p, safe, out)]
    pkg = f"{out}/{_q(safe)}-{_q(p['version'])}.pkg"
    steps = [f"{_q(ms['tool'])} -s -p{' -n -t' if ms['notarize'] else ''} {META}/pycodesign.ini",  # txoof/codesign
             f"mv {_q(safe)}.pkg {pkg}",
             f"pkgutil --check-signature {pkg}"]  # fails if the package is not signed
    if ms["notarize"]:
        steps.append(f"xcrun stapler validate {pkg}")  # fails if Apple's notarisation ticket is not attached
    return steps


def _mac_pkg(p, safe, out):
    return (f"rm -rf pkgroot && mkdir -p pkgroot/Applications/{_q(p['name'])} && "
            f"cp dist/{_q(safe)} pkgroot/Applications/{_q(p['name'])}/ && "
            f"pkgbuild --root pkgroot --identifier com.vundu.{safe} --version {_q(p['version'])} "
            f"--install-location / {out}/{_q(safe)}-{_q(p['version'])}.pkg")


def _deb_steps(p, safe, out, kind, arch="$(dpkg --print-architecture)"):
    s = [f"rm -rf debroot && mkdir -p debroot/DEBIAN debroot/opt/{safe} debroot/usr/bin",
         f"cp {META}/control debroot/DEBIAN/control",
         f'sed -i "s/@ARCH@/{arch}/" debroot/DEBIAN/control']
    if kind == "python":
        s += [f"cp dist/{safe} debroot/opt/{safe}/ && ln -s /opt/{safe}/{safe} debroot/usr/bin/{safe}"]
    else:  # node: ship the app (with production node_modules) and a launcher
        s += [f"tar --exclude=./debroot --exclude=./{out} --exclude=./{META} --exclude=./.git --exclude=./.vunduignore -cf - . "
              f"| (cd debroot/opt/{safe} && tar -xf -)",
              f"install -m 755 {META}/launcher debroot/usr/bin/{safe}"]
    # app-menu entry + icon (so the app appears in the Activities / app grid with an icon)
    if p.get("launcher", True):
        s += [f"mkdir -p debroot/usr/share/applications && cp {META}/app.desktop debroot/usr/share/applications/{safe}.desktop",
              f"ICON=$(cat {META}/menu-icon.name); case \"$ICON\" in *.svg) D=scalable;; *) D=256x256;; esac; "
              f"mkdir -p debroot/usr/share/icons/hicolor/$D/apps && "
              f"cp {META}/$ICON debroot/usr/share/icons/hicolor/$D/apps/{safe}.${{ICON##*.}}"]
    s += [f"if [ -f {META}/copyright ]; then install -D -m 644 {META}/copyright debroot/usr/share/doc/{safe}/copyright; fi",
          f"install -m 755 {META}/postinst debroot/DEBIAN/postinst",
          f"install -m 755 {META}/prerm debroot/DEBIAN/prerm"]
    if p.get("service"):
        s.append(f"mkdir -p debroot/lib/systemd/system && cp {META}/app.service debroot/lib/systemd/system/{safe}.service")
    s.append(f"dpkg-deb --root-owner-group --build debroot {out}/{safe}_{deb_version(p['version'])}_{arch}.deb")
    return s


def collect(ws):
    files = []
    for f in glob.glob(os.path.join(ws, "vundu-out", "**", "*"), recursive=True):
        if os.path.isfile(f) and f.lower().endswith(lib.ARTIFACT_EXT):
            files.append(f)
    return sorted(set(files))


def _run_local(cmds, cwd, log):
    for c in cmds:
        log(f"$ {c}")
        rc = jobs.stream(["bash", "-lc", c], log, cwd=cwd)
        if rc != 0:
            raise RuntimeError(f"Step failed (exit {rc}): {c}")


def _ssh_base(t):
    b = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-p", str(t.get("port", 22))]
    if t.get("key"):
        b += ["-i", os.path.expanduser(t["key"])]
    return b + [f"{t['user']}@{t['host']}"]


def _run_ssh(cmds, ws, t, log):
    remote = t.get("workdir") or "vundu-build"
    base = _ssh_base(t)
    log(f"Uploading source to {t['host']}:{remote}")
    with tempfile.NamedTemporaryFile(suffix=".tgz") as tf:
        with tarfile.open(tf.name, "w:gz") as tar:
            tar.add(ws, arcname=".")
        with open(tf.name, "rb") as up:
            subprocess.run(base + [f"rm -rf {_q(remote)} && mkdir -p {_q(remote)} && tar -xz -C {_q(remote)}"],
                           stdin=up, check=True)
    for c in cmds:
        log(f"[remote] $ {c}")
        rc = jobs.stream(base + [f"cd {_q(remote)} && {c}"], log)
        if rc != 0:
            raise RuntimeError(f"Remote step failed (exit {rc}): {c}")
    log("Downloading artifacts")
    with tempfile.NamedTemporaryFile(suffix=".tgz") as tf:  # streamed to disk, never held in memory
        subprocess.run(base + [f"cd {_q(remote)} && tar -cz vundu-out"], stdout=tf, check=True)
        tf.flush()
        with tarfile.open(tf.name) as tar:
            tar.extractall(ws, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))


def build(p, fmt, log):
    """Build one format. Returns list of artifact paths."""
    osname = FORMATS[fmt]
    key = machine_for(p, fmt)
    t = lib.get_targets()[key]
    if t["mode"] == "unconfigured":
        what = "a Raspberry Pi (needed for Python and C/C++ projects)" if key == "pi" else osname
        raise RuntimeError(f"No build machine is set up for {what}. Open 'Machines' in the left menu and connect one.")
    ws = stage_workspace(p)
    py, eb, pkgbin = "python3", "npx electron-builder", "npx --yes @yao-pkg/pkg"
    if t["mode"] == "local":  # use the private tools installed by Setup
        py = tools.venv_python() or py
        eb = _q(tools.electron_builder_bin()) if tools.electron_builder_bin() else eb
        pkgbin = _q(tools.node_pkg_bin()) if tools.node_pkg_bin() else pkgbin
        host = lib.host_os()
        if host != osname:
            raise RuntimeError(f"This computer ({host}) cannot build {fmt} locally; connect a {osname} build machine.")
    if t["mode"] != "local":
        py = "python" if osname == "windows" else "python3"  # Windows Python has no python3 command
    ms = signing.mac_options(p) if fmt == "pkg" else None
    if fmt == "pkg" and not ms and signing.load()["pkg"]["enabled"]:
        log("NOTE: macOS signing covers Python and Node.js projects. This .pkg will NOT be signed.")
    cmds = plan(p, fmt, py, eb, pkgbin, remote_os=None if t["mode"] == "local" else osname, mac_sign=ms)
    if t["mode"] == "local":
        _run_local(cmds, ws, log)
    else:
        _run_ssh(cmds, ws, t, log)
    files = collect(ws)
    if not files:
        raise RuntimeError("The build finished but no .deb/.exe/.pkg was produced. Check the output above.")
    if fmt == "exe":
        signing.sign_exe(p, files, log)
    return files
