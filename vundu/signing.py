"""Licensing and signing: who built this package, and has it been changed since?

- every release gets a SHA256SUMS file (written by library.store_release, no setup needed)
- .deb (Ubuntu / Debian) and Raspberry Pi OS .deb: GnuPG signs SHA256SUMS (SHA256SUMS.asc + PUBLIC-KEY.asc)
- Windows .exe / .msi: osslsigncode (Authenticode) signs the installer itself, on this computer
- macOS .pkg: txoof/codesign (pycodesign.py) signs, packages and notarises on the Mac build machine

Passwords are never written to disk or to the job log: they are kept in memory until the server stops.
If signing is switched on and fails, the build fails, so there is never a silently unsigned package.
"""
import os
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request

from . import library as lib

FILE = os.path.join(lib.DATA, "signing.json")
DEFAULTS = {
    "deb": {"enabled": False, "key": ""},
    "pi": {"enabled": False, "key": ""},
    "exe": {"enabled": False, "cert": "", "privkey": "", "timestamp": "http://timestamp.digicert.com"},
    "pkg": {"enabled": False, "app_id": "", "installer_id": "", "notary_profile": "", "notarize": False,
            "bundle_prefix": "com.vundu", "tool": "pycodesign.py"},
}
_ID = re.compile(r"[A-Za-z0-9._@:-]{3,64}")  # no spaces or quotes: these end up in a settings file and a command
CHECK = {
    "key": (re.compile(r"[0-9A-Fa-f]{8,64}"), "The GnuPG key must be its fingerprint (letters a-f and numbers)."),
    "timestamp": (re.compile(r"https?://[\w.\-:/]{1,200}"), "The timestamp address must look like http://timestamp.digicert.com"),
    "app_id": (_ID, "The Developer ID Application name must be one word: its hash or your Team ID."),
    "installer_id": (_ID, "The Developer ID Installer name must be one word: its hash or your Team ID."),
    "notary_profile": (_ID, "The notarisation profile must be one word (letters, numbers, - _ .)."),
    "bundle_prefix": (re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,60}"), "The bundle prefix must look like com.yourname"),
    "tool": (re.compile(r"[\w./-]{1,100}"), "The pycodesign path may only use letters, numbers and . / _ -"),
}
PATHS = ("cert", "privkey")
NEEDS = {"deb": ("key",), "pi": ("key",), "exe": ("cert",), "pkg": ("app_id", "installer_id")}
MAC_FRAMEWORKS = ("pyinstaller", "nuitka", "node")  # the .pkg we assemble ourselves; electron/cmake use their own tools

_pw = {}  # format -> password, memory only
GITHUB = "https://github.com"
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "verify.py")


class PasswordNeeded(RuntimeError):
    """The key or certificate is locked with a password the person has not typed yet."""

    def __init__(self, fmt, msg):
        super().__init__(msg)
        self.fmt = fmt


def _locked(fmt, stderr, pattern):
    """Raise PasswordNeeded / a wrong-password error when a signing tool failed because of the password."""
    if not re.search(pattern, stderr, re.I):
        return
    if fmt in _pw:
        _pw.pop(fmt)  # do not keep a wrong password
        raise RuntimeError("That password was not accepted. Check it and try again.")
    raise PasswordNeeded(fmt, "A password is needed to use your signing key or certificate.")


def load():
    saved = lib._jload(FILE, {}) or {}
    return {k: {f: saved.get(k, {}).get(f, v) for f, v in d.items()} for k, d in DEFAULTS.items()}


def save(new):
    cur = load()
    for fmt, d in DEFAULTS.items():
        for f, default in d.items():
            if f not in (new.get(fmt) or {}):
                continue
            v = new[fmt][f]
            if isinstance(default, bool):
                cur[fmt][f] = bool(v)
                continue
            v = str(v or "").strip()
            if v and f in CHECK and not CHECK[f][0].fullmatch(v):
                raise ValueError(CHECK[f][1])
            if v and f in PATHS and not os.path.isfile(os.path.expanduser(v)):
                raise ValueError(f"File not found: {v}")
            cur[fmt][f] = v
        if cur[fmt]["enabled"]:
            missing = [f for f in NEEDS[fmt] if not cur[fmt][f]]
            if fmt == "pkg" and cur[fmt]["notarize"] and not cur[fmt]["notary_profile"]:
                missing.append("notary_profile")
            if missing:
                raise ValueError(f"Fill in {', '.join(missing)} before switching signing on for {fmt}.")
    lib._jsave(FILE, cur)
    return cur


