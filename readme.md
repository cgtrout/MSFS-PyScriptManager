**MSFS-PyScriptManager** is a tool designed for managing and executing custom Python scripts tailored for Microsoft Flight Simulator (MSFS). This tool leverages the [WinPython](https://github.com/winpython) portable Python environment for ease of installation.  Simply download the release and extract it - no further installation required to run scripts!  Comes with some useful scripts, such as "virtual_pos_printer.py" that can print popup notes on the screen from the Fenix A32x printer.

# MSFS 2024 Update
 - All scripts should still work with MSFS 2024, but if you notice any issues with any of the scripts let me know.
 - The community addon for the print-out toolbar works with no modifications for 2024 - the installation script has been updated for the automated installation although note that it hasn't been tested for those with a Microsoft store installation.

# Download
- [Download MSFS-PyScriptManager(Release Page)](https://github.com/cgtrout/MSFS-PyScriptManager/releases/)
- [Virus Total Malware Check](https://www.virustotal.com/gui/url/9f2aab0754a63dc92903b3c99db9cf5dde639241368af9c33f51053997d20333?nocache=1)

# Installation Instructions
- Download the zip file from the newest release (Releases).
- Extract the downloaded zip to a location of your choice. I recommend using a fast unzip tool such as [7-zip](https://www.7-zip.org/download.html) as the default Windows unzip tool is very slow at extracting the WinPython directory.
- Feel free to post an 'issue' here on Github if you have any issues with the launcher or the scripts.

# How to use the Launcher
- Run MSFS-PyScriptManager.exe - this will open the python script manager/launcher.
- Click the "Run Script" button to open a script. Running scripts are each shown in their own individual tabs.
- Right click the tab header for a given script to close it.
- Further details on the provided scripts are included further down.
![image](https://github.com/user-attachments/assets/b8e12084-afad-4cd8-9b4c-2ea9cbb59ff1)

# Included Scripts
- **virtual_pos_printer.py:** Allows print jobs from the Fenix A32x to show as popup 'notes' on the screen.
   - [Virtual Printer Guide](Docs/virtual_pos_printer.md) - please read this guide on how to use
    
    ![image](https://github.com/user-attachments/assets/5b0aac05-f1da-417e-a97b-be8261a4f1ba)
  
- **custom_status_bar.py:** Shows a draggable status bar that shows the real world zulu time and sim zulu time, along with a countdown timer.  Double-click to program the count-down timer.
  - [Custom Status Bar Guide](Docs/custom_status_bar.md) - please read the guide for more information on how to use this script

   ![image](https://github.com/user-attachments/assets/05786688-b542-4050-95eb-1e85bf8d673d)

- **fbw_a380_checklist.py** Allows keyboard control of built in A380 checklist.  This script requires a [Mobiflight "WASM" module installation](https://github.com/MobiFlight/MobiFlight-Connector/wiki/Verifying-the-WASM-module-installation-and-locating-the-MSFS2020-community-folder).
- **fenix_disable_efb.py:** Example script that shows how LVARS can be automated.  This script will hide the EFBs on the Fenix A32x. (Requires Mobiflight "WASM" module installation).
- **fenix_radio.py:** Shows a draggable radio panel that shows RMP1 active/standby channels. (Requires Mobiflight "WASM" module installation).
- **plot_altitude.py:** Shows a draggable graph panel of altitude - can easily be changed to other SimConnect variables.
- **plot_joystick.py:** Show visualization of joystick and trim values state.

# Script Groups
- "Script Groups" can be used to automate loading groups of scripts at once.
- Save your script group as "_autoplay.script_group" to automate loading your script group at startup.

# Technical Notes
- The launcher exe is provided for ease of use.  It is also possible to launch the script "/Launcher/Launcher.py" from "WinPython/WinPython Command Prompt.exe" if you prefer to not launch from the EXE.  The exe can be built by launching "Build.bat" in "\Launcher\LauncherApp" as the "TCC" C-Compiler is included(https://bellard.org/tcc/).
- You can easily create your own scripts and run them as well.  Note that if you need to add any libraries use the "WinPython/WinPython Command Prompt.exe" and run the "pip" command from here to add a library to the WinPython directory.
- I recommend using [Visual Studio Code](https://code.visualstudio.com/download) for editing the scripts.  The built in "Edit" button will open the selected script in VS Code if it is installed.
- Uses WinPython to allow standalone installation - https://github.com/winpython
