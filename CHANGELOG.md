# Changelog

All notable changes to Vundu Studio are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project uses [Semantic Versioning](https://semver.org/).

## [0.0.4] - 2026-11-20

### Added
- **VirtualBox support**: list VMs, start/stop them, automatic SSH port-forward, wait-for-SSH,
  and one click to save a VM as the Windows build machine. Create a new Windows 10/11 VM from an
  ISO. A one-line, copy-ready PowerShell setup (OpenSSH, Git, Node.js, Python, your key) for the
  guest. VirtualBox is an optional Setup component. macOS in VirtualBox is only offered on Apple hardware.
- **App-menu entry with an icon** for installed Python and Node.js packages, so they appear in the
  application menu. Servers open their web address (port detected from the code). A clean default icon
  is generated when none is supplied.
- **Install / remove** links for every `.deb` in the library, with live output, plus a plain
  "where did it go?" explanation on the Releases tab.
- **Start automatically** option for the background service (enabled right after install); the service
  is stopped and disabled on removal.
- `.vunduignore` to keep large data out of packages, a size warning for big project folders,
  and project size on the Overview tab.

### Fixed
- **Memory growth**: job output is now bounded (last 4,000 lines in memory, full log on disk), browsers
  fetch only new lines, the console keeps at most 3,000 lines, overlapping polls are prevented and polling
  stops if the server is gone, finished jobs are pruned, build copies are deleted after every build,
  remote artifacts are streamed to disk, request threads are daemon threads.
- Repeated heavy checks: setup status is cached, tool presence is checked without importing
  PyInstaller/Nuitka, folder scans are capped and cached.
- A `.deb` installed from the library previously had no menu entry or icon.
- Detected web port was not saved with the project.

### Changed
- Build copies and job logs from earlier sessions are cleaned at start-up.

## [0.0.3] - 2026-11-20

### Added
- **Dark and light themes** with a toggle (remembers your choice; follows the system on first run).
- **Developer-tool interface**: side menu (Projects, Library, Machines, Setup), editor-style
  tabs per project (Overview, Build, Releases), an Output console panel for build and setup
  logs, and a status bar. Plain-language help text and a 4-step welcome guide for beginners.
- **Node.js server packaging**: plain Node.js projects (for example a music server) now build
  a `.deb` with a launcher command, production-only `npm` dependencies and an optional
  systemd service (with optional run-as user). `.exe`/`.pkg` via `@yao-pkg/pkg`.
- **Automatic build machines**: this computer's system, user, host name, address and SSH port
  are detected; the host OS builds locally with no configuration. Remote machine forms are
  pre-filled (user, port 22, `~/.ssh/config` hosts, detected keys).
- **Test connection** with plain-English diagnosis, and **Create a key for me** (ed25519) with
  copy-ready authorisation instructions.
- Setup components for package-manager health, and optional `pkg`.

### Fixed
- Setup failing with `dpkg was interrupted`: Setup now runs `dpkg --configure -a` first.
- One unavailable package could block all the others: installs now fall back to one by one.
- Several password prompts: all OS packages are now installed in a single administrator step.
- Setup now verifies each tool afterwards instead of assuming success.
- Plain Node.js projects had no build recipe ("No build recipe for project type node").
- `.deb` files are now created with `--root-owner-group` so files are owned by root.
- Version numbers are sanitised to be valid Debian versions; the architecture is detected
  (`amd64`, `arm64`, ...) instead of being fixed.
- Projects with their own `build/` or `dist/` folders (for example a web front end served by
  a Node.js server) are no longer stripped from the build copy.
- Generated packaging files no longer break on quotes in the description or publisher.

### Changed
- patchelf is now optional (only Nuitka needs it).
- The "Build machines" page replaces manual host/user/port entry for the local machine.

## [0.0.2] - 2026-11-20

### Added
- One-off **First-time setup**: a banner and a **Setup** tab detect missing tools
  and install them with one click, with a live log.
- Private tool environments: PyInstaller and Nuitka in a dedicated Python virtual
  environment, electron-builder in a private npm folder, so system Python is untouched.
- OS package installation through `apt` (Ubuntu), Homebrew (macOS) and `winget`
  (Windows), using `pkexec` or `sudo`, or showing the exact command when
  administrator rights are unavailable.
- `python3 vundu_studio.py` entry point and `run.sh` launcher.
- `VUNDU_DRY_RUN=1` mode to preview setup commands.
- Full README, this changelog and an MIT licence.

### Changed
- Project renamed from "Packager Workstation" to **Vundu Studio**.
- Local builds now use the private tools installed by setup.
- Environment variables renamed to `VUNDU_PORT` and `VUNDU_HOME`; data directory is
  now `~/.vundu-studio`; request header is now `X-Vundu`.
- Remote build download works on Python versions without the tar extraction filter.

## [0.0.1] - 2026-11-20

### Added
- Local web server (Python standard library only), loopback-only with Host and
  custom-header protection.
- Automatic project recognition: Electron, Python and CMake, including name,
  version, entry file and icon.
- Project details: name, version, publisher, description and icon/logo upload.
- Build recipes for `.deb`, `.exe` and `.pkg` using electron-builder, PyInstaller,
  Nuitka, CMake and CPack.
- Build machines: local, or remote over SSH for Windows and macOS (including cloud Macs).
- Backup library with one section per project, grouped by version and numbered
  builds; rebuilds never overwrite earlier builds.
- "Source changed since last build" indicator and "save as" copy-out.

[0.0.4]: https://github.com/OWNER/vundu-studio/releases/tag/v0.0.4
[0.0.3]: https://github.com/OWNER/vundu-studio/releases/tag/v0.0.3
[0.0.2]: https://github.com/OWNER/vundu-studio/releases/tag/v0.0.2
[0.0.1]: https://github.com/OWNER/vundu-studio/releases/tag/v0.0.1
