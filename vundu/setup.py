"""First-run setup: detects and installs the tools Vundu Studio needs.

Python tools (PyInstaller, Nuitka) go into a private virtual environment and
node tools (electron-builder, pkg) into a private folder, both inside the Vundu
data dir, so nothing is installed system-wide except OS packages (apt / brew /
winget), which need administrator rights.
"""
import os
import shutil
import subprocess
import sys
import time

from . import jobs, library as lib

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
DRY = os.environ.get("VUNDU_DRY_RUN") == "1"

VENV = os.path.join(lib.DATA, "venv")
TOOLS = os.path.join(lib.DATA, "tools")
SETUP_FILE = os.path.join(lib.DATA, "setup.json")


def venv_python():
    p = os.path.join(VENV, "Scripts", "python.exe") if IS_WIN else os.path.join(VENV, "bin", "python")
    return p if os.path.isfile(p) else None


def _node_bin(name):
    p = os.path.join(TOOLS, "node_modules", ".bin", name + (".cmd" if IS_WIN else ""))
    return p if os.path.isfile(p) else None


def electron_builder_bin():
    return _node_bin("electron-builder")


def node_pkg_bin():
    return _node_bin("pkg")


def _venv_has(mod):
    # find_spec checks presence without importing (importing PyInstaller/Nuitka on every check is slow and heavy)
    py = venv_python()
    code = f"import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('{mod}') else 1)"
    return bool(py) and subprocess.run([py, "-c", code], capture_output=True).returncode == 0


def _venv_ok():
    py = venv_python()
    return bool(py) and subprocess.run([py, "-m", "pip", "--version"], capture_output=True).returncode == 0


def _can_venv():
    return subprocess.run([sys.executable, "-c", "import venv, ensurepip"], capture_output=True).returncode == 0


def _which(*names):
    return lambda: any(shutil.which(n) for n in names)


def _dpkg_healthy():
    try:
        r = subprocess.run(["dpkg", "--audit"], capture_output=True, text=True, timeout=20)
        return r.returncode == 0 and not r.stdout.strip()
    except Exception:
        return True


COMPONENTS = [
    dict(id="dpkg-repair", label="Package manager health", kind="system", linux_only=True, check=_dpkg_healthy,
         why="An earlier install was interrupted. Repairing it is safe and is needed before anything else can install."),
    dict(id="python-venv", label="Python venv module", why="Creates the private tools environment",
         kind="system", check=_can_venv, apt="python3-venv"),
    dict(id="compiler", label="C/C++ compiler and make", why="Nuitka and CMake projects", kind="system",
         check=lambda: bool(shutil.which("g++") and shutil.which("make")), apt="build-essential", linux_only=True),
    dict(id="cmake", label="CMake + CPack", why="Building CMake projects", kind="system",
         check=lambda: bool(shutil.which("cmake") and shutil.which("cpack")),
         apt="cmake", brew="cmake", win="Kitware.CMake"),
    dict(id="node", label="Node.js and npm", why="Node.js servers and Electron apps", kind="system",
         check=lambda: bool(shutil.which("node") and shutil.which("npm")),
         apt=["nodejs", "npm"], brew="node", win="OpenJS.NodeJS.LTS"),
    dict(id="dpkg", label="dpkg-deb", why="Creating .deb packages", kind="system", check=_which("dpkg-deb"),
         apt="dpkg-dev", linux_only=True),
    dict(id="fakeroot", label="fakeroot", why="Correct file ownership inside .deb files", kind="system",
         check=_which("fakeroot"), apt="fakeroot", linux_only=True),
    dict(id="patchelf", label="patchelf", why="Nuitka on Linux", kind="system", optional=True,
         check=_which("patchelf"), apt="patchelf", linux_only=True),
    dict(id="ssh", label="OpenSSH client", why="Building on Windows/macOS machines remotely", kind="system",
         check=_which("ssh"), apt="openssh-client"),
    dict(id="gnupg", label="GnuPG", why="Signing .deb and Raspberry Pi packages", kind="system", optional=True,
         check=_which("gpg"), apt="gnupg", brew="gnupg", win="GnuPG.GnuPG"),
    dict(id="osslsigncode", label="osslsigncode", why="Signing Windows .exe installers (works on Linux and macOS)",
         kind="system", optional=True, check=_which("osslsigncode"), apt="osslsigncode", brew="osslsigncode"),
    dict(id="nsis", label="NSIS", why="Windows .exe installers from CMake projects", kind="system", optional=True,
         check=_which("makensis"), apt="nsis", brew="makensis", win="NSIS.NSIS"),
    dict(id="venv", label="Private Python environment", why="Holds PyInstaller and Nuitka", kind="venv",
         check=_venv_ok),
    dict(id="pyinstaller", label="PyInstaller", why="Python apps to single executables", kind="pip",
         check=lambda: _venv_has("PyInstaller"), pip="pyinstaller"),
    dict(id="nuitka", label="Nuitka", why="Alternative Python compiler", kind="pip", optional=True,
         check=lambda: _venv_has("nuitka"), pip="nuitka"),
    dict(id="virtualbox", label="VirtualBox", kind="system", optional=True, linux_only=True,
         why="Run Windows build machines on this computer (Secure Boot may ask you to set a one-time password)",
         check=_which("VBoxManage"), apt="virtualbox"),
    dict(id="electron-builder", label="electron-builder", why="Electron apps to .deb/.exe/.pkg", kind="npm",
         check=lambda: bool(electron_builder_bin()), npm="electron-builder"),
    dict(id="node-pkg", label="pkg (Node.js to .exe/.pkg)", why="Standalone Windows/macOS programs from Node.js servers",
         kind="npm", optional=True, check=lambda: bool(node_pkg_bin()), npm="@yao-pkg/pkg"),
]