def unlock(fmt, password):
    if fmt not in ("deb", "pi", "exe"):
        raise ValueError("Nothing to unlock for that format.")
    if password:
        _pw[fmt] = password
    else:
        _pw.pop(fmt, None)


# ---- GnuPG
def _gpg(args, pw=None, timeout=120):
    cmd = ["gpg", "--batch", "--yes"] + (["--pinentry-mode", "loopback", "--passphrase-fd", "0"] if pw is not None else [])
    return subprocess.run(cmd + args, input=(pw + "\n") if pw is not None else "", capture_output=True, text=True,
                          timeout=timeout)


def list_keys():
    if not shutil.which("gpg"):
        return []
    keys, cur = [], None
    for line in _gpg(["--list-secret-keys", "--with-colons", "--fingerprint"]).stdout.splitlines():
        f = line.split(":")
        if f[0] == "sec":
            cur = {"fpr": "", "uid": ""}
            keys.append(cur)
        elif cur and f[0] == "fpr" and not cur["fpr"]:
            cur["fpr"] = f[9]
        elif cur and f[0] == "uid" and not cur["uid"]:
            cur["uid"] = f[9]
    return keys


def create_key(name, email, password):
    if not shutil.which("gpg"):
        raise RuntimeError("GnuPG is not installed. Install it from Setup.")
    if not re.fullmatch(r"[\w .'-]{1,60}", name or "") or not re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", email or ""):
        raise ValueError("Enter a name and a valid e-mail address.")
    uid = f"{name} <{email}>"
    r = _gpg(["--quick-generate-key", uid, "ed25519", "sign", "3y"], pw=password or "")
    if r.returncode:
        raise RuntimeError("GnuPG could not create the key: " + (r.stderr.strip().splitlines() or ["unknown error"])[-1])
    return next(k for k in reversed(list_keys()) if k["uid"] == uid)


def sign_release(p, fmt, rdir, log):
    """GnuPG-sign the release's SHA256SUMS. Returns the extra file names added to the release folder."""
    cfg = load().get(fmt) or {}
    if fmt not in ("deb", "pi") or not cfg.get("enabled"):
        return []
    if not shutil.which("gpg"):
        raise RuntimeError("Signing is on but GnuPG is not installed. Install it from Setup, or switch signing off.")
    sums = os.path.join(rdir, "SHA256SUMS")
    log(f"Signing SHA256SUMS with GnuPG key {cfg['key'][-16:]}")
    r = _gpg(["--armor", "--detach-sign", "-u", cfg["key"], "-o", sums + ".asc", sums], pw=_pw.get(fmt))
    if r.returncode:
        _locked(fmt, r.stderr, r"cancel|passphrase|pinentry|ioctl")
        raise RuntimeError("GnuPG could not sign. " + (r.stderr.strip().splitlines() or [""])[-1])
    pub = _gpg(["--armor", "--export", cfg["key"]])
    if pub.returncode or "BEGIN PGP PUBLIC KEY" not in pub.stdout:
        raise RuntimeError("GnuPG could not export the public key.")
    with open(os.path.join(rdir, "PUBLIC-KEY.asc"), "w") as f:
        f.write(pub.stdout)
    return ["SHA256SUMS.asc", "PUBLIC-KEY.asc"]


def finish_release(p, fmt, rdir, log):
    """Everything added to a release folder after SHA256SUMS: the GnuPG signature and, if the project has
    a GitHub repository, a verify.py for users. Returns the extra file names."""
    extra = sign_release(p, fmt, rdir, log)
    if p.get("github"):
        with open(TEMPLATE) as f:
            text = f.read()
        text = text.replace('REPO = "OWNER/REPO"', f'REPO = "{p["github"]}"').replace('TAG = "v0.0.0"', f'TAG = "v{p["version"]}"')
        with open(os.path.join(rdir, "verify.py"), "w") as f:
            f.write(text)
        os.chmod(os.path.join(rdir, "verify.py"), 0o755)
        extra.append("verify.py")
    return extra


