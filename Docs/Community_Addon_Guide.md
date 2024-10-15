# Virtual Printer Community Toolbar Addon Guide

This document will explain how to install and use the optional community addon toolbar.  This toolbar will allow printouts from the "virtual_pos_printer" script to show in a MSFS toolbar for those in VR. 

Built in collaboration with chrisut - thank-you Chris for the assistance!

  <img src="https://github.com/user-attachments/assets/ab4973c7-11b2-48b4-bd11-053128d64856" alt="Description of image" width="300">

# Install Guide
- Please ensure that you have read the main readme.md and set everything up as shown for the "virtual_pos_printer" script.
- Run the toolbar installer by opening the script "msfs_toolbar_installer.py" in "/Scripts/Installer" using the launcher exe (MSFS-PyScriptManager.exe).
  
    <div style="display: flex;">
        <img src="https://github.com/user-attachments/assets/8001a4b0-e311-43d1-bec0-61f15ac1f147" alt="First image" width="200">
        <img src="https://github.com/user-attachments/assets/a877b0f6-c327-4b72-9f5f-8646a062b50e" alt="Second image" width="200">
    </div>

- If you prefer not to use the automated installer script (or have issues running it) you can manually copy the "chrisaut-toolbar-printouts" directory from /Data/Community_Install to your community addon on directory.

# Usage Guide
- It is critical that the "virtual_pos_printer" script remains running as this handles the communication between the virtual printer and the MSFS toolbar.
- Note that the toolbar **must** remain open for messages to be received.  You can minimize the toolbar so that it takes up less space while you are not using it.
- When a new print message appears it will play a sound, although again note that the toolbar must be open.
- Arrows on left/right will move through messages.  Trash-can will delete current message. + / - buttons will resize the text.

