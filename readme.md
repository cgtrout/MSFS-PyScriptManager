# MSFS-PyScriptManager

**MSFS-PyScriptManager** is a tool designed for managing and executing custom Python scripts tailored for Microsoft Flight Simulator (MSFS). This tool leverages the **WinPython** portable Python environment for ease of installation.  Simply download the release and extract it - no further installation required to run scripts!

# Installation Instructions
- Download zip from releases
- Extract to location of your convenience
- Launch MSFS-PyScriptManager.exe
- Click "Select and Run Script" button to open a script. Scripts are shown in individual tabs.  Right click the tab header to close a script. 

# Scripts Included
- virtual_pos_printer.py: Allows print jobs from the Fenix A32x to show as popups on the screen.
![image](https://github.com/user-attachments/assets/5b0aac05-f1da-417e-a97b-be8261a4f1ba)
  - Notes can be dragged with left mouse click.  Right-click to close note.
  - Use Ctrl+MouseWheel up/down to resize the note.
  
  - Set the virtual printer in the Fenix EFB settings to use the "VirtualTextPrinter" created by the script.
  ![image](https://github.com/user-attachments/assets/13a472df-3aa1-4977-8001-cc7ec6170d92)
 
- get_sim_time.py: Shows a draggable status bar that shows the real world zulu time and sim zulu time.  Double-click to program the count-down timer.

  ![image](https://github.com/user-attachments/assets/be003852-16e7-493b-907d-fcba4e586893)
- msfs-turn-off-fenix-efb: Example script that shows how LVARS can be automated.  This script will hide the EFBs.  This script requires a mobiflight installation.
  
# Technical Notes
- The provided launcher exe is provided for ease of use.  It is also possible to launch the script "/Launcher/Launcher.py" from "WinPython/WinPython Command Prompt.exe" if you prefer to not launch from the EXE.  The exe can be built by launching "Build.bat" in "\Launcher\LauncherApp" as the "TCC" C-Compiler is included.
- You can easily create your own scripts and run them as well.  Note that if you need to add any libraries use the "WinPython/WinPython Command Prompt.exe" and run the "pip" command to add a lib.
