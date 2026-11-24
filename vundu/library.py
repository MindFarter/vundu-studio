"""Projects + backup library. Every build is stored as its own release, never overwritten."""
import hashlib
import json
import os
import re
import shutil
import sys
import time

DATA = os.environ.get("VUNDU_HOME") or os.path.expanduser("~/.vundu-studio")
PROJECTS = os.path.join(DATA, "projects")
LIBRARY = os.path.join(DATA, "library")
WORK = os.path.join(DATA, "work")
TARGETS_FILE = os.path.join(DATA, "targets.json")
ARTIFACT_EXT = (".deb", ".exe", ".pkg", ".msi", ".dmg", ".appimage", ".rpm")


def init():
    for d in (PROJECTS, LIBRARY, WORK):
        os.makedirs(d, exist_ok=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "project"


VERSION_RE = re.compile(r"[A-Za-z0-9][\w.+~-]{0,63}")
URL_RE = re.compile(r"https?://[\w.\-:/?#=+~@,]{1,200}")  # no quotes, spaces, ; & $ or % : it ends up in a shell line
USER_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")


def normalize_repo(v):
    """'https://github.com/owner/repo.git' or 'owner/repo' -> 'owner/repo'; '' stays ''."""
    v = re.sub(r"^https?://github\.com/|\.git$|/$", "", str(v or "").strip())
    if v and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", v):
        raise ValueError("The GitHub repository must look like owner/name (for example MindFarter/vundu-studio).")
    return v


def valid_version(v):
    return bool(VERSION_RE.fullmatch(str(v)))


def _jload(p, default=None):
    try:
        with open(p) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _jsave(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, p)


# ---- projects
def list_projects():
    out = []
    for pid in sorted(os.listdir(PROJECTS)):
        p = _jload(os.path.join(PROJECTS, pid, "project.json"))
        if p:
            out.append(p)
    return out


def get_project(pid):
    return _jload(os.path.join(PROJECTS, slug(pid), "project.json"))


def save_project(p):
    _jsave(os.path.join(PROJECTS, p["id"], "project.json"), p)
    return p


def create_project(source, det):
    base = slug(det["name"])
    pid, n = base, 2
    while os.path.exists(os.path.join(PROJECTS, pid)):
        pid, n = f"{base}-{n}", n + 1
    p = {
        "id": pid, "name": det["name"], "version": det["version"] if valid_version(det["version"]) else "0.0.1",
        "publisher": "",
        "description": "", "source": source, "kind": det["kind"],
        "framework": det["framework"], "entry": det["entry"],
        "engine": None, "service": False, "service_user": "", "autostart": False,
        "port": det.get("port"),
        "launcher": det["framework"] in ("node", "pyinstaller", "nuitka"),
        "launcher_url": f"http://localhost:{det['port']}" if det.get("port") else "",
        "icon": None, "created": time.time(), "last_fingerprint": None, "github": "",
    }
    if det.get("icon"):
        set_icon_file(p, det["icon"])
    return save_project(p)


def set_icon_file(p, src):
    ext = os.path.splitext(src)[1].lower() or ".png"
    dest = os.path.join(PROJECTS, p["id"], "icon" + ext)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(src, dest)
    p["icon"] = os.path.basename(dest)


def icon_path(p):
    return os.path.join(PROJECTS, p["id"], p["icon"]) if p.get("icon") else None


# ---- releases
def project_lib(pid):
    return os.path.join(LIBRARY, slug(pid))


def next_build(pid, version):
    d = os.path.join(project_lib(pid), version)
    nums = [int(m.group(1)) for n in (os.listdir(d) if os.path.isdir(d) else [])
            if (m := re.fullmatch(r"build-(\d+)", n))]
    return max(nums, default=0) + 1


def release_dir(rec):
    return os.path.join(project_lib(rec["project"]), rec["version"], rec["release"])


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def store_release(p, files, fingerprint, log_text, engine_note="", signed=(), after=None):
    """files: list of local paths. Returns release record. Every release gets a SHA256SUMS file so a
    download can be checked; after(rdir) may add more files (a signature) and returns their names."""
    if not valid_version(p["version"]):
        raise ValueError(f"Bad version {p['version']!r}: use letters, numbers and . + ~ - _ only.")
    build = next_build(p["id"], p["version"])
    rel_id = f"build-{build:03d}"
    rdir = os.path.join(project_lib(p["id"]), p["version"], rel_id)
    os.makedirs(rdir)
    try:
        stored = []
        for f in files:
            shutil.copyfile(f, os.path.join(rdir, os.path.basename(f)))
            stored.append({"name": os.path.basename(f), "size": os.path.getsize(f)})
        with open(os.path.join(rdir, "SHA256SUMS"), "w") as sf:  # same format as `sha256sum`, so `sha256sum -c` works
            sf.writelines(f"{_sha256(os.path.join(rdir, s['name']))}  {s['name']}\n" for s in sorted(stored, key=lambda s: s["name"]))
        extra = ["SHA256SUMS"] + (after(rdir) if after else [])
        stored += [{"name": n, "size": os.path.getsize(os.path.join(rdir, n))} for n in extra]
        with open(os.path.join(rdir, "build.log"), "w") as lf:
            lf.write(log_text)
        rec = {"project": p["id"], "name": p["name"], "version": p["version"], "build": build,
               "release": rel_id, "time": time.time(), "files": stored, "signed": list(signed),
               "source_fingerprint": fingerprint, "note": engine_note}
        _jsave(os.path.join(rdir, "release.json"), rec)
    except Exception:
        shutil.rmtree(rdir, ignore_errors=True)  # no half-made release
        raise
    return rec


def list_releases(pid=None):
    out = []
    if not os.path.isdir(LIBRARY):
        return out
    for proj in sorted(os.listdir(LIBRARY)):
        if pid and proj != pid:
            continue
        pd = os.path.join(LIBRARY, proj)
        for ver in os.listdir(pd):
            vd = os.path.join(pd, ver)
            if not os.path.isdir(vd):
                continue
            for rel in os.listdir(vd):
                r = _jload(os.path.join(vd, rel, "release.json"))
                if r:
                    out.append(r)
    out.sort(key=lambda r: r["time"], reverse=True)
    return out


def release_file(pid, version, rel, name):
    if not valid_version(version) or not re.fullmatch(r"[\w-]+", str(rel)):
        return None
    base = os.path.realpath(os.path.join(LIBRARY, slug(pid), version, rel))
    p = os.path.realpath(os.path.join(base, name))
    if not p.startswith(base + os.sep) or not os.path.isfile(p):
        return None
    return p


# ---- build targets (where each OS is built)
def host_os():
    return "linux" if sys.platform.startswith("linux") else "macos" if sys.platform == "darwin" else "windows"


TARGET_KEYS = ("linux", "windows", "macos", "pi")  # "pi" = a Raspberry Pi used to build Python/CMake projects
REMOTE_DEFAULT = {"mode": "unconfigured", "host": "", "user": "", "port": 22, "key": "", "workdir": "vundu-build"}


def get_targets():
    """The computer Vundu runs on builds its own OS automatically; other OSes need an SSH machine."""
    saved = _jload(TARGETS_FILE, {})
    out = {}
    for k in TARGET_KEYS:
        if k == host_os():
            out[k] = {"mode": "local", "host": "", "user": "", "port": 22, "key": "", "workdir": ""}
        else:
            out[k] = {**REMOTE_DEFAULT, **{f: v for f, v in saved.get(k, {}).items() if f in REMOTE_DEFAULT}}
    return out


def save_targets(t):
    saved = _jload(TARGETS_FILE, {})
    for k, v in t.items():
        if k in TARGET_KEYS and k != host_os():
            cur = {**REMOTE_DEFAULT, **saved.get(k, {})}
            cur.update({f: v[f] for f in REMOTE_DEFAULT if f in v})
            cur["mode"] = "ssh" if cur["host"] and cur["user"] else "unconfigured"
            saved[k] = cur
    _jsave(TARGETS_FILE, saved)
    return get_targets()
