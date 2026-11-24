"""Projects + backup library. Every build is stored as its own release, never overwritten."""
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
        "id": pid, "name": det["name"], "version": det["version"], "publisher": "",
        "description": "", "source": source, "kind": det["kind"],
        "framework": det["framework"], "entry": det["entry"],
        "engine": None, "service": False, "service_user": "", "autostart": False,
        "port": det.get("port"),
        "launcher": det["framework"] in ("node", "pyinstaller", "nuitka"),
        "launcher_url": f"http://localhost:{det['port']}" if det.get("port") else "",
        "icon": None, "created": time.time(), "last_fingerprint": None,
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
    return len(os.listdir(d)) + 1 if os.path.isdir(d) else 1


def store_release(p, files, fingerprint, log_text, engine_note=""):
    """files: list of local paths. Returns release record."""
    build = next_build(p["id"], p["version"])
    rel_id = f"build-{build:03d}"
    rdir = os.path.join(project_lib(p["id"]), p["version"], rel_id)
    os.makedirs(rdir)
    stored = []
    for f in files:
        shutil.copyfile(f, os.path.join(rdir, os.path.basename(f)))
        stored.append({"name": os.path.basename(f), "size": os.path.getsize(f)})
    with open(os.path.join(rdir, "build.log"), "w") as lf:
        lf.write(log_text)
    rec = {"project": p["id"], "name": p["name"], "version": p["version"], "build": build,
           "release": rel_id, "time": time.time(), "files": stored,
           "source_fingerprint": fingerprint, "note": engine_note}
    _jsave(os.path.join(rdir, "release.json"), rec)
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
    # path-traversal safe
    base = os.path.realpath(os.path.join(LIBRARY, slug(pid), version, rel))
    p = os.path.realpath(os.path.join(base, name))
    if not p.startswith(base + os.sep) or not os.path.isfile(p):
        return None
    return p


# ---- build targets (where each OS is built)
def host_os():
    return "linux" if sys.platform.startswith("linux") else "macos" if sys.platform == "darwin" else "windows"


REMOTE_DEFAULT = {"mode": "unconfigured", "host": "", "user": "", "port": 22, "key": "", "workdir": "vundu-build"}


def get_targets():
    """The computer Vundu runs on builds its own OS automatically; other OSes need an SSH machine."""
    saved = _jload(TARGETS_FILE, {})
    out = {}
    for k in ("linux", "windows", "macos"):
        if k == host_os():
            out[k] = {"mode": "local", "host": "", "user": "", "port": 22, "key": "", "workdir": ""}
        else:
            out[k] = {**REMOTE_DEFAULT, **{f: v for f, v in saved.get(k, {}).items() if f in REMOTE_DEFAULT}}
    return out


def save_targets(t):
    saved = _jload(TARGETS_FILE, {})
    for k, v in t.items():
        if k in ("linux", "windows", "macos") and k != host_os():
            cur = {**REMOTE_DEFAULT, **saved.get(k, {})}
            cur.update({f: v[f] for f in REMOTE_DEFAULT if f in v})
            cur["mode"] = "ssh" if cur["host"] and cur["user"] else "unconfigured"
            saved[k] = cur
    _jsave(TARGETS_FILE, saved)
    return get_targets()