def _applies(c):
    return not (c.get("linux_only") and not IS_LINUX)


def _check(c):
    try:
        return bool(c["check"]())
    except Exception:
        return False


_cache = {"t": 0, "v": None}


def invalidate():
    _cache["t"] = 0


def status():
    if _cache["v"] is not None and time.time() - _cache["t"] < 10:
        return _cache["v"]
    v = _status()
    _cache.update(t=time.time(), v=v)
    return v


def _status():
    items = [{"id": c["id"], "label": c["label"], "why": c["why"], "kind": c["kind"],
              "optional": bool(c.get("optional")), "ok": _check(c)} for c in COMPONENTS if _applies(c)]
    done = lib._jload(SETUP_FILE, {}) or {}
    return {"items": items, "required_ok": all(i["ok"] for i in items if not i["optional"]),
            "missing": sum(1 for i in items if not i["ok"] and not i["optional"]),
            "completed_at": done.get("completed_at"), "platform": lib.host_os(), "dry_run": DRY}


def _run(cmd, log, shell=False, cwd=None):
    shown = cmd if isinstance(cmd, str) else " ".join(cmd)
    log(f"$ {shown}")
    if DRY:
        log("  (dry run - not executed)")
        return 0
    try:
        return jobs.stream(cmd, lambda line: log("  " + line), shell=shell, cwd=cwd)
    except OSError as e:
        log(f"  could not start: {e}")
        return 127


