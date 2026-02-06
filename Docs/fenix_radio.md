# Fenix Radio Panel (`fenix_radio.py`)

`fenix_radio.py` displays a draggable always-on-top panel with Fenix A32x RMP1 active/standby frequencies.

## Requirements
- Mobiflight WASM module installed.

## How to Run
- Start `MSFS-PyScriptManager.exe`.
- Run `fenix_radio.py`.
- Drag panel with left mouse.
- Resize text with mouse wheel.
- Right-click panel to close.

## Settings
- File: `Settings/fenix_radio.json`
- Stores:
  - font size
  - window position

## Notes
- Script reads Fenix-specific LVARs through Mobiflight.
- If font file is missing, script falls back to default font rendering.
