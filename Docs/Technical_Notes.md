# Technical Notes

## Launcher and Script Development Notes
- The launcher EXE is provided for convenience, but you can also launch the script manually.
- You can launch `Launcher/Launcher.py` from `WinPython/WinPython Command Prompt.exe` or even system python if you prefer not to launch from the EXE.
- The EXE can be built by launching `Build.bat` in `Launcher/LauncherApp` (the TCC C compiler is included: https://bellard.org/tcc/).
- You can create your own scripts and run them as well.
- If you need to add libraries, use `WinPython/WinPython Command Prompt.exe` and run `pip` from there to install into the WinPython directory.
- Recommended editor: [Visual Studio Code](https://code.visualstudio.com/download). The built-in `Edit` button opens the selected script in VS Code if it is installed.

## VS Code Integration
- VS Code `F5` debug runs Launcher.py with the interpreter currently selected in the Python extension (if you want to debug with WinPython, use Ctrl+Shift+P Python:Select Interpreter).

## WinPython Notes
- Uses WinPython to allow standalone installation: https://github.com/winpython
- Supports multiple versions of WinPython.
- To switch WinPython versions, run `MSFS-PyScriptManager.exe --pick` (opens a menu to switch to other installed versions).
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
- It is recommended to use the full release with the bundled WinPython for maximum compatability, but this gives you other options if you prefer not to use that version.

## BYOP Python Version Compatibility
- Python 3.15 is currently not supported due to module incompatibilities.
- Recommended: Use Python 3.14 or earlier.

## Logging and Testing
- Logs are stored in the `Logs/` directory.
- Testing uses pytest, configured via `pyproject.toml`.
- Run tests from the console using the `test` command.