def _elevate_prefix(log):
    """Command prefix that gains admin rights, or None (the user is then shown the command)."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    if shutil.which("pkexec") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        log("A system password prompt will appear (once) to allow installing OS packages.")
        return ["pkexec"]
    if shutil.which("sudo") and subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0:
        return ["sudo", "-n"]
    return None


def _flat(v):
    return [v] if isinstance(v, str) else list(v or [])


def _apt_script(pkgs):
    """One script = one password prompt. Repairs dpkg, updates, installs; falls back to one-by-one
    so a single unavailable package can never block the others."""
    lines = ["export DEBIAN_FRONTEND=noninteractive",
             "echo '--- repairing interrupted package installs (if any)'",
             "dpkg --configure -a",
             "echo '--- updating package lists'",
             "apt-get update"]
    if pkgs:
        names = " ".join(pkgs)
        lines += [f"echo '--- installing: {names}'",
                  f"apt-get install -y {names} || {{ echo '--- retrying one by one'; "
                  f"for p in {names}; do apt-get install -y $p || echo \"COULD NOT INSTALL: $p\"; done; }}"]
    return "\n".join(lines)


def install(ids, log):
    """Install the selected components. Returns {id: 'ok'|'failed'|'manual'}."""
    todo = [c for c in COMPONENTS if c["id"] in ids and _applies(c)]
    manual = set()
    sysc = [c for c in todo if c["kind"] == "system"]

    # 1. OS packages, in a single administrator step
    if sysc:
        if IS_LINUX:
            pkgs = sorted({p for c in sysc for p in _flat(c.get("apt"))})
            script = _apt_script(pkgs)
            log("== Installing OS packages" + (": " + ", ".join(pkgs) if pkgs else " (repair only)"))
            pre = [] if DRY else _elevate_prefix(log)
            if pre is None:
                log("Administrator rights are needed and none are available from here.")
                log("Copy this into a terminal, then press Install again:")
                log("  sudo sh -c '" + script.replace("'", "'\"'\"'") + "'")
                manual |= {c["id"] for c in sysc}
            else:
                _run(pre + ["sh", "-c", script], log)
        elif IS_MAC:
            pk = sorted({p for c in sysc for p in _flat(c.get("brew"))})
            if shutil.which("brew") or DRY:
                log("== Installing with Homebrew: " + ", ".join(pk))
                if pk:
                    _run(["brew", "install"] + pk, log)
            else:
                log("Homebrew is not installed. Install it from https://brew.sh then press Install again.")
                manual |= {c["id"] for c in sysc}
        elif IS_WIN:
            if shutil.which("winget") or DRY:
                for c in sysc:
                    if c.get("win"):
                        log(f"== winget install {c['win']}")
                        _run(["winget", "install", "-e", "--id", c["win"], "--accept-package-agreements",
                              "--accept-source-agreements"], log)
                    else:
                        manual.add(c["id"])
            else:
                log("winget not found. Install 'App Installer' from the Microsoft Store, or install the tools manually.")
                manual |= {c["id"] for c in sysc}

    # 2. private virtual environment + pip tools
    if any(c["kind"] in ("venv", "pip") for c in todo):
        if not _venv_ok():
            log("== Creating private Python environment")
            if _run([sys.executable, "-m", "venv", VENV], log) != 0:
                log("Could not create the virtual environment (is python3-venv installed?).")
        pips = [c["pip"] for c in todo if c["kind"] == "pip"]
        py = venv_python() or os.path.join(VENV, "bin", "python")
        if pips and (venv_python() or DRY):
            log("== pip install " + " ".join(pips))
            _run([py, "-m", "pip", "install", "--upgrade", "pip"], log)
            _run([py, "-m", "pip", "install", "--upgrade"] + pips, log)

    # 3. node tools in a private folder
    npms = [c["npm"] for c in todo if c["kind"] == "npm"]
    if npms:
        if shutil.which("npm") or DRY:
            os.makedirs(TOOLS, exist_ok=True)
            log("== npm install " + " ".join(npms) + " (private folder)")
            _run(["npm", "install", "--prefix", TOOLS] + npms, log, shell=IS_WIN)
        else:
            log("npm is missing - install Node.js first, then press Install again.")

    # 4. verify by re-checking every selected component
    result = {}
    for c in todo:
        result[c["id"]] = "ok" if (DRY or _check(c)) else ("manual" if c["id"] in manual else "failed")
    invalidate()
    s = status()
    if s["required_ok"]:
        lib._jsave(SETUP_FILE, {"completed_at": time.time()})
        log("== Setup complete: all required tools are installed.")
    else:
        missing = [i["label"] for i in s["items"] if not i["ok"] and not i["optional"]]
        log("== Still missing: " + (", ".join(missing) or "nothing") + (" (dry run)" if DRY else ""))
    opt = [i["label"] for i in s["items"] if not i["ok"] and i["optional"]]
    if opt and not DRY:
        log("(Optional, not installed: " + ", ".join(opt) + ")")
    return result
