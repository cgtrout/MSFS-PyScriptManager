# MSFS-PyScriptManager v1.10 Release Notes - Major Update



## Table of Contents
- [Script Changes](#script-changes)
  - [Custom Status Bar (`custom_status_bar.py`) Enhancements](#custom-status-bar---major-enhancements-custom_status_barpy)
- [New Scripts Added](#new-scripts-added)
  - [Metar Load (`metar_load.py`)](#metar-load-script-metar_loadpy)
  - [Joystick Visualization (`plot_joystick.py`)](#plot-joystick-visualization-plot_joystickpy)
- [New MobiFlight Scripts](#mobiflight-scripts)
  - [FBW A380 Checklist (`fbw_a380_checklist.py`)](#fbw-a380-checklist-fbw_a380_checklistpy)
  - [Fenix Lights (`fenix_lights.py`)](#fenix-lights-fenix_lightspy)
  - [Fenix Radio (`fenix_radio.py`)](#fenix-radio-fenix_radiopy)
- [Launcher New Features](#launcher-new-features)

## Script Changes

### Custom Status Bar - Major Enhancements (custom_status_bar.py)

- **Much more customizable than before!**
  - On the first run, a new template file is created `/status_bar_template.py`.  This is a Python file that will be loaded that can be used to extensively change the appearance and behavior of the status bar.
  - For example: now in the template with some minor changes you can use [@leftos](https://github.com/leftos) idea to have the timer show a countdown from the EOBT (Est Off-Block_time) to show if you are ahead or behind schedule before engines are on.
  - Added new template functions `VARIF` / `##` dynamic templates - thanks @leftos for idea/implementation.
- See the documentation for more details: [Custom Status Bar Documentation](Docs/custom_status_bar.md)

# New Scripts Added:
### metar_load.py
- Load either a real time metar or a historical metar based on simulator date/time.

### plot_joystick.py
- Shows a draggable joystick visualization.
- Shows axis and trim values state.
- Trim dynamically set to either helicopter or plane trims.

# New MobiFlight Scripts
> ⚠️ **Important** - 
> The following new scripts require a MobiFlight WASM module installation: See [Notes on Mobiflight Integration](README.md#notes-on-mobiflight-integration). ⚠️

### fenix_lights.py (Requires MobiFlight WASM Community Module)
- Initializes flight deck lighting to preassigned values.
- This will also work around the full bright MSFS 2024 lighting bug (all lights are toggled on/off).
- At start up it will give option to assign a joystick axis to control the screen lighting with one axis.
- Also will take left most screen brightness knob and propogate its brightness value to all screens.

### fenix_radio.py (Requires MobiFlight WASM Community Module)
- Shows a draggable overlay panel that shows radio channel state (RMP1)
- Intended for those with a hardware controller that does not display values.

### fbw_a380_checklist.py (Requires MobiFlight WASM Community Module)
- Allows keyboard control of built in FBW A380 Checklist system.
- **Key Bindings:**
    - `CONFIRM`= "shift+enter"
    - `DOWN` = "shift+down"
    - `UP` = "shift+up"
    - `TOGGLE` = "shift+delete"

## Launcher (MSFS-PyScriptManager) New Features
- Settings Changer: for certain scripts a "Open Settings" button is added to open an integrated save file editor.
- Autoclose: even if MSFS-PyScriptManager is forced closed, it will properly shutdown all running Python processes - this allows full launch/shutdown automation with tools such as MSFS Addons Linker (https://flightsim.to/file/1572/msfs-addons-linker).
- Input Support: can now run scripts that use keyboard input.
- Integrated console(shell): This allows console commands to be run in the launcher directly.
- Dark Mode Support: On Win11 support dark mode of titlebars.
- Added "Restart All" button: to easily relaunch all running scripts.
- Added "Stop" button: stop an individual script.
- Color print() support (ANSI).
- Tab Drag/Drop.
- Performance Metrics Tab: Shows performance stats on running scripts.

## Credits
I want to extend a huge thank-you to [@leftos](https://github.com/leftos) for the invaluable feedback, insightful issue reports, and meaningful contributions to the project. Your support, along with the submitted PRs, has been incredibly helpful!


