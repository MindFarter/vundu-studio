# Changelog

All notable changes to Vundu Studio are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project uses [Semantic Versioning](https://semver.org/).

Versions 0.0.1 to 0.0.5 were private development builds, made before this
repository existed. 0.0.6 is the first version published here.

## [0.0.6] - 2026-11-24

### Added
- **Licensing & Signing page** in the left menu, between Machines and Build, with a clearly marked card for
  Ubuntu / Debian `.deb`, Raspberry Pi OS `.deb`, Windows `.exe` and macOS `.pkg`.
  - **GnuPG** signs the checksum list of `.deb` releases (Ubuntu and Raspberry Pi OS), with a button to create a key.
  - **osslsigncode** Authenticode-signs Windows `.exe`/`.msi` installers on this computer, with a timestamp
    server (`.pfx`, or PEM certificate and key).
  - **txoof/codesign** signs, packages and (optionally) notarises macOS `.pkg` files on the Mac build machine
    (Python and Node.js projects).
  - Passwords are kept in memory only and never saved, logged or put on a command line.
  - If signing is switched on and fails, the build fails.
- **Every release now has a `SHA256SUMS` file**, and signed releases also `SHA256SUMS.asc` and `PUBLIC-KEY.asc`.
  The Library shows what each release is signed with, and a **how to check** link shows the commands.
- The project's `LICENSE` file is installed inside `.deb` files at `/usr/share/doc/<package>/copyright`.
- **GitHub verification.** Add a GitHub repository to a project (Overview page). Each release in the Library
  then has a **verify against GitHub** link that compares the real files with the `SHA256SUMS` published on
  that repository's release (tag `v` + version), with a tick or cross per file.
- **`verify.py` for your users.** Each release of a project with a GitHub repository includes a ready-made,
  standalone `verify.py` (Python 3 only) that checks downloaded files against the same GitHub release.
  The template is `vundu/templates/verify.py` and can be used for any project.
- GnuPG and osslsigncode are optional Setup components.
- The Build page shows a **signed** / **not signed** mark next to each format.
- Tests for checksums, signing settings, the macOS steps and a real GnuPG sign-and-verify round trip.

### Changed
- **Passwords are asked for only when a build needs them**, in a box on the Build page that says exactly
  what the password is (for a GnuPG key: a brand-new password you made up when you created it, not one from
  anywhere else). The always-visible password boxes and Unlock buttons are gone from the Signing page.
- Menu order is now Projects, Library, Machines, Signing, Build, Setup.
- A failed release (for example a signing error) no longer leaves a half-made folder in the Library.

## [0.0.5] - 2026-11-24

Raspberry Pi OS support, a reorganised menu, a new dark-mode colour, and fixes from a full code review of 0.0.4.

### Added
- **Raspberry Pi OS (Trixie) `.deb` builds.** Node.js apps are built on this computer as an
  architecture-independent `.deb` (refused if they contain compiled `.node` add-ons). Electron apps are
  cross-built for 64-bit Pi (arm64). Python and CMake projects are built natively on a Raspberry Pi
  connected as a build machine over SSH, because they must be built by the same kind of processor.
- A **Raspberry Pi** card on the Machines page, with setup instructions for the Pi.
- `tests/test_core.py`: core checks, run with `python3 tests/test_core.py`.
- Git version control.
- A **Build** page in the left menu, under Machines: choose a project, see which machine builds each
  format, and build.

### Fixed
- **A second copy deleted the first copy's builds.** Start-up now opens the port first and, if it is
  taken, exits with a clear message without cleaning anything.
- **Remove could uninstall the wrong package.** Install and Remove now read the real package name from
  inside the `.deb` instead of guessing it from the project id (which differs after a rename or for
  duplicate project names).
- **Python builds on Windows/macOS build machines** failed because PyInstaller was never installed there,
  and Windows has no `python3` command. Remote Python builds now create a venv in the build folder and
  install PyInstaller (or Nuitka) into it.
- **A failing `pip install -r requirements.txt` was hidden** and produced a broken program. It now fails
  the build; only a missing `requirements.txt` is skipped.
- **A failed build cleared "changed since last build".** The marker is now only updated when at least one
  format was built.
- **Two builds of the same project at once** destroyed each other's build folder. A second build is now
  refused with a clear message.
- **The "changed" marker flickered on very large folders** because a cut-short scan gave a random
  fingerprint. Such folders now report "unknown" and show no marker.
- **Slow project list.** The list no longer scans every folder before showing; sizes and markers fill
  in from a background scan ("checking size...").
- **Versions such as `../x` could write builds outside the library.** Versions are validated when saved,
  when stored and when a library file is requested, and library paths are checked.
- **Build numbers could collide** after a build folder was deleted by hand (the finished build was then
  thrown away). The next number is now the highest existing one plus one.
- **Symbolic links** in a project were followed when it was copied (loops, huge copies, failures). They
  are now copied as links.
- **Unquoted values in generated files.** The web address, start file and service user are validated or
  shell-quoted, so a stray quote can no longer break the launcher or run extra commands.
- The change check and the package now use one shared list of skipped folders. Previously edits in
  `dist/`, `build/` or `out/` were packaged but never counted as changes.
- An unknown project id now answers "no such project" instead of a Python error message.
- The README was damaged (most sections below "Node.js servers" were empty) and described buttons that
  no longer exist. It is rewritten.

### Changed
- **Menu order is now Projects, Library, Machines, Build, Setup.** The Build tab moved out of the project
  page into its own page, so you choose your machines first and then build.
- **Releases moved into the Library**, as the first tab, with Backups next to it (it was the project's
  Releases tab). Releases has a project picker.
- **Dark mode accent colour is now #FFC014** (buttons, links, tabs, status bar, highlights), with dark text
  on it so it stays readable. Light mode is unchanged.
- **Questions in build, setup and install steps stay answerable, and are now impossible to miss.** Every
  job starts with a reminder. A question left half-written (for example `Ok to proceed? (y)`) is shown in
  the Output panel as "WAITING FOR YOU", and 20 seconds without output prints a notice that says to click
  the terminal window, type the answer (usually `y`) and press Enter.
- The desktop launcher now opens a terminal window so there is somewhere to answer those questions.
- The browser is opened without its start-up messages (for example snap/GTK warnings), and `BROWSER`
  is honoured. Works with any Chromium-based browser.
- `dist`, `build` and `out` folders in a project are packaged and tracked (use `.vunduignore` to leave
  them out). `.cache` is no longer packaged.
- The Releases notes and menu command use the real package name.
- Command output reading is shared in one place (`jobs.stream`) instead of four copies.

### Removed
- Unused code: `detect.fingerprint`, a repeated host-OS check, unused imports, the unused job label and
  an unused script argument.

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

[0.0.6]: https://github.com/MindFarter/vundu-studio/releases/tag/v0.0.6
