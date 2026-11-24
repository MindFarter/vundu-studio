"""Vundu Studio - local web server (standard library only)."""
import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs

from . import builders, detect, jobs, library as lib, machines, setup as tools, vbox

VERSION = "0.0.4"
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PORT = 8765
_scan_cache = {}  # project id -> (time, scan result); avoids re-walking big folders on every refresh
_scan_lock = threading.Lock()


def project_scan(p, force=False):
    with _scan_lock:
        hit = _scan_cache.get(p["id"])
    if hit and not force and time.time() - hit[0] < 60:
        return hit[1]
    try:
        r = detect.scan(p["source"])
    except OSError:
        r = {"fingerprint": None, "bytes": 0, "files": 0, "truncated": False}
    with _scan_lock:
        _scan_cache[p["id"]] = (time.time(), r)
    return r


def public_project(p):
    sc = project_scan(p)
    q = dict(p)
    q["changed_since_release"] = bool(p.get("last_fingerprint")) is False or p.get("last_fingerprint") != sc["fingerprint"]
    q["size_mb"] = round(sc["bytes"] / 1e6, 1)
    q["size_truncated"] = sc["truncated"]
    return q


def run_build(job, p, formats):
    try:
        for fmt in formats:
            job.log(f"=== Building {fmt} for {p['name']} {p['version']} ===")
            try:
                files = builders.build(p, fmt, job.log)
                fp = project_scan(p, force=True)["fingerprint"]
                rec = lib.store_release(p, files, fp, job.full_log(), engine_note=fmt)
                job.results.append({"format": fmt, "ok": True, "release": rec["release"], "files": rec["files"]})
                job.log(f"Stored in library: {p['name']} / {p['version']} / {rec['release']}")
            except Exception as e:  # carry on with the other formats
                job.results.append({"format": fmt, "ok": False, "error": str(e)})
                job.log(f"ERROR: {e}")
        p["last_fingerprint"] = project_scan(p, force=True)["fingerprint"]
        lib.save_project(p)
    except Exception:
        job.log(traceback.format_exc())
    finally:
        shutil.rmtree(os.path.join(lib.WORK, p["id"]), ignore_errors=True)  # never leave build copies behind
        job.finish()


def run_setup(job, ids):
    try:
        res = tools.install(ids, job.log)
        job.results = [{"id": k, "status": v} for k, v in res.items()]
    except Exception:
        job.log(traceback.format_exc())
    job.finish()


