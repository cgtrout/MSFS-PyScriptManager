# Technical Notes

## Launcher and Script Development Notes
- The launcher EXE is provided for convenience, but you can also launch the script manually.
- You can launch `Launcher/Launcher.py` from `WinPython/WinPython Command Prompt.exe` if you prefer not to launch from the EXE.
- The EXE can be built by launching `Build.bat` in `Launcher/LauncherApp` (the TCC C compiler is included: https://bellard.org/tcc/).
- You can create your own scripts and run them as well.
- If you need to add libraries, use `WinPython/WinPython Command Prompt.exe` and run `pip` from there to install into the WinPython directory.
- Recommended editor: [Visual Studio Code](https://code.visualstudio.com/download). The built-in `Edit` button opens the selected script in VS Code if it is installed.

## WinPython Notes
- Uses WinPython to allow standalone installation: https://github.com/winpython
- Supports multiple versions of WinPython.
- To switch versions, run `MSFS-PyScriptManager.exe --pick` (opens a menu to switch to other installed versions).
- Extract new WinPython versions into the `WinPython` directory, then use the `--pick` command to switch.
- The launcher uses `Launcher/requirements.txt` to ensure required modules are installed through pip.
- The active Python install is configured in `Launcher/launcher.ini` under `[Python]` with `PythonDir=<relative path>`.

## BYO Python Mode
- If no WinPython is present, you can run the launcher EXE without bundled Python.
- In this mode, the launcher uses your system Python from `PATH`.
- On first run in BYO mode, the launcher can prompt to install dependencies from `Launcher/requirements.txt`.
- This preference is saved in `Launcher/launcher.ini` under:
  - `[BYO]`
  - `AutoInstallDeps=true|false`

## Update Checker Config
- The launcher checks GitHub releases on startup by default.
- Update checker settings are read from `Launcher/launcher.ini` under `[Update]`:
  - `RepoOwner`
  - `RepoName`
  - `CheckOnStartup=true|false`
  - `CheckIntervalHours=<hours>`
