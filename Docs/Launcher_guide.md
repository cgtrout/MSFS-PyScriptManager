# Launcher Guide
The launcher **MSFS-PyScriptManager** is used to load and execute Python scripts.

This guide explains how to use the MSFS-PyScriptManager launcher to load Python scripts, covering features like opening and closing scripts, managing script groups, using shortcuts, and leveraging the (optional) command-line interface.

![image](https://github.com/user-attachments/assets/b5d1a001-9dec-42aa-b8e3-03e78bd18ac4)

## How to Open or Close a Running Script
- Each loaded script will be run in a separate tab.
- Right-click a tab to close it.
- Click "Run Script" to load a script.
- Consult the main readme for more info on the scripts: [Main Readme](readme.md#Included Scripts)

![image](https://github.com/user-attachments/assets/b8e12084-afad-4cd8-9b4c-2ea9cbb59ff1)

## Script Groups
- **Script groups** give a way to automate loading multiple scripts at once.
- **Save Script Group**: will take the currently loaded scripts and save them to a script_group file.
- **Load Script Group**: loads all of the scripts contained in the script group file.
- **_autoplay.script_group**: this script group file will load at startup.

## Shortcuts
- **F5** : reload current tab (if a Script tab)
- **Ctrl+Tab** : cycle through open tabs
- **Ctrl+~** : opens command line (see below)

## Command Line Tab

The "command line" can be opened in various ways:
- Click "command line" button.
- Use **ctrl+~** keyboard shortcut.

![image](https://github.com/user-attachments/assets/694e3461-d538-4adc-8aee-20deafc3adc1)

This will open a shell window which is connected to a CMD.exe instance - this means you can run command line commands directly from this tab.  This is given scope to WinPython directory meaning that commands such as PIP can be run from this console tab. Starting directory is /Scripts.

It also will 'intercept' the following custom commands:
- **python/py**: running these will open a script directly in MSFS-PyScriptManager
- **switch/s**: will select a tab that is running given script such

Note that it will autocomplete on file names by pressing "tab" on the keyboard.  Pressing tab multiple times will cycle through possible matches.

The main intention of this was to give a more keyboard focused way to interact with MSFS-PyScriptManager but will give easy access to commands such as PIP if you need to run them.


