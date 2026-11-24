"""VirtualBox integration (through the VBoxManage command line tool).

Lets Vundu Studio use a VirtualBox virtual machine as a build machine: list VMs,
start/stop them, create an SSH port-forward automatically (so host/port are filled
in for you), wait for SSH to come up, and create a new Windows VM from an ISO.

Note: Apple's licence only allows macOS in a VM on Apple hardware, so Vundu offers
VirtualBox for macOS builds only when it is running on a Mac.
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import time

FORWARD_RULE = "vundu-ssh"
FIRST_PORT = 2222


def exe():
    p = shutil.which("VBoxManage")
    if p:
        return p
    for c in (r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe", "/Applications/VirtualBox.app/Contents/MacOS/VBoxManage"):
        if os.path.isfile(c):
            return c
    return None


def _run(args, timeout=60):
    return subprocess.run([exe()] + args, capture_output=True, text=True, timeout=timeout)


def _showvminfo(name):
    r = _run(["showvminfo", name, "--machinereadable"], 30)
    info = {}
    for line in r.stdout.splitlines():
        k, _, v = line.partition("=")
        info[k.strip()] = v.strip().strip('"')
    return info


def info():
    if not exe():
        return {"installed": False, "version": "", "vms": []}
    ver = _run(["--version"], 15).stdout.strip()
    names = re.findall(r'^"(.+)" \{', _run(["list", "vms"], 30).stdout, re.M)
    running = set(re.findall(r'^"(.+)" \{', _run(["list", "runningvms"], 30).stdout, re.M))
    vms = []
    for n in names:
        i = _showvminfo(n)
        fwd = None
        for k, v in i.items():
            if k.startswith("Forwarding") and v.startswith(FORWARD_RULE + ","):
                parts = v.split(",")
                fwd = int(parts[3])
        vms.append({"name": n, "running": n in running, "ostype": i.get("ostype", ""),
                    "nic1": i.get("nic1", ""), "ssh_port": fwd,
                    "mac": "mac" in i.get("ostype", "").lower()})
    return {"installed": True, "version": ver, "vms": vms}


def _port_free(port):
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def ensure_forward(name, log):
    """Make host 127.0.0.1:<port> -> guest :22 on the VM's NAT adapter. Returns the port."""
    i = _showvminfo(name)
    running = i.get("VMState") == "running"
    for k, v in i.items():
        if k.startswith("Forwarding") and v.startswith(FORWARD_RULE + ","):
            port = int(v.split(",")[3])
            log(f"SSH port-forward already set: 127.0.0.1:{port} -> guest 22")
            return port
    if i.get("nic1") != "nat":
        raise RuntimeError("The VM's first network adapter is not NAT, so Vundu cannot forward a port automatically. "
                           "Set Adapter 1 to NAT in VirtualBox (Settings > Network), or enter the VM's address manually.")
    port = FIRST_PORT
    while not _port_free(port):
        port += 1
    rule = f"{FORWARD_RULE},tcp,127.0.0.1,{port},,22"
    log(f"Creating SSH port-forward 127.0.0.1:{port} -> guest 22")
    r = _run(["controlvm", name, "natpf1", rule] if running else ["modifyvm", name, "--natpf1", rule])
    if r.returncode != 0:
        raise RuntimeError("VBoxManage could not add the port-forward: " + (r.stderr or r.stdout).strip())
    return port


def start(name, log):
    if _showvminfo(name).get("VMState") == "running":
        log("VM is already running.")
        return
    log(f"Starting '{name}' in the background ...")
    r = _run(["startvm", name, "--type", "headless"], 120)
    if r.returncode != 0:
        raise RuntimeError("Could not start the VM: " + (r.stderr or r.stdout).strip())


def stop(name):
    r = _run(["controlvm", name, "acpipowerdown"])
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())


def wait_ssh(host, port, log, timeout=240):
    log(f"Waiting for SSH on {host}:{port} (a freshly started Windows can take a few minutes) ...")
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection((host, port), timeout=3) as s:
                s.settimeout(3)
                if s.recv(4).startswith(b"SSH"):
                    log("SSH is answering.")
                    return True
        except OSError:
            pass
        time.sleep(4)
    return False


