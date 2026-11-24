"""Core checks. Run:  python3 tests/test_core.py   (plain asserts, no extra packages)"""
import os
import sys
import tempfile

os.environ["VUNDU_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import shutil  # noqa: E402
import subprocess  # noqa: E402

from vundu import builders, detect, jobs, library as lib, signing  # noqa: E402

lib.init()


def test_deb_version():
    assert builders.deb_version("1.0.0") == "1.0.0"
    assert builders.deb_version("v1 beta") == "0.v1.beta"


def test_version_and_url_validation():
    assert lib.valid_version("1.2.3-rc1") and not lib.valid_version("../x") and not lib.valid_version("")
    assert lib.URL_RE.fullmatch("http://localhost:3000/a?b=1")
    assert not lib.URL_RE.fullmatch("http://x';rm -rf ~;'") and not lib.URL_RE.fullmatch("javascript:alert(1)")


def test_release_file_cannot_escape():
    assert lib.release_file("p", "../../..", "build-001", "x") is None
    assert lib.release_file("p", "1.0.0", "..", "x") is None


def test_next_build_survives_a_deleted_build():
    d = os.path.join(lib.LIBRARY, "demo", "1.0.0")
    for n in ("build-001", "build-003"):
        os.makedirs(os.path.join(d, n))
    assert lib.next_build("demo", "1.0.0") == 4


def test_ignore_patterns():
    assert detect.ignored("music/a.mp3", ["music"]) and detect.ignored("x/y.log", ["*.log"])
    assert not detect.ignored("src/app.js", ["music", "*.log"])


def test_guess_port():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "server.js"), "w").write("app.listen(process.env.PORT || 8080)")
    assert detect.guess_port(d, "server.js") == 8080


def test_scan_cut_short_has_no_fingerprint():
    d = tempfile.mkdtemp()
    open(os.path.join(d, "a.txt"), "w").write("x")
    assert detect.scan(d)["fingerprint"]
    old, detect.MAX_FILES = detect.MAX_FILES, 0
    try:
        assert detect.scan(d)["fingerprint"] is None
    finally:
        detect.MAX_FILES = old


def test_job_snapshot_drops_old_lines():
    j = jobs.Job("t")
    for i in range(jobs.MAX_LINES + 5):
        j.log(str(i))
    s = j.snapshot(0)
    assert s["dropped"] == 5 and s["lines"][0] == "5" and s["next"] == jobs.MAX_LINES + 5
    j.finish()


def test_stream_shows_a_waiting_question():
    out = []
    rc = jobs.stream(["python3", "-c", "import sys,time;sys.stdout.write('Ok to proceed? (y) ');sys.stdout.flush();time.sleep(2.2)"],
                     out.append)
    assert rc == 0 and any("WAITING FOR YOU" in x and "Ok to proceed" in x for x in out)


def _py(**kw):
    return {"name": "Demo", "version": "1.0.0", "framework": "pyinstaller", "kind": "python", "entry": "main.py", **kw}


def test_python_plan_does_not_hide_pip_failure():
    steps = builders.plan(_py(), "deb")
    pip = next(s for s in steps if "requirements.txt" in s)
    assert "|| true" not in pip and pip.startswith("if [ -f requirements.txt ]")


def test_remote_python_plan_installs_pyinstaller_in_a_venv():
    steps = builders.plan(_py(), "exe", "python", remote_os="windows")
    assert steps[1] == "python -m venv .vundu-venv"
    assert ".vundu-venv/Scripts/python.exe -m pip install --upgrade pyinstaller" in steps[2]
    assert any(".vundu-venv/Scripts/python.exe -m PyInstaller" in s for s in steps)


def _node():
    return {"name": "Demo", "version": "1.0.0", "framework": "node", "kind": "node", "entry": "server.js"}


def test_pi_node_is_arch_all_and_refuses_compiled_addons():
    steps = builders.plan(_node(), "pi")
    assert any('s/@ARCH@/all/' in s for s in steps)
    assert steps[-1].endswith("_all.deb")
    assert any("find node_modules -name '*.node'" in s for s in steps)