def github_check(p, version, rdir):
    """Compare the files of a release with the SHA256SUMS published on the project's GitHub release."""
    repo = p.get("github")
    if not repo:
        raise ValueError("This project has no GitHub repository yet. Add it on the project's Overview page.")
    remote, tried = None, [f"v{version}", version]
    for tag in tried:
        url = f"{GITHUB}/{repo}/releases/download/{tag}/SHA256SUMS"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VunduStudio"})  # no personal details are sent
            with urllib.request.urlopen(req, timeout=20) as r:
                remote = r.read(1_000_000).decode("utf-8", "replace")
            break
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise RuntimeError(f"GitHub answered {e.code}. Try again later.")
        except OSError as e:
            raise RuntimeError(f"Could not reach GitHub: {e}")
    if remote is None:
        raise ValueError(f"GitHub has no release tagged {tried[0]} with a SHA256SUMS file in {repo}. "
                         f"Publish the release first and attach SHA256SUMS to it.")
    published = {}
    for line in remote.splitlines():
        m = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line.strip())
        if m:
            published[m.group(2)] = m.group(1).lower()
    files = []
    for line in open(os.path.join(rdir, "SHA256SUMS")).read().splitlines():
        name = line.split(None, 1)[1].lstrip("* ")
        mine = lib._sha256(os.path.join(rdir, name))  # hash the real file, not the list
        files.append({"name": name, "status": "missing" if name not in published else "ok" if published[name] == mine else "differs"})
    return {"repo": repo, "tag": tried[0], "files": files, "ok": bool(files) and all(f["status"] == "ok" for f in files)}


# ---- Windows (osslsigncode)
def sign_exe(p, files, log):
    """Authenticode-sign every .exe/.msi in place. No-op unless Windows signing is switched on."""
    cfg = load()["exe"]
    if not cfg["enabled"]:
        return
    exe = shutil.which("osslsigncode")
    if not exe:
        raise RuntimeError("Signing is on but osslsigncode is not installed. Install it from Setup, or switch signing off.")
    pwfile = None
    try:
        if _pw.get("exe"):
            fd, pwfile = tempfile.mkstemp()  # mode 0600; the password never appears in a command line or the log
            os.write(fd, _pw["exe"].encode())
            os.close(fd)
        for f in (x for x in files if x.lower().endswith((".exe", ".msi"))):
            cert = os.path.expanduser(cfg["cert"])
            cmd = [exe, "sign", "-h", "sha256", "-n", p["name"]]
            cmd += ["-certs", cert, "-key", os.path.expanduser(cfg["privkey"])] if cfg["privkey"] else ["-pkcs12", cert]
            if cfg["timestamp"]:
                cmd += ["-ts", cfg["timestamp"]]
            if pwfile:
                cmd += ["-readpass", pwfile]
            out = f + ".signed"
            log(f"Signing {os.path.basename(f)} with osslsigncode")
            r = subprocess.run(cmd + ["-in", f, "-out", out], capture_output=True, text=True, timeout=300)
            if r.returncode:
                if os.path.exists(out):
                    os.remove(out)
                err = r.stderr.strip() or r.stdout.strip() or "unknown error"
                _locked("exe", err, r"pass|decrypt|mac verify|private key|pkcs12")
                raise RuntimeError("osslsigncode could not sign. " + err.splitlines()[-1])
            os.replace(out, f)
    finally:
        if pwfile:
            os.remove(pwfile)


# ---- macOS (txoof/codesign, runs on the Mac)
def mac_options(p):
    cfg = load()["pkg"]
    return cfg if cfg["enabled"] and p["framework"] in MAC_FRAMEWORKS else None


ENTITLEMENTS = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>com.apple.security.cs.allow-jit</key><true/>
<key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
<key>com.apple.security.cs.disable-library-validation</key><true/>
</dict></plist>
"""  # PyInstaller and Node.js programs unpack and generate code at run time; the hardened runtime blocks that without these


def mac_ini(cfg, safe, version):
    return (f"[identification]\napplication_id = {cfg['app_id']}\ninstaller_id = {cfg['installer_id']}\n"
            f"keychain-profile = {cfg['notary_profile'] or 'none'}\n\n[package_details]\npackage_name = {safe}\n"
            f"bundle_id = {cfg['bundle_prefix']}.{safe}\nfile_list = dist/{safe}\n"
            f"installation_path = /Applications/{safe}\nentitlements = .vundu/entitlements.plist\nversion = {version}\n")


def applied(p, fmt):
    """What was done to a finished build, for the release record."""
    s = load()
    if fmt in ("deb", "pi") and s[fmt]["enabled"]:
        return ["gpg"]
    if fmt == "exe" and s["exe"]["enabled"]:
        return ["authenticode"]
    if fmt == "pkg" and mac_options(p):
        return ["macos"] + (["notarized"] if s["pkg"]["notarize"] else [])
    return []


def status():
    return {"settings": load(), "keys": list_keys(),
            "tools": {"gpg": bool(shutil.which("gpg")), "osslsigncode": bool(shutil.which("osslsigncode"))},
            "unlocked": {k: k in _pw for k in ("deb", "pi", "exe")}}
