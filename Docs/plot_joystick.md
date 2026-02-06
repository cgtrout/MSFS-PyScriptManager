# Joystick Plot (`plot_joystick.py`)

`plot_joystick.py` shows a draggable transparent joystick overlay and trim indicators.

## What It Does
- Displays live joystick X/Y movement.
- Displays trim lines for fixed-wing or helicopter trim values.
- Supports right-click joystick selection menu.
- Persists selected joystick and window position.

## How to Run
- Start `MSFS-PyScriptManager.exe`.
- Run `plot_joystick.py`.
- Right-click the overlay to choose joystick.
- Drag to reposition.

## Settings
- File: `Settings/plot_joystick.json`
- Stored values include:
  - selected joystick name
  - window position

## Notes
- Uses SimConnect for trim values.
- If no joystick is selected/found, overlay remains active and prompts selection.
