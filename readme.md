**MSFS-PyScriptManager** is a tool designed for running custom Python scripts tailored for Microsoft Flight Simulator (MSFS). This tool leverages the [WinPython](https://github.com/winpython) portable Python environment for an easy installation.  Simply download the release and extract it — no further installation is required to run the included scripts!

![image](https://github.com/user-attachments/assets/afea8bd1-8e31-434f-b655-908882052df9)


**Comes with several useful scripts, such as:**
- [virtual_pos_printer.py](#virtual-pos-printer-for-fenix-a32x---virtual_pos_printerpy)- displays print jobs as popups on the screen from the Fenix A32x printer.
- [custom_status_bar.py](#custom-status-bar---custom_status_barpy)- shows a status bar that can dynamically pull information from the sim and Simbrief.
- [fenix_lights.py](Docs/fenix_lights.md) - pre-configures flight deck lighting in A32x and optionally binds joystick axis to screen brightness.

**No Python programming knowledge is required** to run the included scripts!

# Table of Contents
- [Download](#download)
- [Installation Instructions](#installation-instructions)
- [How to Use the Launcher](#how-to-use-the-launcher)
- [Included Scripts - Showcase](#included-scripts---showcase)
  - [Virtual Pos Printer for Fenix A32x (`virtual_pos_printer.py`)](#virtual-pos-printer-for-fenix-a32x---virtual_pos_printerpy)
  - [Custom Status Bar (`custom_status_bar.py`)](#custom-status-bar---custom_status_barpy)
- [More Scripts](#more-scripts)
  - [Historical METAR Loader (`metar_load.py`)](#more-scripts)
  - [Altitude Plotter (`plot_altitude.py`)](#more-scripts)
  - [Joystick & Trim Visualizer (`plot_joystick.py`)](#more-scripts)
- [Notes on Mobiflight Integration](#notes-on-mobiflight-integration)
- [More Scripts - Mobiflight Required](#More-Scripts---Mobiflight-Required)
  - [FBW A380 Checklist (`fbw_a380_checklist.py`)](#More-Scripts---Mobiflight-Required)
  - [Fenix Disable EFB (`fenix_disable_efb.py`)](#More-Scripts---Mobiflight-Required)
  - [Fenix Radio Panel (`fenix_radio.py`)](#More-Scripts---Mobiflight-Required)
  - [Fenix Lights (`fenix_lights.py`)](#More-Scripts---Mobiflight-Required)
- [Note On Included Script Behavior](#note-on-included-script-behavior)
- [MSFS 2024 Update](#msfs-2024-update)
- [Script Groups](#script-groups)
- [Technical Notes](#technical-notes)
- [Additional Credits](#additional-credits)

# Download
- [Download MSFS-PyScriptManager(Release Page)](https://github.com/cgtrout/MSFS-PyScriptManager/releases/)
- [Virus Total Malware Check](https://www.virustotal.com/gui/url/68f6f554bab721ca62f3fe49416ad7ee02d4aedc524904a61062eb73b54490ce)

# Installation Instructions
- Download the ZIP file from the newest release (Releases).
- Extract the downloaded ZIP file to a location of your choice. Tip: Use a fast unzip tool such as [7-zip](https://www.7-zip.org/download.html) as the default Windows ZIP extraction tool is very slow at extracting the WinPython directory.
- Feel free to post an 'issue' here on Github if you have any issues with the launcher or the scripts.

# How to use the Launcher
- Run `MSFS-PyScriptManager.exe` - this will open the python script manager/launcher.
- Click the "Run Script" button to open a script. Running scripts are each shown in their own individual tabs.
- Right click the tab header for a given script to close it.
- Further details on the provided scripts are included further down.
- For more information on how to use the Launcher see: [Launcher Guide](Docs/Launcher_guide.md)
![image](https://github.com/user-attachments/assets/b8e12084-afad-4cd8-9b4c-2ea9cbb59ff1)

# Included Scripts - Showcase
## **Virtual Pos Printer for Fenix A32x - virtual_pos_printer.py:**
   - Allows print jobs from the Fenix A32x to show as popup 'notes' on the screen.
   - [Virtual Printer Guide](Docs/virtual_pos_printer.md) - please read this guide for further instructions on how to use.

   ![image](https://github.com/user-attachments/assets/5b0aac05-f1da-417e-a97b-be8261a4f1ba)

## Custom Status Bar - custom_status_bar.py:
  - Shows a customizable draggable status bar that shows the real world zulu time and sim zulu time, along with a countdown timer (that can also fetch times from Simbrief).
  - [Custom Status Bar Guide](Docs/custom_status_bar.md) - please read the guide for more information on how to use this script.

   ![image](https://github.com/user-attachments/assets/05786688-b542-4050-95eb-1e85bf8d673d)

## More Scripts
- **metar_load.py:** Load a historical metar based on Simulator or real world time - can print to virtual_pos_printer.
- **plot_altitude.py:** Shows a draggable graph panel of altitude - can easily be changed to other SimConnect variables.  Can also export recorded data as CSV.
- **plot_joystick.py:** Show visualization of joystick and trim values state. Will either show heli or plane trims dynamically.

## Notes on MobiFlight Integration
> ⚠️ Several of the scripts listed below require the Mobiflight WASM module.  ⚠️
- This module is required to facilitate communication between the scripts and MSFS for those that need to access LVARS (for Fenix).
- This WASM module can be downloaded here: https://github.com/MobiFlight/MobiFlight-WASM-Module/releases/tag/1.0.1.  Download the ZIP and extract to your community folder.  Alternatively, if you have MobiFlight Connector installed, you can install this module with the top menu command (Extras > Microsoft Flight Simulator > Install WASM Module)

## More Scripts - Mobiflight Required
**Note:** most of these will wait until ground power is enabled before the logic is triggered.
- **fbw_a380_checklist.py** Allows keyboard control of built in A380 checklist.
- **fenix_disable_efb.py:** Hides the EFBs on the Fenix A32x when run.
- **fenix_radio.py:** Shows a draggable radio panel that shows A32x RMP1 active/standby channels.
- **fenix_lights.py:** Preassign flight deck lighting knob values.  Also allows one knob to control all screen brightness or to optionally bind a joystick axis to control screen lighting. This will also reset all of the lights to get around the MSFS 2024 'full bright' lighting bug. For more info see the documentation for this: [Docs/fenix_lights](Docs/fenix_lights.md).


# Note On Included Script Behavior
Currently, **most of the included scripts will detect Simulator state**.  However, in certain scenarios, such as starting a new flight (second+ flight of the session) you may need to restart some/all of the scripts.  Please use the following method:
- Click "Restart All" in `MSFS-PyScriptManager.exe` after your aircraft has fully loaded in MSFS.


# MSFS 2024 Update
 - All scripts should work with MSFS 2024, but please report any issues.
 - The community addon for the print-out toolbar works without modifications in MSFS 2024. The installation script has been updated for automated installation; however, it has not been tested with the Microsoft Store version.

# Script Groups
- "Script Groups" can be used to automate loading groups of scripts at once.
- Save your script group as `_autoplay.script_group` to automate loading your script group at startup.

# Technical Notes
- The launcher EXE is provided for convenience, but you can also launch the script manually.  It is also possible to launch the script "/Launcher/Launcher.py" from "WinPython/WinPython Command Prompt.exe" if you prefer to not launch from the EXE.  The exe can be built by launching "Build.bat" in "\Launcher\LauncherApp" as the "TCC" C-Compiler is included(https://bellard.org/tcc/).
- You can easily create your own scripts and run them as well.  Note that if you need to add any libraries use the "WinPython/WinPython Command Prompt.exe" and run the "pip" command from here to add a library to the WinPython directory.
- I recommend using [Visual Studio Code](https://code.visualstudio.com/download) for editing the scripts.  The built in "Edit" button will open the selected script in VS Code if it is installed.
- Uses WinPython to allow standalone installation - https://github.com/winpython

## Additional Credits
- Icon used for Launcher: [JoyPixels Emojione](https://github.com/joypixels/emojione) (MIT License)

