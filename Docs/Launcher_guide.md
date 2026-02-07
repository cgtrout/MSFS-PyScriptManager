# Launcher Guide
The launcher **MSFS-PyScriptManager** is used to load and execute Python scripts.

This guide covers script tabs, script groups, keyboard shortcuts, and the optional command-line tab.

![image](https://github.com/user-attachments/assets/b5d1a001-9dec-42aa-b8e3-03e78bd18ac4)

## Open and Close Scripts
- Each loaded script runs in its own tab.
- Click **Run Script** to load a script.
- Right-click a tab header to close that tab.
- Press **Ctrl+W** to close the active tab.
- See [Main Readme](../readme.md) for script overviews.

![image](https://github.com/user-attachments/assets/b8e12084-afad-4cd8-9b4c-2ea9cbb59ff1)

## Script Groups
- **Save Script Group** saves currently running script tabs to a `.script_group` file.
- **Load Script Group** loads scripts from a `.script_group` file.
- A file named `_autoplay.script_group` in `/Scripts` auto-loads at launcher startup.

## Shortcuts
- **F5**: restart the active script tab.
- **Ctrl+Tab**: cycle through open tabs.
- **Ctrl+`**: open or focus the command-line tab.
- **Ctrl+W**: close the active tab.

## Command Line Tab
Open the command line by either:
- Clicking the **Command Line** button.
- Pressing **Ctrl+`**.

![image](https://github.com/user-attachments/assets/694e3461-d538-4adc-8aee-20deafc3adc1)

The command line runs a persistent `cmd.exe` session rooted to the project script environment, so commands like `pip` are available from this tab. The initial directory is `/Scripts`.

The launcher also intercepts these custom commands:
- `help`: display available commands and usage information.
- `python` / `py <script.py>`: open a script in a new launcher script tab.
- `switch` / `s <script.py>`: focus an already-running script tab by script name.
- `reload`: restart all running script tabs.
- `test`: run the pytest test suite.

Autocomplete:
- Press **Tab** to autocomplete file names.
- Press **Tab** repeatedly to cycle possible matches.


