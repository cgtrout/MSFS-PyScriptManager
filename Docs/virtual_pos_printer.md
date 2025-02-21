# Virtual Printer Script (virtual_pos_printer.py)
This script intercepts print jobs and displays them as on-screen popups. It is primarily intended for use with the Fenix A32x but should work with any application that utilizes text-based printing.

## How to Run the Script
- Launch MSFS-PyScriptManager.exe.
- Click Run Script.
- Open virtual_pos_printer.py from the script directory.
- Follow the Setup Guide below:
## Setup Guide - Mandatory
 1. **Virtual Printer Creation:** When run, this will automatically create a "Fake" network Windows printer called "VirtualTextPrinter".
 2. **Configure the Printer**: Set the printer in the Fenix EFB settings to use the "VirtualTextPrinter" created by the script:

     ![ACARS Printer Setup](https://github.com/user-attachments/assets/13a472df-3aa1-4977-8001-cc7ec6170d92)
 3. **VR Community Addon (Optional):** Has an optional community toolbar addon for those in VR see: [Community Addon Guide](./Docs/Community_Addon_Guide.md)
 4. Note that this script **must** be running for the print functionality to work as it functions as a print server.
## How to test the Printer
- There is a script called "virtual_pos_TEST.py" that can be run to test the printer.  Run this in conjunction with the "virtual_pos_printer" script to test.  If everything is working correctly you should see popups with a test message every five seconds.  Close the test script to end the testing.

## Usage Guide
  - Notes can be dragged with left mouse click (hold).  Right-click to close a note.
  - Use Ctrl+MouseWheel up/down to resize a note (with mouse cursor on top of note).
  - Use Ctrl+Shift+P shortcut to define a new note spawning location (it will use the current mouse position).
  - If you have any issues with the automated printer installation see this guide: [Printer Troubleshooting Guide](https://github.com/cgtrout/MSFS-PyScriptManager/blob/main/Docs/Printer_Troubleshooting_Guide.md)
