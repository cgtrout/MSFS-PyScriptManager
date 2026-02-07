# Virtual Printer Script (virtual_pos_printer.py)
This script intercepts print jobs and displays them as on-screen popups. It is primarily intended for use with the Fenix A32x but should work with any application that utilizes text-based printing.

## How to Run the Script
- Launch MSFS-PyScriptManager.exe.
- Click Run Script.
- Open virtual_pos_printer.py from the script directory.
- Follow the Setup Guide below:
## Setup Guide - Mandatory
 1. **Virtual Printer Creation:** When run, this will automatically create a "Fake" network Windows printer.
 2. **Configure the Printer**: Set the printer in the Fenix EFB settings to use the same printer name configured for this script (default: `"VirtualTextPrinter"`):

     ![ACARS Printer Setup](https://github.com/user-attachments/assets/13a472df-3aa1-4977-8001-cc7ec6170d92)
 3. **VR Community Addon (Optional):** Has an optional community toolbar addon for those in VR see: [Community Addon Guide](./Community_Addon_Guide.md)
 4. Note that this script **must** be running for the print functionality to work as it functions as a print server.
## How to test the Printer
- There is a script called "virtual_pos_TEST.py" that can be run to test the printer.  Run this in conjunction with the "virtual_pos_printer" script to test.  If everything is working correctly you should see popups with a test message every five seconds.  Close the test script to end the testing.

## Usage Guide
  - Notes can be dragged with left mouse click (hold).  Right-click to close a note.
  - Use Ctrl+MouseWheel up/down to resize a note (with mouse cursor on top of note).
  - Use **Ctrl+Shift+Alt+P** to define a new note spawn location (uses current mouse position).
  - If you have any issues with the automated printer installation see this guide: [Printer Troubleshooting Guide](https://github.com/cgtrout/MSFS-PyScriptManager/blob/main/Docs/Printer_Troubleshooting_Guide.md)
  - Click "Open Settings" to change settings for this script.

## Ports and Integration Notes
- The virtual printer listener binds to loopback `127.0.0.1:<printer_port>` (default `127.0.0.1:9102`)
- `printer_name` in `/Settings/settings.json` controls the printer name created/used by `virtual_pos_printer.py` (default: `VirtualTextPrinter`).
- `printer_port` in `/Settings/settings.json` controls the virtual printer TCP port and Windows printer port name (default: `9102`).
- `enable_popups` in `/Settings/settings.json` controls whether native Windows popup notes are shown.
- The port can be changed by using the "Open Settings" dialog. Restart to apply.
