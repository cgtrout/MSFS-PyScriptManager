# Release Notes (1.20)

## Download Notes
Two separate versions are now provided:

- **MSFS-PyScriptManager_1.20.zip** (WinPython version)
  - Standard release. Contains everything required to run MSFS-PyScriptLauncher
  - No system Python installation required
  - Simply extract to run this.

- **MSFS-PyScriptManager_1.20_byop.zip** (Bring-Your-Own-Python)
  - Doesn't include WinPython: will use whatever is on system path
  - Runs automated pip to install any missing dependencies . (Will ask for permission first)
  - NOTE: Python 3.15 currently doesn't work due to module incompatabilities with 3.15

---

## New Features & Improvements

### Launcher & Interface

#### Script Picker
- Better file browser interface (switched to `tkfilebrowser`)
- Shows per-script descriptions using metadata

#### Console
- Added `help` command
- Shortcut always opens same instance (no duplicates)
- Fixed Control-Tab behavior
- Cleaner output and improved startup guidance

#### Input Handling
- Complete rewrite to fix interactive scripts
  - User input now properly buffered
  - Backspace and editing work correctly
  - Mouse selection works properly

#### Other Improvements
- **Markdown viewer**: Switched to `tkinterweb` for better performance and reliability
- **Testing**: Added `test` command to run pytest suite from console

## Script Changes

### plot_joystick
- Added rudder indicator with configurable bindings (drawn horizontally at top)
- Added optional value display toggle (via right-click menu)
- Added support for rotorcraft trim indicator (`ROTOR_LATERAL_TRIM_PCT`)

### virtual_pos_printer
- Configure printer name and port directly in settings
- Added scrolling support for large print jobs

### fbw_a380
- Added input debounce to prevent multiple activations from single press

### Core Improvements
- **All scripts**: Improved sim state detection (knows when in menu vs. in-flight)
- **All scripts**: Better reliability when connecting to flight simulator
- **Included resources**: GitHub users now get `chrisaut-toolbar-printouts` built-in

---

## Bug Fixes

### virtual_pos_printer
- Fixed Windows firewall prompt being triggered

### metar_load
- Fixed loading weather data from NOAA service
- METAR window now reliably comes to focus when opened

### custom_status_bar
- Improved simulator detection using new shared library

### Launcher
- **Error handling**: Window no longer closes when errors occur (keeps error message visible)
- **Process management**: Fixed output corruption under heavy load; more reliable shutdown
- **Process startup**: Fixed libraries loading before dependencies were ready
- **Logging**: Fixed NUL characters appearing in shutdown logs

---

## Behind the Scenes

### Launcher Architecture
- Refactored `launcher.py` into modular app package
- Added type hints throughout launcher code
- Simplified process tracking and stdout/stderr handling
- Added script arguments support

### Process Management & Robustness
- Fixed EOF handling in pipe readers
- Added incremental UTF-8 decoder for robust text handling
- Implemented back-pressure handling to prevent dropped output under heavy load
- Fixed stdin-writer thread cleanup on shutdown
- Added termination polling for reliable process monitoring
- Improved AutoRestart behavior
- Added deterministic pipe stress tests

### Shared Libraries & Infrastructure
- **sim_state.py**: New library to detect simulator state (menu vs. in-flight)
  - Uses CAMERA STATE via raw SimConnect DLL
  - Distinguishes between cockpit, external, drone, loading, and menu states
- **connection_helpers.py**: Standardized connection interface for all scripts
  - `SimConnectConnectionHelper`: For direct SimConnect access
  - `MobiFlightConnectionHelper`: For MobiFlight WASM access
  - Both support automatic sim state detection and connection timing
- **mobiflight_connection.py**: Updated to use helper pattern
  - Fixed `None` handling in `set_and_verify_lvar`
- **window_focus.py**: Low-level Windows API to reliably force window focus

### Python Compatibility
- Python 3.14 support now supported
- Requirements.txt file added to automate loading of required modules (if not present)
- Added BYO-Python fallback when WinPython not found
  - Searches PATH for python.exe/pythonw.exe
  - Clearer error messages and instructions
- Improved WinPython selection prompts (Y/N when only one found)
- Added command-line argument to select specific WinPython instance

### Testing & Quality Assurance
- Centralized all testing on pytest
- Created `pyproject.toml` for test configuration
- Added console `test` command to run full suite
- Added `import_checker.py` tool to validate package requirements
- Added pipe reliability stress tests

### Quality of Life
- Logs moved to dedicated `Logs/` directory
- Autostart groups file auto-created if missing
- New version detection / recommendation.

### Packaging & Resources
- Linked `chrisaut-toolbar-printouts` as git submodule
- More files included for GitHub users
