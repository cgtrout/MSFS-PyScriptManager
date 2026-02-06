# MSFS-PyScriptManager

**MSFS-PyScriptManager** is a launcher for running custom Python scripts for Microsoft Flight Simulator.
It uses a portable [WinPython](https://github.com/winpython) environment, so release ZIPs can be extracted and run without a separate Python install.

![image](https://github.com/user-attachments/assets/afea8bd1-8e31-434f-b655-908882052df9)

## Highlights
- No Python coding knowledge is required to run the included scripts.
- Multiple scripts can be run simultaneously and managed from one self contained interface.
- Script groups (`.script_group`) allow automation of loading multiple scripts (with startup autoplay support).
- Virtual printer + optional VR toolbar community addon support (and many other scripts)
- Out of the box ready to use for SimConnect automation ([Mobiflight WASM](#mobiflight-wasm-notes) needed for some scripts).

## Who Is This For?
This project is for MSFS simmers who want extra tooling around their sim -- such as overlays, automation, data visualization, print functionality, etc.

**You'll probably like this if you:**
- Fly Fenix or FBW aircraft and want things like virtual printouts, radio displays, or checklist hotkeys, although note that these provide the template for interacting with other planes (HubHop is a great resource for looking up sim variable info)?
- Want a draggable status bar with live SimConnect/SimBrief data?
- Want ready-to-use scripts out of the box?  See [Included Scripts](#included-scripts) and [Additional Scripts](#additional-scripts).
- Like the idea of Python scripting for MSFS but don't want to set up a dev environment?

**This probably isn't for you if you:**
- Already use FSUIPC, SPAD.neXt, or similar tools and they cover your needs.

## Table of Contents
- [MSFS-PyScriptManager](#msfs-pyscriptmanager)
  - [Highlights](#highlights)
  - [Who Is This For?](#who-is-this-for)
  - [Table of Contents](#table-of-contents)
  - [Download](#download)
  - [Installation](#installation)
  - [Launcher Quick Start](#launcher-quick-start)
  - [Included Scripts](#included-scripts)
    - [Virtual POS Printer (`virtual_pos_printer.py`)](#virtual-pos-printer-virtual_pos_printerpy)
    - [Custom Status Bar (`custom_status_bar.py`)](#custom-status-bar-custom_status_barpy)
  - [Additional Scripts](#additional-scripts)
  - [Mobiflight Required Scripts](#mobiflight-required-scripts)
  - [Mobiflight WASM Notes](#mobiflight-wasm-notes)
  - [Script Groups](#script-groups)
  - [Technical Notes](#technical-notes)
  - [Additional Credits](#additional-credits)

## Download
- [Releases](https://github.com/cgtrout/MSFS-PyScriptManager/releases/)

## Installation
- Download the latest release ZIP from the releases page.
- Extract to a location of your choice.
- Tip: use [7-Zip](https://www.7-zip.org/download.html) for much faster extraction of WinPython files.

## Launcher Quick Start
- Run `MSFS-PyScriptManager.exe`.
- Click **Run Script** to open a script.
- Each running script appears in its own tab.
- Right-click a tab header to close it.
- Full launcher usage guide: [Docs/Launcher_guide.md](Docs/Launcher_guide.md)

![image](https://github.com/user-attachments/assets/b8e12084-afad-4cd8-9b4c-2ea9cbb59ff1)

## Included Scripts
### Virtual POS Printer (`virtual_pos_printer.py`)
- Intercepts print jobs and shows popup printouts on screen.
- Intended primarily for Fenix A32x printing.
- Guide: [Docs/virtual_pos_printer.md](Docs/virtual_pos_printer.md)
- Printer troubleshooting: [Docs/Printer_Troubleshooting_Guide.md](Docs/Printer_Troubleshooting_Guide.md)
- Optional VR toolbar addon guide: [Docs/Community_Addon_Guide.md](Docs/Community_Addon_Guide.md)

![image](https://github.com/user-attachments/assets/5b0aac05-f1da-417e-a97b-be8261a4f1ba)

### Custom Status Bar (`custom_status_bar.py`)
- Draggable and customizable status bar with SimConnect + SimBrief data.
- Includes countdown timer modes and template customization.
- Guide: [Docs/custom_status_bar.md](Docs/custom_status_bar.md)

![image](https://github.com/user-attachments/assets/05786688-b542-4050-95eb-1e85bf8d673d)

## Additional Scripts
- `metar_load.py`: historical/real-time METAR lookup and printer output.
  - Guide: [Docs/metar_load.md](Docs/metar_load.md)
- `plot_altitude.py`: draggable real-time plot for altitude (or other SimVars) with CSV export.
  - Guide: [Docs/plot_altitude.md](Docs/plot_altitude.md)
- `plot_joystick.py`: joystick + trim visualization overlay.
  - Guide: [Docs/plot_joystick.md](Docs/plot_joystick.md)

## Mobiflight Required Scripts
> These scripts require the Mobiflight WASM module.

- `fbw_a380_checklist.py`: keyboard control for the FBW A380 checklist.
  - Guide: [Docs/fbw_a380_checklist.md](Docs/fbw_a380_checklist.md)
- `fenix_disable_efb.py`: hide Fenix EFBs.
  - Guide: [Docs/fenix_disable_efb.md](Docs/fenix_disable_efb.md)
- `fenix_radio.py`: draggable RMP1 radio display.
  - Guide: [Docs/fenix_radio.md](Docs/fenix_radio.md)
- `fenix_lights.py`: set cockpit lighting presets and optional joystick brightness binding.
  - Guide: [Docs/fenix_lights.md](Docs/fenix_lights.md)

## Mobiflight WASM Notes
- Required for scripts that use Fenix LVAR access.
- **If you use MobiFlight Connector**: install via `Extras > Microsoft Flight Simulator > Install WASM Module`.
- **Standalone module download**: https://github.com/MobiFlight/MobiFlight-WASM-Module/releases/

## Script Groups
- Script groups let you launch multiple scripts together.
- Save any group as `_autoplay.script_group` to auto-load it at launcher startup.

## Technical Notes
- See [Docs/Technical_Notes.md](Docs/Technical_Notes.md) for launcher internals, WinPython version switching, and Bring-Your-Own Python mode details.

## Additional Credits
- Launcher icon: [JoyPixels Emojione](https://github.com/joypixels/emojione) (MIT)
- Fonts: DIGITAL-7 v1.11 [Style-7](http://www.styleseven.com)
- Sound effect: "Receipt Printer 01" by thepodcastdoctor (Freesound), via Pixabay (CC0 / Pixabay Content License)
