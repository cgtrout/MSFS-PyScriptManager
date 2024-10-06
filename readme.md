# MSFS-PyScriptManager

**MSFS-PyScriptManager** is a tool designed for managing and executing custom Python scripts tailored for Microsoft Flight Simulator (MSFS). This tool leverages the **WinPython** portable Python environment for ease of installation.  Simply download the release and extract it - no further installation required to run scripts!  Comes with some useful scripts, such as "virtual_pos_printer.py" that can print popup notes on the screen from the Fenix A32x printer.

# NEW {TODO: date} - POS printer functionality can now be sent optionally to MSFS to show up as a toolbar window. SEE (TODO PROVIDE LINK? )
  - Many thanks to {TODO: appropriate credits for this}

# Download
- [Download MSFS-PyScriptManager(Release Page)](https://github.com/cgtrout/MSFS-PyScriptManager/releases/)
- [Virus Check]({TODO: NEW LINK})
  
# Installation Instructions
- Download the zip file from the newest release (Releases).
- Extract the downloaded file to a location of your choice.
- Launch MSFS-PyScriptManager.exe.
- Click the "Run Script" button to open a script. Running scripts are each shown in their own individual tabs.  Right click the tab header for a given script to close it.
- Further details on the provided scripts are included further down.
- Feel free to post an 'issue' here on Github if you have any issues with the launcher or the scripts.

# Scripts Included
- virtual_pos_printer.py: Allows print jobs from the Fenix A32x to show as popup 'notes' on the screen.
![image](https://github.com/user-attachments/assets/5b0aac05-f1da-417e-a97b-be8261a4f1ba)
  - This will automatically create a "Fake" network Windows printer called "VirtualTextPrinter".
  - Set the printer in the Fenix EFB settings to use the "VirtualTextPrinter" created by the script.
  - {TODO: CONSIDER FULL SPLIT OFF TUTORIAL?}
  ![image](https://github.com/user-attachments/assets/13a472df-3aa1-4977-8001-cc7ec6170d92)
  - Note that this script **must** be running for the print functionality to work as it functions as a print server.
  - There is a script called "virtual_pos_TEST.py" that can be run to test the printer.  If everything is working correctly you should see popups with a test message every five seconds.
  - Notes can be dragged with left mouse click (hold).  Right-click to close a note.
  - Use Ctrl+MouseWheel up/down to resize a note (with mouse cursor on top of note).
  - Use Ctrl+Shift+P shortcut to define a new note spawning location (it will use the current mouse position).
- custom_status_bar.py: Shows a draggable status bar that shows the real world zulu time and sim zulu time.  Double-click to program the count-down timer.
  - Previously called "get_sim_time"
  - Now uses more easily modifiable 'template' system to define variables that show on the bar to make it easier to modify.  See source file for more details.
  ![image](https://github.com/user-attachments/assets/be003852-16e7-493b-907d-fcba4e586893)
- msfs-turn-off-fenix-efb: Example script that shows how LVARS can be automated.  This script will hide the EFBs on the Fenix A32x.  This script requires a mobiflight installation.
  
# Technical Notes
- The launcher exe is provided for ease of use.  It is also possible to launch the script "/Launcher/Launcher.py" from "WinPython/WinPython Command Prompt.exe" if you prefer to not launch from the EXE.  The exe can be built by launching "Build.bat" in "\Launcher\LauncherApp" as the "TCC" C-Compiler is included.
- You can easily create your own scripts and run them as well.  Note that if you need to add any libraries use the "WinPython/WinPython Command Prompt.exe" and run the "pip" command from here to add a library to the WinPython directory.
