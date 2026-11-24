# Vundu Studio

**Version 0.0.4** · Open-source, cross-platform application packaging workstation

Vundu Studio is a local web app (with a desktop launcher) with a developer-tool
look (side menu, tabs, output console, dark and light themes) that is simple
enough for a complete beginner. It recognises your project, builds native
installers (`.deb`, `.exe`, `.pkg`) and files every build in a backup library,
one section per project, so each release is easy to find.

It is written in pure Python (standard library only) and needs nothing
installed to start. A one-off **Setup** button installs everything else.

- Development platform: Ubuntu Linux
- Release targets: Ubuntu and Windows, with macOS designed into the architecture
- Build tools used: electron-builder, PyInstaller, Nuitka, CMake and CPack

> Status: early development. Linux `.deb` builds are the most exercised path.
> Windows and macOS builds run on remote machines over SSH and need real-world
> testing. Please open issues.

## Contents

1.  [Quick start](#quick-start)
2.  [First-time setup](#first-time-setup)
3.  [Using Vundu Studio](#using-vundu-studio)
- [Node.js servers](#nodejs-servers-music-servers-apis-bots)
- [Themes](#themes)
- [After you install a .deb](#after-you-install-a-deb)
- 
  [Keeping big data out of a package (.vunduignore)](#keeping-big-data-out-of-a-package-vunduignore)
4.  [The backup library](#the-backup-library)
5.  [Building for Windows and macOS](#building-for-windows-and-macos)
6.  [Supported project types](#supported-project-types)
7.  [Configuration](#configuration)
8.  [Project layout](#project-layout)
9.  [Security](#security)
10. [Troubleshooting](#troubleshooting)
11. [Roadmap](#roadmap)
12. [Contributing and licence](#contributing-and-licence)

## Quick start

Requirements: Python 3.9 or newer (Python 3.12 or newer recommended).

    unzip Vundu_Studio_0.0.4.zip
    cd Vundu_Studio
    python3 vundu_studio.py

Your browser opens at <http://127.0.0.1:8765>. If it does not, open that
address yourself. Stop the server with Ctrl+C.

Optional desktop launcher (Linux): copy vundu-studio.desktop into
~/.local/share/applications/. Keep it next to run.sh or edit its Exec= line.

Options:

    python3 vundu_studio.py --no-browser     # do not open a browser tab
    VUNDU_PORT=9000 python3 vundu_studio.py  # use another port

## First-time setup

On first launch a **First-time setup** banner appears. Click **Set up now** (or
open the **Setup** tab), tick what you need, and press **Install selected**. This
is a one-off step; the banner disappears once all required tools are present.
You can return to the Setup tab at any time to re-check or repair.

What gets installed, and where:


|Component            |Used for                                   |Installed by         |Location      |
|---------------------|-------------------------------------------|---------------------|--------------|
|Python venv module   |Creates the private environment            |apt (python3-venv)   |system        |
|C/C++ compiler, make |Nuitka, CMake projects                     |apt (build-essential)|system        |
|CMake + CPack        |CMake projects                             |apt / brew / winget  |system        |
|Node.js + npm        |Electron projects                          |apt / brew / winget  |system        |
|dpkg-deb, fakeroot   |Building .deb files                        |apt                  |system        |
|patchelf (optional)  |Nuitka on Linux                            |apt                  |system        |
|OpenSSH client       |Remote Windows/macOS builds                |apt                  |system        |
|VirtualBox (optional)|Windows build machines on this computer    |apt                  |system        |
|NSIS (optional)      |.exe from CMake projects                   |apt / brew / winget  |system        |
|PyInstaller, Nuitka  |Python apps                                |pip                  |private venv  |
|electron-builder     |Electron apps                              |npm                  |private folder|
|pkg (optional)       |Windows/macOS programs from Node.js servers|npm                  |private folder|

- Python tools live in a private virtual environment (~/.vundu-studio/venv) and
  electron-builder in ~/.vundu-studio/tools. They never touch your system
  Python.
- **One password prompt.** All OS packages are installed in a single
  administrator step.
- **Self-repairing.** If an earlier install was interrupted (dpkg was
  interrupted, you must manually run 'dpkg --configure -a'), Setup runs that
  repair first, then installs. If one package cannot be installed, the others
  are still installed and the failure is reported.
- OS packages need administrator rights. Vundu Studio uses pkexec (a graphical
  password prompt) or passwordless sudo if available. If neither is possible it
  prints the exact sudo apt-get install ... command for you to run in a
  terminal, then you press Install again.
- On Ubuntu this uses apt; on macOS it needs [Homebrew](https://brew.sh); on
  Windows it uses winget. Ubuntu is the tested platform.
- An internet connection is required during setup.

## Using Vundu Studio

1.  **Add project**: choose your project folder. The type, name, version, entry
    file and any icon/logo image are detected automatically.
2.  **Project details**: edit name, version, publisher, description and upload an
    icon or logo (PNG, ICO or SVG). Click **Save details**.
3.  **Build installers**: tick .deb, .exe and/or .pkg and press **Build & store
    in library**. A live log shows progress.
4.  Finished installers are stored automatically in the backup library.

### Node.js servers (music servers, APIs, bots)

A plain Node.js project (a package.json without Electron) is detected as a 
**Node.js app / server**. The start file is read from main or from your start
script. Building a .deb:

- runs npm install --omit=dev so only production dependencies are shipped;
- installs your app into /opt/
- 
-    
-      

   

### ** ** 

- 
-  
- 
-  

  

###   

    # not part of the program
    music
    *.mp3
    cache

  

###  

 

## 

    ~/.vundu-studio/library/
      my-app/
        1.0.0/
          build-001/   my-app_1.0.0_amd64.deb, build.log, release.json
          build-002/   (a rebuild of the same version after a code update)
        1.1.0/
          build-001/

- 
-  
-  
- 

##   

-   
-   
-  
-   

|||
|||
|||
|||
|||


    

###  

1.     
2.     
3.  

  

 ** **  

>   

### 1.   
2.     
3.   

### 1.     
2.   
3.   

 

 

## 
||||||
||||||
||||||
||||||
||||||
||||||

-  
-  
-  

## 
||||
||||
||||
||||
||||
||||

 



    vundu_studio.py      entry point (python3 vundu_studio.py)
    run.sh               shell launcher
    vundu-studio.desktop Linux desktop launcher
    vundu/
      server.py          HTTP API, build and setup jobs
      detect.py          automatic project recognition
      builders.py        build recipes, local and SSH runners
      library.py         projects, backup library, build machine settings
      setup.py           first-run dependency detection, repair and installation
      machines.py        build-machine discovery, SSH test, key creation
      vbox.py            VirtualBox VMs as build machines
      jobs.py            background jobs with bounded memory
      icon.py            default app icon generator
      web/index.html     the user interface
    README.md  CHANGELOG.md  LICENSE

## - 
-   
-  
-  
- 
-  

## 
|||
|||
|||
|||
|||
|||
|||
|||
|||
|||
|||

## - 
- 
- 
- 
- 
- 
- 
- 
- 

##   

