"""Automatic project recognition."""
import json
import os
import re

# Folders left out of both the change check and the package. dist/build/out are NOT here: they are
# often real source (compiled output) and are packaged, so edits there must count as changes.
# Use a .vunduignore file to leave them out.
SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache", "vundu-out", ".vundu"}
ICON_NAMES = ("icon", "logo", "app-icon", "appicon")
ICON_EXTS = (".png", ".ico", ".icns", ".svg")
ICON_DIRS = ("", "assets", "build", "resources", "static", "images", "img", "icons")


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _find_icon(root):
    for d in ICON_DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for fn in sorted(os.listdir(base)):
            stem, ext = os.path.splitext(fn.lower())
            if stem in ICON_NAMES and ext in ICON_EXTS:
                return os.path.join(base, fn)
    return None


def detect(root):
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        raise ValueError(f"Not a directory: {root}")
    res = {
        "kind": "unknown", "framework": None, "entry": None,
        "name": os.path.basename(root.rstrip("/")) or "app",
        "version": "0.0.1", "icon": _find_icon(root), "notes": [],
    }
    names = set(os.listdir(root))

    if "package.json" in names:
        try:
            pkg = json.loads(_read(os.path.join(root, "package.json")))
        except ValueError:
            pkg = {}
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        res["name"] = pkg.get("productName") or pkg.get("name") or res["name"]
        res["version"] = pkg.get("version", res["version"])
        res["entry"] = pkg.get("main")
        if not res["entry"]:
            m = re.search(r"node(?:mon)?\s+(?:--?\S+\s+)*([\w./-]+\.[cm]?js)", (pkg.get("scripts") or {}).get("start", ""))
            res["entry"] = m.group(1) if m else next(
                (e for e in ("server.js", "index.js", "app.js", "main.js", "src/index.js", "src/server.js")
                 if os.path.isfile(os.path.join(root, e))), None)
        if "electron" in deps:
            res.update(kind="node", framework="electron")
            res["notes"].append("Electron app -> electron-builder")
        else:
            res.update(kind="node", framework="node")
            res["port"] = guess_port(root, res["entry"])
            res["notes"].append("Node.js app/server -> .deb with launcher (optional background service)")
        return res

    if "CMakeLists.txt" in names:
        txt = _read(os.path.join(root, "CMakeLists.txt"))
        m = re.search(r"project\s*\(\s*([\w.\-]+)(?:[^)]*?VERSION\s+([\d.]+))?", txt, re.I)
        if m:
            res["name"] = m.group(1)
            if m.group(2):
                res["version"] = m.group(2)
        res.update(kind="cmake", framework="cmake")
        res["notes"].append("CMake project -> cmake + cpack (needs install() rules)")
        return res

    py_markers = {"pyproject.toml", "setup.py", "requirements.txt", "main.py", "app.py", "__main__.py"}
    if names & py_markers or any(n.endswith(".py") for n in names):
        entry = next((e for e in ("main.py", "app.py", "__main__.py") if e in names), None)
        if not entry:
            entry = next((n for n in sorted(names) if n.endswith(".py")), None)
        txt = _read(os.path.join(root, "pyproject.toml"))
        m = re.search(r'^name\s*=\s*"([^"]+)"', txt, re.M)
        if m:
            res["name"] = m.group(1)
        m = re.search(r'^version\s*=\s*"([^"]+)"', txt, re.M)
        if m:
            res["version"] = m.group(1)
        res.update(kind="python", framework="pyinstaller", entry=entry)
        res["notes"].append("Python app -> PyInstaller (or Nuitka)")
        return res

    res["notes"].append("Could not recognise project type")
    return res


def load_ignore(root):
    """Patterns from an optional .vunduignore file (one per line, # comments, * wildcards)."""
    pats = []
    try:
        with open(os.path.join(root, ".vunduignore"), encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip().rstrip("/")
                if line and not line.startswith("#"):
                    pats.append(line.lstrip("./"))
    except OSError:
        pass
    return pats


def ignored(rel, pats):
    import fnmatch
    base = os.path.basename(rel)
    return any(fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(base, p) or rel.startswith(p + "/") for p in pats)


MAX_FILES = 40000
MAX_SECONDS = 8


def scan(root):
    """One capped pass: change fingerprint, total size in bytes, and whether the scan was cut short.
    A cut-short scan has no fingerprint (None): where it stops varies, so its hash would be random."""
    import hashlib
    import time
    h, total, n, cut = hashlib.sha256(), 0, 0, False
    pats, t0 = load_ignore(root), time.time()
    for dp, dn, fn in os.walk(root):
        rel_dir = os.path.relpath(dp, root)
        dn[:] = sorted(d for d in dn if d not in SKIP and not ignored(os.path.normpath(os.path.join(rel_dir, d)), pats))
        for f in sorted(fn):
            rel = os.path.normpath(os.path.join(rel_dir, f))
            if ignored(rel, pats):
                continue
            try:
                st = os.stat(os.path.join(dp, f))
            except OSError:
                continue
            n += 1
            total += st.st_size
            h.update(f"{rel}:{st.st_size}:{int(st.st_mtime)}".encode())
        if n > MAX_FILES or time.time() - t0 > MAX_SECONDS:
            cut = True
            break
    return {"fingerprint": None if cut else h.hexdigest()[:16], "bytes": total, "files": n, "truncated": cut}


def guess_port(root, entry):
    """Look for the port a web server listens on, e.g. listen(3000) or PORT || 8080."""
    texts = []
    for rel in filter(None, [entry, "package.json", ".env", ".env.example", "config.json"]):
        texts.append(_read(os.path.join(root, rel))[:200000])
    blob = "\n".join(texts)
    for pat in (r"\.listen\(\s*(?:process\.env\.PORT\s*(?:\|\||\?\?)\s*)?(\d{2,5})",
                r"\bPORT\b\s*(?:\|\||\?\?|=|:)\s*[\"']?(\d{2,5})", r"\"port\"\s*:\s*(\d{2,5})",
                r"\bport\b\s*(?:=|:)\s*(\d{2,5})"):
        m = re.search(pat, blob, re.I)
        if m and 80 <= int(m.group(1)) <= 65535:
            return int(m.group(1))
    return None
