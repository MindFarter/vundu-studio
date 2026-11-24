# Vundu Studio

**Version 0.0.6** · Open-source application packaging workstation

Vundu Studio is a local web app with a developer-tool look (side menu, tabs, an
output console, dark and light themes) that is simple enough for a complete
beginner. It recognises your project, builds native installers (`.deb`, `.exe`,
`.pkg`) and files every build in a backup library, one section per project, so
each release is easy to find.

It is written in pure Python (standard library only) and needs nothing installed
to start. A one-off **Setup** button installs everything else.

- Development platform: Ubuntu Linux
- Release targets: Ubuntu, Raspberry Pi OS (Trixie) and Windows, with macOS designed into the architecture
- Build tools used: electron-builder, PyInstaller, Nuitka, `@yao-pkg/pkg`, CMake and CPack
- Signing tools used: [GnuPG](https://www.gnupg.org/), [osslsigncode](https://github.com/mtrojnar/osslsigncode) and [txoof/codesign](https://github.com/txoof/codesign)
- Browser: any current browser. It is developed with Opera and uses only
  standard web features, so Chrome, Chromium, Edge, Brave, Vivaldi and other
  Chromium-based browsers work too.

> ## Built on open-source software: credit goes to its developers
>
> **Vundu Studio is built around open-source software.** It does not compile,
> sign or package anything by itself. It is a friendly front end that drives
> the programs listed in [Built on open-source software](#built-on-open-source-software-and-attribution).
> **All attribution and credit for the real work belong to the original
> developers of those programs.** Vundu Studio is not affiliated with or
> endorsed by any of them. Each tool keeps its own licence and its own authors.

> **Status: early development.** Linux `.deb` builds are the most exercised path.
> Windows and macOS builds run on remote machines over SSH and need real-world
> testing. Please open issues.

## Contents

1. [Quick start](#quick-start)
2. [First-time setup](#first-time-setup)
3. [Using Vundu Studio](#using-vundu-studio)
   - [Licensing and signing](#licensing-and-signing)
   - [Node.js servers](#nodejs-servers-music-servers-apis-bots)
   - [Python apps](#python-apps)
   - [Raspberry Pi OS (Trixie)](#raspberry-pi-os-trixie)
   - [Keeping big data out of a package](#keeping-big-data-out-of-a-package-vunduignore)
   - [After you install a .deb](#after-you-install-a-deb)
   - [When a question needs your answer](#when-a-question-needs-your-answer)
4. [The backup library](#the-backup-library)
5. [Building for Windows and macOS](#building-for-windows-and-macos)
6. [Supported project types](#supported-project-types)
7. [Configuration](#configuration)
8. [Project layout](#project-layout)
9. [Security](#security)
10. [Troubleshooting](#troubleshooting)
11. [Tests](#tests)
12. [Roadmap](#roadmap)
13. [Built on open-source software and attribution](#built-on-open-source-software-and-attribution)
14. [Contributing and licence](#contributing-and-licence)

## Quick start

Requirements: Python 3.9 or newer (Python 3.12 or newer recommended).

    git clone https://github.com/MindFarter/vundu-studio.git
    cd vundu-studio
    python3 vundu_studio.py

Your browser opens at <http://127.0.0.1:8765>. If it does not, open that address
yourself. Stop the server with Ctrl+C.

Options:

    python3 vundu_studio.py --no-browser     # do not open a browser tab
    VUNDU_PORT=9000 python3 vundu_studio.py  # use another port

Keep the terminal window open while you use Vundu Studio. Some tools may ask you
a question there (see [When a question needs your answer](#when-a-question-needs-your-answer)).

Optional desktop launcher (Linux): copy `vundu-studio.desktop` into
`~/.local/share/applications/`. Keep it next to `run.sh`, or edit its `Exec=`
line. The launcher opens a terminal window on purpose, so you can answer
questions there.

If port 8765 is already in use, Vundu Studio tells you and exits without
touching the running copy.

## First-time setup

Open the **Setup** page (the status bar at the bottom shows "Setup needed (N)"
until everything required is installed). Tick what you need and press **Install
everything missing**. This is a one-off step. You can return to the Setup page
at any time to re-check or repair.

What gets installed, and where:

| Component             | Used for                                    | Installed by          | Location       |
|-----------------------|---------------------------------------------|-----------------------|----------------|
| Package manager health| Repairs an interrupted install              | `dpkg --configure -a` | system         |
| Python venv module    | Creates the private environment             | apt (python3-venv)    | system         |
| C/C++ compiler, make  | Nuitka, CMake projects                      | apt (build-essential) | system         |
| CMake + CPack         | CMake projects                              | apt / brew / winget   | system         |
| Node.js + npm         | Node.js and Electron projects               | apt / brew / winget   | system         |
| dpkg-deb, fakeroot    | Building .deb files                         | apt                   | system         |
| patchelf (optional)   | Nuitka on Linux                             | apt                   | system         |
| OpenSSH client        | Remote Windows/macOS builds                 | apt                   | system         |
| VirtualBox (optional) | Windows build machines on this computer     | apt                   | system         |
| GnuPG (optional)      | Signing .deb and Raspberry Pi packages      | apt / brew / winget   | system         |
| osslsigncode (optional)| Signing Windows .exe installers            | apt / brew            | system         |
| NSIS (optional)       | .exe from CMake projects                    | apt / brew / winget   | system         |
| PyInstaller, Nuitka   | Python apps                                 | pip                   | private venv   |
| electron-builder      | Electron apps                               | npm                   | private folder |
| pkg (optional)        | Windows/macOS programs from Node.js servers | npm                   | private folder |

- Python tools live in a private virtual environment (`~/.vundu-studio/venv`) and
  Node tools in `~/.vundu-studio/tools`. They never touch your system Python.
- **One password prompt.** All OS packages are installed in a single
  administrator step.
- **Self-repairing.** If an earlier install was interrupted (dpkg says you must
  run `dpkg --configure -a`), Setup runs that repair first, then installs. If one
  package cannot be installed, the others are still installed and the failure is
  reported.
- OS packages need administrator rights. Vundu Studio uses `pkexec` (a graphical
  password prompt) or passwordless `sudo` if available. If neither is possible it
  prints the exact `sudo` command for you to run in a terminal, then you press
  Install again.
- On Ubuntu this uses apt; on macOS it needs [Homebrew](https://brew.sh); on
  Windows it uses winget. Ubuntu is the tested platform.
- An internet connection is required during setup.
- `VUNDU_DRY_RUN=1` shows the setup commands without running them.

## Using Vundu Studio

The left menu runs top to bottom in the order you use it: **Projects**,
**Library**, **Machines**, **Signing** (Licensing & Signing), **Build**,
**Setup**. Run **Setup** once first (see [First-time setup](#first-time-setup)).

1. **Projects: add a project.** Press **+ Add** and browse to your project
   folder. The type, name, version, start file and any icon or logo image are
   detected automatically. On the **Overview** tab check or change:
   - **Name, version, publisher and description.** The version may use letters,
     numbers and `. + ~ - _` only (for example `1.0.0`). Each version gets its own
     folder in the Library.
   - **Start file** (Node.js and Python), and the **Python builder** (PyInstaller
     or Nuitka) for Python projects.
   - For Node.js and Python: **Show in the app menu, with an icon**. For Node.js
     also the **web address** to open, and the optional
     [background service](#nodejs-servers-music-servers-apis-bots).
   - **Icon / logo** (PNG, ICO or SVG). A clean default icon is made if you skip it.
   - **GitHub repository** (optional): for checking releases and for the
     `verify.py` your users can run (see
     [Verifying against your GitHub repository](#verifying-against-your-github-repository)).

   Press **Save details**, then **Next: Build**.
2. **Machines: choose where each installer is built.** This computer builds for
   itself automatically. Connect other machines here: a Windows PC or VM, a Mac,
   and a Raspberry Pi (see
   [Building for Windows and macOS](#building-for-windows-and-macos) and
   [Raspberry Pi OS (Trixie)](#raspberry-pi-os-trixie)).
3. **Signing: switch on signing for each kind of installer**, with your key or
   certificate (see [Licensing and signing](#licensing-and-signing)). Optional, but
   recommended for anything you give to other people.
4. **Build: pick a project and tick the formats you want.** The choices are
   `.deb` (Ubuntu / Debian), `.deb` for Raspberry Pi OS (Trixie), `.exe`
   (Windows) and `.pkg` (macOS). Each format shows which machine will build it and
   whether it will be **signed**. Press **Build & save to Library**. If a signing
   password is needed, a box asks for it and builds again. Only one build of a
   project can run at a time.
5. **Library: your finished installers.** They are saved automatically.
   - **Releases** lists the installers of one project (choose it at the top).
   - **Backups** lists every project, newest first.
   - Each release shows what it is signed with, and has links to **download** each
     file, **copy to folder...**, **install on this computer** and **remove** (for
     `.deb` files on Linux), **how to check** and **verify against GitHub**.

Around the screen:

- **Output panel.** Progress of builds, setup and installs appears here, and
  opens by itself. **clear**, **_** (make small) and **x** (close) are at its top;
  the **Output** button in the status bar opens it again. If a tool asks a
  question, see [When a question needs your answer](#when-a-question-needs-your-answer).
- **Status bar.** Shows whether Setup is complete, the version, and the data folder.
- **Themes.** The button at the top right switches between dark and light. Your
  choice is remembered; the first time it follows your system. Dark mode uses a
  yellow accent (`#FFC014`).
- **Change dot.** A small dot next to a project means its source changed since
  the last successful build. A build that fails does not clear the dot. For very
  large folders the check cannot be completed in time, and Vundu Studio shows no
  dot rather than a wrong one.

### Licensing and signing

Vundu Studio is free software under the MIT licence. The **Signing** page (left
menu, between Machines and Build) helps the people who use your packages be sure
they are the originals and were not changed. Each kind of installer has its own
card, clearly marked:

| Card                       | Signed with                                         | Where it signs                         | You need                                              |
|----------------------------|-----------------------------------------------------|----------------------------------------|-------------------------------------------------------|
| Ubuntu / Debian `.deb`     | [GnuPG](https://www.gnupg.org/)                     | this computer                          | a GnuPG key (the page can create one)                 |
| Raspberry Pi OS `.deb`     | GnuPG (same as Ubuntu: Pi OS is Debian)             | this computer, whichever machine built it | a GnuPG key (can be the same one)                  |
| Windows `.exe`             | [osslsigncode](https://github.com/mtrojnar/osslsigncode) | this computer, no Windows machine needed | a code-signing certificate (`.pfx`, or PEM + key)   |
| macOS `.pkg`               | [txoof/codesign](https://github.com/txoof/codesign) | the Mac build machine                  | Apple Developer account ($99/year), Developer ID certificates |

Install GnuPG and osslsigncode from **Setup**. Then, on the Signing page, fill in
a card, tick **Sign every build of this type**, and press **Save**. The Build page
shows a **signed** or **not signed** mark next to every format.

- **If signing is on and fails, the build fails.** You never get an unsigned
  package by accident.
- **Passwords.** There are no password boxes on the page. If your key or
  certificate is locked with a password, Vundu Studio asks for it in a box on the
  Build page, only at the moment a build needs it, and then builds again. It keeps
  the password in memory until you stop Vundu Studio. It is never saved to disk,
  never put on a command line, and never shown in the Output.
  - **GnuPG key:** the password is a **brand-new password that you make up
    yourself** when you press **Create a key for me**. It is not from any website
    or account; nobody else has it. Write it down: it cannot be recovered. Leave it
    empty for a key with no password (simpler, but anyone who copies the key can
    sign as you). If you forget it, create a new key.
  - **Windows certificate (`.pfx`):** the password you chose when you exported the
    file, or that your certificate authority gave you when you downloaded it.
    Leave it alone if the file has none.
  - **macOS:** Vundu Studio never asks. Apple's tools use the Mac's keychain.

**Every release is checkable, with or without signing.** Each build in the
Library gets a `SHA256SUMS` file (the same format as `sha256sum`). With GnuPG
signing on, it also gets `SHA256SUMS.asc` (the signature) and `PUBLIC-KEY.asc`
(your public key). Your project's own `LICENSE` file is installed inside every
`.deb` at `/usr/share/doc/<package>/copyright`.

**To publish a release on GitHub:** open Library, Releases, download the
installer plus `SHA256SUMS` (and the GnuPG files and `verify.py`, if present), and
attach them to your GitHub release. Name the release tag `v` plus the version, for
example `v1.0.0`. The **how to check** link on each release shows people the
commands:

    sha256sum -c SHA256SUMS --ignore-missing     # the file is unchanged
    gpg --import PUBLIC-KEY.asc                  # then:
    gpg --verify SHA256SUMS.asc SHA256SUMS       # the checksums come from the publisher

Publish your key fingerprint on your GitHub profile or README, so people can
compare it with the one gpg shows (a second channel, so a fake release cannot
bring its own fake key).

#### Verifying against your GitHub repository

On a project's **Overview** page, enter its **GitHub repository** (for example
`MindFarter/vundu-studio`; the full web address works too). Then:

- **For you:** every release in the Library gets a **verify against GitHub**
  link. It downloads the `SHA256SUMS` attached to your GitHub release (tag `v` +
  version), hashes the real files on your disk, and shows a green tick or a red
  cross for each one. It only contacts GitHub when you press it, and only
  `github.com`.
- **For your users:** every release also gets a ready-made `verify.py`, with your
  repository and version filled in. Attach it to the GitHub release. Users put it
  next to the installer they downloaded and run `python3 verify.py`. It needs only
  Python 3. The template is [vundu/templates/verify.py](vundu/templates/verify.py).
  You can also copy it into any other project, replace `REPO` and `TAG` at the top
  (or run it with `--repo owner/name --tag v1.0.0`).

This proves the files match what is published on that repository, so it is only as
trustworthy as the repository and your GitHub account (use two-factor sign-in).
GnuPG signing adds proof that you made the files. Use both for best protection.

Good to know:

- **Linux has no "trusted publisher" pop-up.** GnuPG signatures are checked by
  people on purpose (above). A signed apt repository, where `apt` checks
  automatically, is on the roadmap.
- **Windows:** without a certificate from a certificate authority, Windows shows
  "Unknown publisher". A self-made certificate does not remove that. Certificates
  that are kept on a hardware token are not supported yet.
- **macOS** (not yet tested by the developers on a real Mac): needs the one-time
  setup shown on the Signing page (install `pycodesign.py` on the Mac, and store
  your notarisation login with `xcrun notarytool store-credentials`). The Mac's
  login keychain must be unlocked while building. It covers Python and Node.js
  projects. Electron and CMake `.pkg` files are not signed, and the Output says so.
- Signing of Electron and CMake **`.deb`** files works (the checksum list is
  signed). The licence file is only added to the `.deb` files Vundu Studio
  assembles itself (Node.js and Python).

#### Verifying Vundu Studio itself

The same method works for Vundu Studio's own releases: attach a `SHA256SUMS` file
(`sha256sum vundu-studio-X.Y.Z.zip > SHA256SUMS`) and its signature
(`gpg --armor --detach-sign SHA256SUMS`) to each GitHub release.

### Node.js servers (music servers, APIs, bots)

A plain Node.js project (a `package.json` without Electron) is detected as a
**Node.js app / server**. The start file is read from `main` or from your
`start` script. Building a `.deb`:

- runs `npm install --omit=dev`, so only production dependencies are shipped;
- installs your app into `/opt/<package>` and adds a command with the package
  name (the project name, lower-case, with dashes);
- depends on the `nodejs` package, so installing the `.deb` pulls Node.js in;
- adds an application-menu entry with an icon (a clean default icon is made if
  you did not supply one);
- if you set a **web address** (for example `http://localhost:3000`), the menu
  entry starts the server and opens that address. The port is detected from your
  code where possible. The address must start with `http://` or `https://` and
  may not contain spaces, quotes or shell characters.

Optional **background service (systemd)**:

- **Run as a background service** installs a systemd unit for your app.
- **Start automatically** enables and starts it right after install, and at every
  boot. It is stopped and disabled when the package is removed.
- **Run the service as user** lets a server read files in your home folder (for
  example a music library). Leave it empty to use a safe temporary user. Use a
  normal user name such as `alex`.

`.exe` and `.pkg` builds of a Node.js server use `@yao-pkg/pkg` (Node 20 targets).

### Python apps

Python projects are built with PyInstaller (default) or Nuitka (choose on the
Overview page). `requirements.txt` is installed first. **If installing the
requirements fails, the build fails** (it is never hidden).

On this computer the private environment from Setup is used. On a remote
Windows or macOS build machine, Vundu Studio creates a throw-away virtual
environment inside the build folder and installs PyInstaller (or Nuitka) there,
so the remote machine only needs Python.

### Raspberry Pi OS (Trixie)

Tick **.deb  Raspberry Pi OS (Trixie)** on the Build page. How it is built
depends on the project type, because a program must be built by the same kind
of processor it will run on (your PC is x86, a Pi is ARM):

| Project  | Built on                    | Result                                             |
|----------|-----------------------------|----------------------------------------------------|
| Node.js  | this computer               | `<name>_<version>_all.deb`, runs on any Pi (32- or 64-bit) |
| Electron | this computer               | 64-bit Pi (arm64) `.deb`, cross-built by electron-builder  |
| Python   | a Raspberry Pi over SSH     | native `.deb` for that Pi (arm64 or armhf)         |
| CMake    | a Raspberry Pi over SSH     | native `.deb` for that Pi (arm64 or armhf)         |

- A Node.js app that has compiled add-ons (`.node` files in `node_modules`) is
  refused, because those files would be built for your PC. Build it on a Pi.
- For Python and CMake, open **Machines**, find **Raspberry Pi OS (.deb)**, enable
  SSH on the Pi (`sudo raspi-config`, Interface Options, SSH) and install the
  tools there: `sudo apt install python3 python3-venv build-essential cmake dpkg-dev fakeroot`.
  Then connect it like any other machine.
- Electron builds for 32-bit Pi OS are not offered yet.
- Pi `.deb` files made for arm64 cannot be installed on your PC, so the Library
  only offers **install on this computer** for the architecture-independent
  Node.js ones.

### Keeping big data out of a package (.vunduignore)

Everything in your project folder is copied into every build, except tool and
cache folders (`.git`, `node_modules`, `__pycache__`, `.venv`, `venv`, `.cache`,
`vundu-out`, `.vundu`). Folders such as `dist`, `build` and `out` **are**
packaged, because they are often real source (compiled output), and edits in
them count as changes.

If your folder holds data such as music, videos or databases, list those in a
file called `.vunduignore` inside the project folder, one pattern per line
(`#` starts a comment, `*` is a wildcard):

    # not part of the program
    music
    *.mp3
    cache

The same file also keeps those folders out of the change check and the size
figure. Symbolic links are copied as links, never followed.

### After you install a .deb

Once installed, a package lives in `/opt/<package>` with a command of the same
name, and (if enabled) an entry in the application menu. Press the Super key and
search for it.

- List its files: `dpkg -L <package>`
- Remove it: use **remove** in the Library, or `sudo apt remove <package>`

The Library's **install** and **remove** links read the real package name from
inside the `.deb` file, so they always act on the package you built, even if you
later renamed the project.

### When a question needs your answer

Some tools (for example `npx`, or an installer) can stop and ask a question such
as "Ok to proceed? (y)". Vundu Studio leaves your keyboard connected on purpose,
so you stay in control. When that happens:

- the Output panel shows a line starting with **WAITING FOR YOU** that repeats
  the question;
- after 20 seconds without any output the panel also prints **NO OUTPUT FOR 20
  SECONDS**, which tells you what to do;
- **click the terminal window where you started Vundu Studio, type your answer
  (usually `y`) and press Enter.**

Every build, setup and install job starts with a reminder of this. A long quiet
step (a big compile) can trigger the 20-second message without any question
being asked. In that case just wait.

## The backup library

Every finished installer is stored by project, then version, then build.
Nothing is ever overwritten:

    ~/.vundu-studio/library/
      my-app/
        1.0.0/
          build-001/   my-app_1.0.0_amd64.deb, SHA256SUMS, build.log, release.json
                       (with GnuPG signing also SHA256SUMS.asc, PUBLIC-KEY.asc)
          build-002/   (a rebuild of the same version after a code update)
        1.1.0/
          build-001/

- Build numbers always go up, even if you delete an old build by hand.
- `build.log` holds the full output of the job that made the build.
- `SHA256SUMS` lets anyone check the installer is unchanged. Signed releases show a badge (GnuPG signed, Windows signed, macOS signed, notarised) in the Library.
- **copy to folder...** copies an installer anywhere you choose.
- **install on this computer** and **remove** work for `.deb` files on Linux.

## Building for Windows and macOS

An installer has to be built on the same kind of computer it is for. This
computer builds for itself automatically. For the others, open **Machines** and
connect a second computer or a virtual machine over SSH. Vundu Studio uploads
the project, runs the build there, and downloads the result into your library.

### Windows

1. Use a Windows PC or virtual machine with **OpenSSH Server** switched on, plus
   Git for Windows (its `bash` runs the build steps), Node.js and Python.
2. Enter its address, user name and port on the Machines page. Press **Create a
   key for me**, add the public key to the machine as shown, then **Test
   connection** and **Save**.

### Windows in VirtualBox on this computer

1. Install VirtualBox from Setup.
2. On the Machines page, pick a VM and press **Use this VM**. Vundu Studio
   starts it, adds an SSH port-forward (`127.0.0.1:2222` and up), waits for SSH
   and saves it as your Windows build machine. Or press **Create a new Windows
   VM** and give it a Windows ISO (you need a valid Windows licence).
3. First time with a new VM: inside Windows, open PowerShell as Administrator and
   paste the one-line setup shown on the Machines page. It turns on SSH,
   installs Git, Node.js and Python, and authorises your key.

### macOS

A real Mac (or a rented cloud Mac such as MacinCloud) is needed to build `.pkg`
files. Type its address and user on the Machines page. Apple only allows macOS in
a virtual machine on Apple hardware, so VirtualBox is offered for macOS only
when Vundu Studio runs on a Mac.

## Supported project types

| Type     | Detected by                  | `.deb`                      | Raspberry Pi `.deb`        | `.exe` / `.pkg`                        |
|----------|------------------------------|-----------------------------|----------------------------|----------------------------------------|
| Electron | `package.json` with electron | electron-builder            | electron-builder (arm64)   | electron-builder (NSIS / pkg)          |
| Node.js  | `package.json`               | launcher, optional service  | same, architecture `all`   | `@yao-pkg/pkg` (Node 20)               |
| Python   | `.py` files, `pyproject.toml`, `requirements.txt` | PyInstaller or Nuitka | built on a Pi over SSH | PyInstaller or Nuitka on the target OS |
| CMake    | `CMakeLists.txt`             | CPack (DEB)                 | built on a Pi over SSH     | CPack (NSIS / productbuild)            |

CMake projects need `install()` rules for CPack to package anything.

## Configuration

| Setting            | Where        | Meaning                                         |
|--------------------|--------------|-------------------------------------------------|
| `--no-browser`     | command line | Do not open a browser tab at start              |
| `VUNDU_PORT`       | environment  | Port to listen on (default 8765)                |
| `VUNDU_HOME`       | environment  | Data folder (default `~/.vundu-studio`)         |
| `VUNDU_DRY_RUN=1`  | environment  | Setup shows commands without running them       |
| `BROWSER`          | environment  | Browser to open instead of the system default   |

The data folder holds `projects/` (one folder per project), `library/`,
`work/` (temporary build copies, deleted after each build), `venv/` and `tools/`
(private tools), `targets.json` (your build machines), `signing.json` (which signing
is on, key ids and certificate paths: never passwords) and `setup.json`.

## Project layout

    vundu_studio.py      entry point (python3 vundu_studio.py)
    run.sh               shell launcher
    vundu-studio.desktop Linux desktop launcher
    vundu/
      server.py          HTTP API, build and setup jobs
      detect.py          automatic project recognition and change check
      builders.py        build recipes, local and SSH runners
      library.py         projects, backup library, build machine settings
      setup.py           first-run dependency detection, repair and installation
      machines.py        build-machine discovery, SSH test, key creation
      signing.py         licensing and signing: GnuPG, osslsigncode, txoof/codesign, GitHub check
      templates/verify.py  the verify.py template added to releases
      vbox.py            VirtualBox VMs as build machines
      jobs.py            background jobs, bounded memory, command output streaming
      icon.py            default app icon generator
      web/index.html     the user interface
    tests/test_core.py   core checks (python3 tests/test_core.py)
    README.md  CHANGELOG.md  LICENSE

## Security

Vundu Studio is a tool for one person on one computer. It can run build
commands and install packages, so it is locked down:

- It listens on `127.0.0.1` only, never on the network.
- Every request must carry a `Host` of `127.0.0.1` or `localhost`. This blocks
  DNS-rebinding attacks. The only exception is the one-time Windows VM setup
  script, which a VirtualBox guest fetches from `10.0.2.2` (how a NAT guest
  reaches its host).
- Every change (POST/PUT) needs a custom `X-Vundu` header. A web page on another
  site cannot send it without a browser permission check that Vundu never grants.
- Values that end up in generated shell lines and installed files are checked:
  versions, web addresses and service user names are validated, and the start
  file and project names are shell-quoted.
- Library file paths are validated, so a request cannot read or copy files
  outside the library.
- Signing passwords are kept in memory only (never saved, never logged, never on a
  command line). `signing.json` holds only key ids and file paths. Keep your
  private keys and certificates out of your project folders and out of git.
- Administrator rights are only used for installing OS packages and for
  installing or removing a `.deb`, through `pkexec` or `sudo`.
- Build machines are reached with SSH keys (no passwords stored). New host keys
  are accepted on first contact (`StrictHostKeyChecking=accept-new`).
- Only build projects you trust: building runs your project's own scripts
  (`npm install`, `pip install`, CMake).

## Troubleshooting

- **Browser messages in the terminal** (for example `Failed to load module ...
  gio-modules` or `zygote ... Broken pipe`). These come from a snap-packaged
  browser, not from Vundu Studio. Vundu hides the browser's start-up output, but
  you can also run with `--no-browser` and open the address yourself.
- **"cannot start on port 8765".** Vundu Studio is probably already running.
  Open `http://127.0.0.1:8765/`, or use another port with `VUNDU_PORT`.
- **A box asks for a password when I build.** Your signing key or certificate is
  locked. Type its password (for a GnuPG key made in Vundu Studio: the new one you
  made up when you created it). Vundu Studio then builds again.
- **"That password was not accepted".** Type it again. If you forgot a GnuPG key
  password, create a new key on the Signing page.
- **"GitHub has no release tagged v1.0.0".** Publish the release on GitHub, tag it
  `v` plus the version, and attach `SHA256SUMS` to it.
- **A step seems stuck.** A question may be waiting in the terminal. See
  [When a question needs your answer](#when-a-question-needs-your-answer).
- **"dpkg was interrupted".** Run Setup. It repairs this first.
- **"No build machine is set up for ...".** Open Machines and connect one. For a Raspberry Pi `.deb` of a Python or CMake project that means a real Pi.
- **Python build fails with "No module named PyInstaller".** Run Setup (for this
  computer). Remote machines get PyInstaller automatically.
- **A build step fails.** The full output is in the Output panel and, for
  finished builds, in `build.log` next to the installer.
- **The change dot looks wrong.** Check your `.vunduignore`. Very large folders
  cannot be checked completely and show no dot.
- **Start over.** Stop Vundu Studio and delete `~/.vundu-studio`. Your own
  project folders are never modified.

## Tests

    python3 tests/test_core.py

Plain Python asserts, no extra packages. They cover version cleaning, input
validation, path safety, build numbering, checksums, signing settings, a real GnuPG
sign-and-verify round trip, the GitHub check and verify.py against a fake local GitHub, the change check, job logs, question detection and the
generated build steps.

## Roadmap

Ideas, not promises:

- More real-world testing of Windows and macOS builds
- Raspberry Pi: 32-bit Electron builds, and building Python/CMake without a real Pi
- Code signing for `.exe` and `.pkg`
- A signed apt repository, so `apt` checks Pi and Ubuntu packages automatically
- Windows signing with a hardware token (PKCS#11), and macOS signing for Electron and CMake
- More project types (for example Rust and Go)
- Automatic update of the private tools

## Built on open-source software and attribution

**Vundu Studio is built around open-source software, and all attribution
belongs to the original developers of those programs.** Vundu Studio only
detects your project, asks a few questions and runs these tools for you.
Without them it would do nothing. Please thank, star, support and credit the
people who made them.

| Used for | Software | Project home |
| --- | --- | --- |
| Language and web server | Python | <https://www.python.org/> |
| JavaScript projects and packages | Node.js and npm | <https://nodejs.org/> |
| Electron installers | electron-builder | <https://www.electron.build/> |
| Python to native executable | PyInstaller | <https://pyinstaller.org/> |
| Python to compiled executable | Nuitka | <https://nuitka.net/> |
| Node.js to native executable | @yao-pkg/pkg | <https://github.com/yao-pkg/pkg> |
| C and C++ projects | CMake and CPack | <https://cmake.org/> |
| Windows installers | NSIS | <https://nsis.sourceforge.io/> |
| `.deb` packages | dpkg and fakeroot | <https://wiki.debian.org/Teams/Dpkg> |
| macOS packages | pkgbuild and productbuild (Apple) | <https://developer.apple.com/> |
| Signing `.deb` checksums | GnuPG | <https://www.gnupg.org/> |
| Signing Windows installers | osslsigncode | <https://github.com/mtrojnar/osslsigncode> |
| Signing macOS packages | txoof/codesign | <https://github.com/txoof/codesign> |
| Remote Windows and macOS builds | OpenSSH | <https://www.openssh.com/> |
| Windows in a virtual machine | VirtualBox | <https://www.virtualbox.org/> |

Also thank you to the Debian, Ubuntu and Raspberry Pi OS communities, and to
the authors of every library those tools depend on.

All product and project names are trademarks of their respective owners and are
used here only to say which software Vundu Studio works with. If you are an
author of one of these tools and want your entry changed or added, please open
an issue and it will be fixed straight away.

## Contributing and licence

Issues and pull requests are welcome. Please run `python3 tests/test_core.py`
before sending a change, and keep the app standard-library only.

Released under the MIT licence. See [LICENSE](LICENSE). The MIT licence covers
Vundu Studio's own code only. The tools listed in
[Built on open-source software](#built-on-open-source-software-and-attribution)
are not part of this repository and keep their own licences.
