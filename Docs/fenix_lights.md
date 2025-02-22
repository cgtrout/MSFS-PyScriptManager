# Fenix Lights Script (fenix_lights.py)

This script accomplishes several tasks:
- Sets all cockpit lights in the FenixA32x to preset values.  This also by extension corrects the 'full bright' MSFS 2024 bug.
- Binds all screen brightess knobs to left most knob (PFD Brightness).
- (Optionally) Binds all brightness knobs to joystick axis.

![image](https://github.com/user-attachments/assets/7cc9c920-e624-43b1-b5a3-56794bb2a8b4)
All screen brightness knobs are bound to left-most screen brightness knob.

## How To Use
- On first run it will present a prompt.  If you wish to bind a joystick axis, type 'y' and hit enter to bind.  Follow the subsequent prompts to select a joystick and axis. **Enter 'n' if you do not want to bind a joystick axis.**

![image](https://github.com/user-attachments/assets/0cae8eb6-c8f7-4d23-b5e1-217e059d4e73)

- If you ever need to rebind, delete the "fenix_lights.json" file in the /Settings dir and restart the script ("Restart Script" button).

## MobiFlight WASM Module Installation is Required!
> ⚠️ Requires Mobiflight WASM module.  ⚠️
- Note that this requires a MobiFlight WASM installation: see [Notes on Mobiflight Integration](../readme.md#notes-on-mobiflight-integration). 

## How to Change the Preset Brightness Values
- At the moment for this you will need to edit the script directly.  This section dictates the starting values:
``` python
# Lighting LVARs with default values (will be assigned at start)
LIGHTING_LVARS = {
    "L:S_OH_INT_LT_DOME": 0,                # Dome Light (0,1,2)
    "L:A_OH_LIGHTING_OVD": 100,             # Overhead backlighting (0-100)
    "L:A_MIP_LIGHTING_MAP_L": 0.1,          # Left Map Lighting
    "L:A_MIP_LIGHTING_MAP_R": 0.1,          # Right Map Lighting
    "L:A_MIP_LIGHTING_FLOOD_MAIN": 0.1,     # Flood Light - Main Panel
    "L:A_MIP_LIGHTING_FLOOD_PEDESTAL": 0.1, # Flood Light - Pedestal
    "L:A_PED_LIGHTING_PEDESTAL": 1,         # Panel & Pedestal (button backlight)
    "L:A_CHART_LIGHT_TEMP_FO": 0,           # FO window brightness knob
    "L:S_CHART_LIGHT_TEMP_FO": 0,           # FO chart light switch
    "L:A_CHART_LIGHT_TEMP_CAPT": 0,         # Capt window brightness knob
    "L:S_CHART_LIGHT_TEMP_CAPT": 0,         # Capt chart light switch
    "L:S_MIP_LIGHT_CONSOLEFLOOR_CAPT": 0,   # Console floor light (capt)
    "L:S_MIP_LIGHT_CONSOLEFLOOR_FO": 0      # Console floor light (FO)
}
```
- Change these to taste if you wish to use other values.