def create_vm(name, iso, ostype, mem_mb, cpus, disk_gb, log):
    """Create + register a VM, attach the ISO, add an SSH port-forward. Returns the port."""
    if not os.path.isfile(os.path.expanduser(iso)):
        raise RuntimeError(f"ISO file not found: {iso}")
    if not re.fullmatch(r"[A-Za-z0-9 ._-]{1,60}", name):
        raise RuntimeError("Use letters, numbers, spaces, dots, dashes or underscores in the VM name.")
    if ostype not in ("Windows10_64", "Windows11_64"):
        raise RuntimeError("Unsupported OS type.")
    iso = os.path.abspath(os.path.expanduser(iso))
    port = FIRST_PORT
    while not _port_free(port):
        port += 1

    def vb(*args, t=300):
        log("$ VBoxManage " + " ".join(args))
        r = _run(list(args), t)
        for line in (r.stdout + r.stderr).splitlines():
            if line.strip():
                log("  " + line)
        if r.returncode != 0:
            raise RuntimeError(f"VBoxManage {args[0]} failed")

    vb("createvm", "--name", name, "--ostype", ostype, "--register")
    cfg = _showvminfo(name).get("CfgFile", "")
    folder = os.path.dirname(cfg) if cfg else os.path.expanduser("~/VirtualBox VMs/" + name)
    mod = ["modifyvm", name, "--memory", str(mem_mb), "--cpus", str(cpus), "--vram", "128",
           "--graphicscontroller", "vboxsvga", "--nic1", "nat", "--boot1", "dvd", "--boot2", "disk",
           "--natpf1", f"{FORWARD_RULE},tcp,127.0.0.1,{port},,22"]
    if ostype == "Windows11_64":  # Windows 11 needs UEFI + TPM 2.0 (VirtualBox 7+)
        mod += ["--firmware", "efi", "--tpm-type", "2.0"]
    vb(*mod)
    disk = os.path.join(folder, name + ".vdi")
    vb("createmedium", "disk", "--filename", disk, "--size", str(int(disk_gb) * 1024), "--format", "VDI")
    vb("storagectl", name, "--name", "SATA", "--add", "sata", "--controller", "IntelAhci")
    vb("storageattach", name, "--storagectl", "SATA", "--port", "0", "--device", "0", "--type", "hdd", "--medium", disk)
    vb("storageattach", name, "--storagectl", "SATA", "--port", "1", "--device", "0", "--type", "dvddrive", "--medium", iso)
    log(f"VM '{name}' created. SSH will be reachable at 127.0.0.1:{port} once Windows has OpenSSH enabled.")
    return port


def windows_guest_script(pubkey, host_url):
    """PowerShell to run once inside the Windows VM (as Administrator)."""
    key = pubkey.replace("'", "''")
    return f"""# Vundu Studio - one-time setup for this Windows build machine. Run in PowerShell as Administrator.
$ErrorActionPreference = 'Continue'
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
if (-not (Get-NetFirewallRule -Name 'sshd-vundu' -ErrorAction SilentlyContinue)) {{
  New-NetFirewallRule -Name 'sshd-vundu' -DisplayName 'OpenSSH (Vundu)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}}
winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
New-Item -Path 'HKLM:\\SOFTWARE\\OpenSSH' -Force | Out-Null
New-ItemProperty -Path 'HKLM:\\SOFTWARE\\OpenSSH' -Name DefaultShell -Value 'C:\\Program Files\\Git\\bin\\bash.exe' -PropertyType String -Force | Out-Null
$key = '{key}'
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole('Administrators')
if ($isAdmin) {{ $f = "$env:ProgramData\\ssh\\administrators_authorized_keys" }} else {{ New-Item -ItemType Directory -Force "$HOME\\.ssh" | Out-Null; $f = "$HOME\\.ssh\\authorized_keys" }}
if (-not (Test-Path $f) -or -not (Select-String -Path $f -SimpleMatch $key -Quiet)) {{ Add-Content -Path $f -Value $key }}
if ($isAdmin) {{ icacls $f /inheritance:r /grant 'Administrators:F' /grant 'SYSTEM:F' | Out-Null }}
Restart-Service sshd
Write-Host 'Done. Go back to Vundu Studio and press Test connection.' -ForegroundColor Green
"""