def test_pi_electron_is_arm64_and_python_goes_to_a_pi():
    el = builders.plan({**_node(), "framework": "electron"}, "pi")
    assert "--linux deb --arm64" in el[-1]
    assert builders.machine_for(_py(), "pi") == "pi" and builders.machine_for(_node(), "pi") == "linux"
    assert "pi" in lib.get_targets() and lib.get_targets()["pi"]["mode"] == "unconfigured"


def test_every_release_gets_a_sha256sums_file():
    f = os.path.join(tempfile.mkdtemp(), "app_1.0.0_all.deb")
    open(f, "wb").write(b"hello")
    rec = lib.store_release({"id": "sums", "name": "Sums", "version": "1.0.0"}, [f], None, "log")
    line = open(os.path.join(lib.release_dir(rec), "SHA256SUMS")).read()
    assert line == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824  app_1.0.0_all.deb\n"
    assert any(x["name"] == "SHA256SUMS" for x in rec["files"]) and rec["signed"] == []


def test_signing_settings_are_validated():
    for bad in ({"deb": {"key": "not a key!"}}, {"exe": {"timestamp": "ftp://x"}}, {"pkg": {"app_id": "a b"}},
                {"exe": {"cert": "/no/such/file.pfx"}}, {"deb": {"enabled": True}}, {"pkg": {"enabled": True, "app_id": "ABCDE12345"}}):
        try:
            signing.save(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")
    assert signing.load()["deb"]["enabled"] is False


def test_macos_signed_pkg_steps():
    cfg = {**signing.DEFAULTS["pkg"], "enabled": True, "app_id": "ABCDE12345", "installer_id": "FGHIJ67890", "notarize": True}
    steps = builders._mac_steps(_py(), "demo", "vundu-out", cfg)
    assert steps[0] == "pycodesign.py -s -p -n -t .vundu/pycodesign.ini"
    assert any(x.startswith("pkgutil --check-signature") for x in steps) and any("stapler validate" in x for x in steps)
    assert builders._mac_steps(_py(), "demo", "vundu-out", None)[0].startswith("rm -rf pkgroot")
    ini = signing.mac_ini(cfg, "demo", "1.0.0")
    assert "application_id = ABCDE12345" in ini and "file_list = dist/demo" in ini


def test_deb_ships_the_project_licence():
    assert any("usr/share/doc/demo/copyright" in x for x in builders.plan(_py(), "deb"))


def test_windows_signing_without_the_tool_fails_loudly():
    real, signing.shutil.which = signing.shutil.which, lambda n: None
    try:
        s = signing.load()
        s["exe"]["enabled"] = True
        signing.lib._jsave(signing.FILE, s)
        try:
            signing.sign_exe({"name": "x"}, ["a.exe"], print)
        except RuntimeError as e:
            assert "osslsigncode is not installed" in str(e)
        else:
            raise AssertionError("signed without a tool")
    finally:
        signing.shutil.which = real
        signing.lib._jsave(signing.FILE, signing.load() | {"exe": signing.DEFAULTS["exe"]})


def test_gnupg_signature_round_trip():
    if not shutil.which("gpg"):
        return
    os.environ["GNUPGHOME"] = home = tempfile.mkdtemp()
    os.chmod(home, 0o700)
    key = signing.create_key("Test Dev", "t@example.com", "pw1")
    s = signing.load()
    s["deb"].update(enabled=True, key=key["fpr"])
    signing.lib._jsave(signing.FILE, s)
    rdir = tempfile.mkdtemp()
    open(os.path.join(rdir, "SHA256SUMS"), "w").write("abc  file\n")
    try:
        signing.sign_release({}, "deb", rdir, print)  # no password unlocked: must ask for it, not hang
        raise AssertionError("signed a protected key without its password")
    except signing.PasswordNeeded as e:
        assert e.fmt == "deb"
    signing.unlock("deb", "wrong")
    try:
        signing.sign_release({}, "deb", rdir, print)
        raise AssertionError("accepted a wrong password")
    except RuntimeError as e:
        assert not isinstance(e, signing.PasswordNeeded) and "not accepted" in str(e)
    assert "deb" not in signing._pw  # a wrong password is forgotten
    signing.unlock("deb", "pw1")
    assert signing.sign_release({}, "deb", rdir, print) == ["SHA256SUMS.asc", "PUBLIC-KEY.asc"]
    assert subprocess.run(["gpg", "--verify", os.path.join(rdir, "SHA256SUMS.asc"), os.path.join(rdir, "SHA256SUMS")],
                          capture_output=True).returncode == 0
    signing.unlock("deb", "")
    signing.lib._jsave(signing.FILE, signing.load() | {"deb": signing.DEFAULTS["deb"]})


def _fake_github(body):
    """A tiny local web server standing in for github.com. Serves `body` as .../SHA256SUMS, 404 otherwise."""
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            ok = body is not None and self.path.endswith("/SHA256SUMS") and "/v1.0.0/" in self.path
            self.send_response(200 if ok else 404)
            self.end_headers()
            self.wfile.write(body.encode() if ok else b"")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def _release_dir(content=b"hello"):
    f = os.path.join(tempfile.mkdtemp(), "app_1.0.0_all.deb")
    open(f, "wb").write(content)
    rec = lib.store_release({"id": "ghchk", "name": "Gh", "version": "1.0.0"}, [f], None, "log")
    return lib.release_dir(rec)


def test_normalize_repo():
    assert lib.normalize_repo("https://github.com/MindFarter/vundu-studio.git") == "MindFarter/vundu-studio"
    assert lib.normalize_repo("MindFarter/vundu-studio/") == "MindFarter/vundu-studio" and lib.normalize_repo("") == ""
    for bad in ("nonsense", "a/b/c", "x y/z", "https://evil.com/a/b"):
        try:
            lib.normalize_repo(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def test_github_check_and_verify_script():
    rdir = _release_dir()
    good = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824  app_1.0.0_all.deb\n"
    p = {"github": "me/app"}
    real = signing.GITHUB
    try:
        srv, signing.GITHUB = _fake_github(good)
        r = signing.github_check(p, "1.0.0", rdir)
        assert r["ok"] and r["files"] == [{"name": "app_1.0.0_all.deb", "status": "ok"}]
        # the generated verify.py, pointed at the fake server, passes and then fails when the file is changed
        text = signing.finish_release({**p, "version": "1.0.0"}, "deb", rdir, print)
        assert text == ["verify.py"]
        src = open(os.path.join(rdir, "verify.py")).read().replace("https://github.com", signing.GITHUB)
        assert 'REPO = "me/app"' in src and 'TAG = "v1.0.0"' in src
        script = os.path.join(rdir, "verify_local.py")
        open(script, "w").write(src)
        assert subprocess.run([sys.executable, script], capture_output=True).returncode == 0
        open(os.path.join(rdir, "app_1.0.0_all.deb"), "wb").write(b"tampered")
        assert subprocess.run([sys.executable, script], capture_output=True).returncode == 1
        assert signing.github_check(p, "1.0.0", rdir)["files"][0]["status"] == "differs"
        srv.shutdown()
        srv, signing.GITHUB = _fake_github("")  # release exists but does not list the file
        assert signing.github_check(p, "1.0.0", rdir)["files"][0]["status"] == "missing"
        srv.shutdown()
        srv, signing.GITHUB = _fake_github(None)  # no such release
        try:
            signing.github_check(p, "1.0.0", rdir)
            raise AssertionError("passed without a release")
        except ValueError as e:
            assert "no release tagged v1.0.0" in str(e)
        srv.shutdown()
    finally:
        signing.GITHUB = real
    try:
        signing.github_check({}, "1.0.0", rdir)
    except ValueError as e:
        assert "no GitHub repository" in str(e)


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            n += 1
    print(f"{n} tests passed")