def run_cmd(job, cmd, verify=None, label=""):
    """Run an administrator command (install / remove a .deb) with live output."""
    try:
        pre = tools._elevate_prefix(job.log)
        if pre is None:
            job.log("Administrator rights are needed. Run this in a terminal instead:")
            job.log("  sudo " + " ".join(cmd))
            job.results.append({"ok": False, "error": "needs administrator rights"})
        else:
            job.log("$ " + " ".join(pre + cmd))
            pr = subprocess.Popen(pre + cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in pr.stdout:
                job.log("  " + line.rstrip())
            rc = pr.wait()
            ok = rc == 0 and (verify() if verify else True)
            job.results.append({"ok": ok, "error": "" if ok else f"exit code {rc}"})
            job.log(f"== {label} {'finished' if ok else 'FAILED'}")
    except Exception:
        job.log(traceback.format_exc())
    job.finish()


def run_vbox_connect(job, name, user, os_target):
    try:
        port = vbox.ensure_forward(name, job.log)
        vbox.start(name, job.log)
        ready = vbox.wait_ssh("127.0.0.1", port, job.log)
        lib.save_targets({os_target: {"host": "127.0.0.1", "user": user, "port": port, "key": ""}})
        if ready:
            job.log("== The VM is saved as your build machine. Next: press Test connection on the Machines page.")
        else:
            job.log("== The VM is saved, but SSH is not answering yet. Windows needs OpenSSH switched on: "
                    "run the one-time setup line shown on the Machines page inside the VM.")
        job.results.append({"ok": True, "port": port, "ssh_ready": ready})
    except Exception as e:
        job.log(f"ERROR: {e}")
        job.results.append({"ok": False, "error": str(e)})
    job.finish()


def run_vbox_create(job, b):
    try:
        port = vbox.create_vm(b["name"], b["iso"], b.get("ostype", "Windows10_64"), int(b.get("memory", 6144)),
                              int(b.get("cpus", 4)), int(b.get("disk", 60)), job.log)
        lib.save_targets({"windows": {"host": "127.0.0.1", "user": b.get("user", ""), "port": port, "key": ""}})
        job.log("== Next: start the VM, install Windows from the ISO, then run the one-time setup line inside it.")
        job.results.append({"ok": True, "port": port})
    except Exception as e:
        job.log(f"ERROR: {e}")
        job.results.append({"ok": False, "error": str(e)})
    job.finish()


class H(BaseHTTPRequestHandler):
    server_version = "VunduStudio/" + VERSION

    def log_message(self, *a):
        pass

    # ---- helpers
    def _json(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _err(self, code, msg):
        self._json({"error": msg}, code)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20_000_000:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n) or b"{}")

    def _host_ok(self, path=""):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host in ("127.0.0.1", "localhost"):
            return True
        # A VirtualBox NAT guest reaches this server as 10.0.2.2. Only the one-time setup script is served there.
        return host == "10.0.2.2" and path == "/guest/windows.ps1"

    def _file(self, path, download_name=None):
        if not path or not os.path.isfile(path):
            return self._err(404, "not found")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(os.path.getsize(path)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def _text(self, text):
        b = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    # ---- GET
    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        if not self._host_ok(path):
            return self._err(403, "bad host")
        try:
            if path in ("/", "/index.html"):
                return self._file(os.path.join(WEB, "index.html"))
            if path == "/guest/windows.ps1":
                try:
                    machines.keygen()  # makes sure a key exists, then embeds its public half
                    return self._text(vbox.windows_guest_script(machines.public_key(), ""))
                except Exception as e:  # never hand PowerShell an error blob to execute
                    msg = str(e).replace("'", "")
                    return self._text(f"Write-Host 'Vundu Studio could not prepare the setup script: {msg}. "
                                      f"Open Setup in Vundu Studio and install OpenSSH client, then try again.' -ForegroundColor Red\n")
            if path == "/api/info":
                return self._json({"version": VERSION, "data_dir": lib.DATA, "host_os": lib.host_os()})
            if path == "/api/projects":
                return self._json([public_project(p) for p in lib.list_projects()])
            m = re.fullmatch(r"/api/projects/([\w-]+)/icon", path)
            if m:
                p = lib.get_project(m.group(1))
                return self._file(lib.icon_path(p) if p else None)
            m = re.fullmatch(r"/api/projects/([\w-]+)", path)
            if m:
                p = lib.get_project(m.group(1))
                return self._json(public_project(p)) if p else self._err(404, "no such project")
            if path == "/api/library":
                return self._json(lib.list_releases(q.get("project", [None])[0]))
            m = re.fullmatch(r"/api/library/([\w-]+)/([^/]+)/([\w-]+)/(.+)", path)
            if m:
                pid, ver, rel, name = (unquote(x) for x in m.groups())
                return self._file(lib.release_file(pid, ver, rel, name), download_name=os.path.basename(name))
            m = re.fullmatch(r"/api/jobs/([\w-]+)", path)
            if m:
                j = jobs.get(m.group(1))
                if not j:
                    return self._err(404, "no such job")
                return self._json(j.snapshot(int(q.get("since", ["0"])[0] or 0)))
            if path == "/api/targets":
                return self._json(lib.get_targets())
            if path == "/api/setup":
                return self._json(tools.status())
            if path == "/api/machines/local":
                return self._json(machines.local_info())
            if path == "/api/machines/pubkey":
                return self._json({"public": machines.public_key(q.get("key", [None])[0])})
            if path == "/api/vbox":
                d = vbox.info()
                d["guest_command"] = ("irm http://10.0.2.2:%d/guest/windows.ps1 | iex" % PORT)
                d["host_os"] = lib.host_os()
                return self._json(d)
            if path == "/api/browse":
                d = os.path.abspath(os.path.expanduser(q.get("path", ["~"])[0]))
                if not os.path.isdir(d):
                    return self._err(400, "not a directory")
                dirs = sorted(x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x)) and not x.startswith("."))
                return self._json({"path": d, "parent": os.path.dirname(d), "dirs": dirs})
            return self._err(404, "not found")
        except Exception as e:
            return self._err(500, str(e))

    def _post_like(self):
        if not self._host_ok():
            self._err(403, "bad host")
            return None
        # A custom header forces a CORS preflight for any other website, which we never answer.
        if self.headers.get("X-Vundu") != "1":
            self._err(403, "missing X-Vundu header")
            return None
        try:
            return self._body()
        except Exception as e:
            self._err(400, str(e))
            return None

    def _start(self, target, *args, label="", project=""):
        j = jobs.create(project, label)
        threading.Thread(target=target, args=(j,) + args, daemon=True).start()
        return self._json({"job": j.id}, 202)

    # ---- POST
    def do_POST(self):
        b = self._post_like()
        if b is None:
            return
        path = urlparse(self.path).path
        try:
            if path == "/api/projects":
                src = os.path.abspath(os.path.expanduser(b["source"]))
                det = detect.detect(src)
                p = lib.create_project(src, det)
                return self._json({"project": public_project(p), "detected": det}, 201)
            m = re.fullmatch(r"/api/projects/([\w-]+)/detect", path)
            if m:
                p = lib.get_project(m.group(1))
                project_scan(p, force=True)
                return self._json(detect.detect(p["source"]))
            m = re.fullmatch(r"/api/projects/([\w-]+)/icon", path)
            if m:
                p = lib.get_project(m.group(1))
                data = b["data_url"].split(",", 1)[1]
                ext = {"image/png": ".png", "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico",
                       "image/svg+xml": ".svg"}.get(re.match(r"data:([^;,]+)", b["data_url"]).group(1), ".png")
                dest = os.path.join(lib.PROJECTS, p["id"], "icon" + ext)
                with open(dest, "wb") as f:
                    f.write(base64.b64decode(data))
                p["icon"] = os.path.basename(dest)
                return self._json(lib.save_project(p))
            m = re.fullmatch(r"/api/projects/([\w-]+)/build", path)
            if m:
                p = lib.get_project(m.group(1))
                fmts = [f for f in b.get("formats", []) if f in builders.FORMATS]
                if not fmts:
                    return self._err(400, "choose at least one format: deb, exe, pkg")
                return self._start(run_build, p, fmts, project=p["id"])
            if path == "/api/library/save":
                src = lib.release_file(b["project"], b["version"], b["release"], b["file"])
                dest = os.path.abspath(os.path.expanduser(b["dest_dir"]))
                if not src or not os.path.isdir(dest):
                    return self._err(400, "bad source or destination")
                shutil.copyfile(src, os.path.join(dest, os.path.basename(src)))
                return self._json({"saved_to": os.path.join(dest, os.path.basename(src))})
            if path == "/api/library/install":
                src = lib.release_file(b["project"], b["version"], b["release"], b["file"])
                if not src or not src.endswith(".deb") or lib.host_os() != "linux":
                    return self._err(400, "only .deb files can be installed here, and only on Linux")
                name = lib.slug(b["project"])
                return self._start(run_cmd, ["apt-get", "install", "-y", src],
                                   lambda: subprocess.run(["dpkg", "-s", name], capture_output=True).returncode == 0,
                                   "Install", project=name)
            if path == "/api/library/uninstall":
                name = lib.slug(b["project"])
                if lib.host_os() != "linux":
                    return self._err(400, "only available on Linux")
                return self._start(run_cmd, ["apt-get", "remove", "-y", name],
                                   lambda: subprocess.run(["dpkg", "-s", name], capture_output=True).returncode != 0,
                                   "Remove", project=name)
            if path == "/api/machines/test":
                return self._json(machines.test(b.get("host", "").strip(), b.get("user", "").strip(),
                                                int(b.get("port") or 22), b.get("key", "")))
            if path == "/api/machines/keygen":
                return self._json(machines.keygen())
            if path == "/api/vbox/connect":
                return self._start(run_vbox_connect, b["name"], b.get("user", "").strip(),
                                   "macos" if b.get("os") == "macos" else "windows", project="vbox")
            if path == "/api/vbox/start":
                j = jobs.create("vbox")
                try:
                    vbox.start(b["name"], j.log)
                finally:
                    j.finish()
                return self._json({"ok": True})
            if path == "/api/vbox/stop":
                vbox.stop(b["name"])
                return self._json({"ok": True})
            if path == "/api/vbox/create":
                return self._start(run_vbox_create, b, project="vbox")
            if path == "/api/setup/install":
                known = {i["id"] for i in tools.status()["items"]}
                ids = [i for i in (b.get("ids") or []) if i in known]
                if not ids:
                    return self._err(400, "nothing to install")
                return self._start(run_setup, ids, project="setup")
            return self._err(404, "not found")
        except Exception as e:
            return self._err(400, str(e))

    def do_PUT(self):
        b = self._post_like()
        if b is None:
            return
        path = urlparse(self.path).path
        try:
            m = re.fullmatch(r"/api/projects/([\w-]+)", path)
            if m:
                p = lib.get_project(m.group(1))
                for k in ("name", "version", "publisher", "description", "entry", "engine", "framework", "service",
                          "service_user", "autostart", "launcher", "launcher_url"):
                    if k in b:
                        p[k] = (b[k] or None) if k in ("engine", "entry") else b[k]
                return self._json(public_project(lib.save_project(p)))
            if path == "/api/targets":
                return self._json(lib.save_targets(b))
            return self._err(404, "not found")
        except Exception as e:
            return self._err(400, str(e))


class Server(ThreadingHTTPServer):
    daemon_threads = True  # request threads never pile up or block shutdown
    block_on_close = False


def main():
    global PORT
    lib.init()
    PORT = int(os.environ.get("VUNDU_PORT", PORT))
    # leftovers from older sessions: build copies and job logs
    shutil.rmtree(lib.WORK, ignore_errors=True)
    os.makedirs(lib.WORK, exist_ok=True)
    shutil.rmtree(os.path.join(lib.DATA, "joblogs"), ignore_errors=True)
    srv = Server(("127.0.0.1", PORT), H)  # loopback only
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Vundu Studio {VERSION} running at {url}  (data: {lib.DATA})")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.6, lambda: __import__("webbrowser").open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
