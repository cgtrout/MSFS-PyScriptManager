# METAR Loader (`metar_load.py`)

`metar_load.py` fetches METAR data for an ICAO airport and can print selected output to `VirtualTextPrinter`.

## What It Does
- Pulls METAR data from online sources (tries multiple providers).
- Matches best report to simulator time (or real-world UTC, based on settings).
- Shows results in a selectable list.
- Prints selected METAR text to `VirtualTextPrinter`.

## How to Run
- Start `MSFS-PyScriptManager.exe`.
- Run `metar_load.py`.
- Enter an ICAO code when prompted.
- Select/confirm output in the result window.

## Settings
- File: `Settings/metar_load.json`
- Current setting:
  - `use_simulator_time`: if `true`, matching prefers simulator time; if `false`, uses real-world UTC.

You can use the launcher's **Open Settings** button for this script.

## Notes
- If simulator connection is unavailable, the script falls back to real-world time.
- Printing requires `virtual_pos_printer.py` to be running with `VirtualTextPrinter` configured.
