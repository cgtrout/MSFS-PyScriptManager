# Altitude Plot (`plot_altitude.py`)

`plot_altitude.py` opens a draggable transparent graph window that plots a SimConnect value over time.

## What It Does
- Plots `PLANE_ALTITUDE` by default.
- Supports scroll-back in history with mouse wheel.
- Supports `Ctrl + MouseWheel` resizing.
- Offers right-click context menu to export captured data to CSV.
- Copy and edit this script to tailor it to your own usecases.

## How to Run
- Start `MSFS-PyScriptManager.exe`.
- Run `plot_altitude.py`.
- Drag the window with left mouse.
- Right-click the plot to export CSV.

## Quick Customization (in script)
- `lookup_key`: SimVar to plot.
- `y_axis_label`, `y_min`, `y_max`: axis formatting.
- `update_interval`: sample interval.
- `recording_duration`: retained history length.

## Notes
- SimVar names: https://docs.flightsimulator.com/html/Programming_Tools/SimVars/Simulation_Variables.htm
- If SimConnect drops, the script retries connection.
