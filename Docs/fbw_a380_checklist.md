# FBW A380 Checklist Controls (`fbw_a380_checklist.py`)

`fbw_a380_checklist.py` maps keyboard shortcuts to FBW A380 checklist controls while MSFS is the active window.

## Requirements
- Mobiflight WASM module installed.

## Key Bindings
- `Shift+Enter`: confirm checklist item.
- `Shift+Down`: move checklist down.
- `Shift+Up`: move checklist up.
- `Shift+Delete`: toggle checklist.

## How to Run
- Start `MSFS-PyScriptManager.exe`.
- Run `fbw_a380_checklist.py`.
- Keep the script running during flight.

## Notes
- Inputs are only sent when the active window title is `Microsoft Flight Simulator`.
- Script continuously writes on/off states to related LVAR controls.
