"""Build-machine discovery: describe this computer, find SSH hosts/keys, test and create keys."""
import getpass
import os
import platform
import socket
import subprocess

from . import library as lib

SSH_DIR = os.path.expanduser("~/.ssh")
VUNDU_KEY = os.path.join(SSH_DIR, "id_ed25519_vundu")


def _distro():
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return platform.platform()


def _ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def _ssh_port():
    port = 22
    try:
        with open("/etc/ssh/sshd_config") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2 and parts[0].lower() == "port" and parts[1].isdigit():
                    port = int(parts[1])
                    break
    except OSError:
        pass
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.4).close()
        return port, True
    except OSError:
        return port, False


def ssh_config_hosts():
    hosts, cur = [], None
    try:
        with open(os.path.join(SSH_DIR, "config")) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                k, _, v = line.partition(" ")
                k, v = k.lower(), v.strip()
                if k == "host":
                    cur = None
                    if "*" not in v and "?" not in v and v:
                        cur = {"alias": v.split()[0], "host": v.split()[0], "user": "", "port": 22, "key": ""}
                        hosts.append(cur)
                elif cur is not None:
                    if k == "hostname":
                        cur["host"] = v
                    elif k == "user":
                        cur["user"] = v
                    elif k == "port" and v.isdigit():
                        cur["port"] = int(v)
                    elif k == "identityfile":
                        cur["key"] = v
    except OSError:
        pass
    return hosts


def keys():
    out = []
    try:
        for fn in sorted(os.listdir(SSH_DIR)):
            if fn.startswith("id_") and not fn.endswith(".pub") and os.path.isfile(os.path.join(SSH_DIR, fn)):
                out.append(os.path.join(SSH_DIR, fn))
    except OSError:
        pass
    return out


def local_info():
    port, running = _ssh_port()
    return {
        "os": lib.host_os(),
        "system": _distro(), "arch": platform.machine(), "user": getpass.getuser(),
        "hostname": socket.gethostname(), "ip": _ip(), "ssh_port": port, "ssh_running": running,
        "keys": keys(), "ssh_hosts": ssh_config_hosts(), "vundu_key": VUNDU_KEY,
        "vundu_key_exists": os.path.isfile(VUNDU_KEY),
    }


def public_key(path=None):
    path = (path or VUNDU_KEY) + ".pub"
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def keygen():
    os.makedirs(SSH_DIR, mode=0o700, exist_ok=True)
    if not os.path.isfile(VUNDU_KEY):
        r = subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "vundu-studio", "-f", VUNDU_KEY],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("ssh-keygen failed: " + (r.stderr or r.stdout).strip())
    return {"key": VUNDU_KEY, "public": public_key()}


def test(host, user, port=22, key=""):
    """Try a key-based SSH login. Returns {ok, message, hint}."""
    if not host or not user:
        return {"ok": False, "message": "Enter a host and a user first.", "hint": ""}
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new",
           "-p", str(port)]
    if key:
        cmd += ["-i", os.path.expanduser(key)]
    cmd += [f"{user}@{host}", "echo vundu-ok"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return {"ok": False, "message": "The ssh program is not installed.", "hint": "Open Setup and install 'OpenSSH client'."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "The machine did not answer in time.",
                "hint": "Check the address, that the machine is switched on, and that port " + str(port) + " is open."}
    err = (r.stderr or "").strip()
    if r.returncode == 0 and "vundu-ok" in r.stdout:
        return {"ok": True, "message": "Connected. This machine is ready to build.", "hint": ""}
    low = err.lower()
    if "permission denied" in low:
        hint = ("The machine is reachable, but it does not know your key yet. Copy your public key "
                "(button below) into the machine's authorized_keys file, then test again.")
    elif "refused" in low:
        hint = "Nothing is listening on that port. Make sure the SSH server (OpenSSH) is installed and running."
    elif "could not resolve" in low or "name or service" in low:
        hint = "That host name was not found. Check the spelling or use the machine's IP address."
    elif "no route" in low or "unreachable" in low or "timed out" in low:
        hint = "The machine could not be reached. Check the address and that you are on the same network or VPN."
    elif "host key" in low:
        hint = "The machine's identity changed. If you trust it, remove its old line from ~/.ssh/known_hosts."
    else:
        hint = ""
    return {"ok": False, "message": err.splitlines()[-1] if err else "Connection failed.", "hint": hint}
