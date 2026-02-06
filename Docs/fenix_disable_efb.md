# Fenix Disable EFB Script (fenix_disable_efb.py)

This script hides the Fenix A32x EFBs (Electronic Flight Bags) and their charging cables for both captain and first officer sides.

## How To Use
- Run the script from the launcher.
- The script waits for the ground power switch (`S_OH_ELEC_EXT_PWR`) to be active before disabling the EFBs.
- Once complete, the script shuts down automatically. Restart it if you need to disable EFBs again (e.g. after a flight reload).

## What It Does
Disables the following Fenix LVARs:
- `S_EFB_VISIBLE_CAPT` / `S_EFB_VISIBLE_FO` — hides the EFB tablets
- `S_EFB_CHARGING_CABLE_CAPT` / `S_EFB_CHARGING_CABLE_FO` — hides the charging cables

## MobiFlight WASM Module Installation is Required!
> Requires Mobiflight WASM module.
- See [Mobiflight WASM Notes](../readme.md#mobiflight-wasm-notes) for installation instructions.

## Finding Other LVARs
- Fenix provides an LVAR reference guide: https://kb.fenixsim.com/example-of-how-to-use-lvars
