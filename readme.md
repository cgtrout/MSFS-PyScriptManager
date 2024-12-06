**MSFS-PyScriptManager** is a tool designed for managing and executing custom Python scripts tailored for Microsoft Flight Simulator (MSFS). This tool leverages the [WinPython](https://github.com/winpython) portable Python environment for ease of installation.  Simply download the release and extract it - no further installation required to run scripts!  Comes with some useful scripts, such as "virtual_pos_printer.py" that can print popup notes on the screen from the Fenix A32x printer.

# MSFS 2024 Update
 - Note: at moment the Mobiflight functionality of some scripts may not be working correctly (such as fenix_disable_efb.py).  As of yet the Python library has not been updated for MSFS 2024.
 - custom_status_bar.py - works as expected except that MSFS 2024 currently does not report the sim time correctly meaning that the sim time reported on the panel is incorrect. (it reports sim time as real world time).  I believe this has been marked as a bug and should eventually be fixed by Asobo.
 - The other scripts should all still work the same as before.
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

  <img src="https://github.com/user-attachments/assets/6dbde597-67e0-453b-8478-b096e44edd1d" alt="Description of image" width="500">

# Included Scripts
- **virtual_pos_printer.py:** Allows print jobs from the Fenix A32x to show as popup 'notes' on the screen.
![image](https://github.com/user-attachments/assets/5b0aac05-f1da-417e-a97b-be8261a4f1ba)
  - This will automatically create a "Fake" network Windows printer called "VirtualTextPrinter".
  - Set the printer in the Fenix EFB settings to use the "VirtualTextPrinter" created by the script.
  
     ![image](https://github.com/user-attachments/assets/13a472df-3aa1-4977-8001-cc7ec6170d92)
  - Has an optional community toolbar addon for those in VR see: [Community Addon Guide](https://github.com/cgtrout/MSFS-PyScriptManager/blob/main/Docs/Community_Addon_Guide.md)
  - Note that this script **must** be running for the print functionality to work as it functions as a print server.
  - There is a script called "virtual_pos_TEST.py" that can be run to test the printer.  Run this in conjunction with the "virtual_pos_printer" script to test.  If everything is working correctly you should see popups with a test message every five seconds.  Close the test script to end the testing.
  - Notes can be dragged with left mouse click (hold).  Right-click to close a note.
  - Use Ctrl+MouseWheel up/down to resize a note (with mouse cursor on top of note).
  - Use Ctrl+Shift+P shortcut to define a new note spawning location (it will use the current mouse position).
  - If you have any issues with the automated printer installation see this guide: [Printer Troubleshooting Guide](https://github.com/cgtrout/MSFS-PyScriptManager/blob/main/Docs/Printer_Troubleshooting_Guide.md)

- **custom_status_bar.py:** Shows a draggable status bar that shows the real world zulu time and sim zulu time, along with a countdown timer.  Double-click to program the count-down timer.
  - NEW: If 'SIMBRIEF_USERNAME' is set, it will look up the time for this flight to automatically set the countdown timer (thanks @leftos for this idea/initial implementation).
  - Uses an easily modifiable 'template' system to define variables that show on the bar.  See source file for more details.
  ![image](https://github.com/user-attachments/assets/05786688-b542-4050-95eb-1e85bf8d673d) 

- **fbw_a380_checklist.py** Allows keyboard control of built in A380 checklist.
- **fenix_disable_efb.py:** Example script that shows how LVARS can be automated.  This script will hide the EFBs on the Fenix A32x.  This script requires a Mobiflight "Wasm" module installation.
- **fenix_radio.py:** Shows a draggable radio panel that shows RMP1 active/standby channels.
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
