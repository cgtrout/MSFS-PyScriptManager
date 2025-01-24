# Custom Status Bar (custom_status_bar.py)
![image](https://github.com/user-attachments/assets/05786688-b542-4050-95eb-1e85bf8d673d)
- This script displays a fully customizable status bar that dynamically retrieves information from SimConnect and SimBrief.
- A key feature of this is a dynamic countdown timer which can either be manually set or set to a SimBrief time.  See: [Setting the Countdown Timer](#setting-the-countdown-timer).
- This script uses an easily modifiable 'template' system to define the variables that show on the bar.
    - On first run, a file will be created at /Settings/status_bar_templates.py that defines these templates.
    - For more info see: [Template Customization](#template-customization)

## How to Run the Script
- To open this script, ensure MSFS-PyScriptManager.exe is running, click "Run Script" and then open "custom_status_bar.py".
  
## Setting the Countdown Timer 
If the status bar is double-clicked, it will bring up a settings dialog for the countdown timer:

![image](https://github.com/user-attachments/assets/b3271a5d-6cf6-48f9-b2c1-1aed4832bb73)
- If you want a simple countdown timer set to a specific time, type it in the top field and click OK (or hit enter on keyboard).
- Alternatively, to use a SimBrief-based timer, click the SimBrief Settings button to expand the configuration page.
- The settings for this will be explained below:

## Basic SimBrief Usage Example
- Set to your SimBrief user name.
- Ensure you have filed a flight with SimBrief.
- Select either "Estimated In" or "Estimated TOD".
- Click "Get Time" - this will set timer using the settings provided on the page.  The dialog will be closed.

## Detailed SimBrief Timer Settings
- **SimBrief UserName:** SimBrief Id used to optionally pull time (for countdown timer)
- **Gate Out Time**: Set this if your gate leave time is behind or ahead of schedule.  If not set, the gate out time from the SimBrief report will be used
- **Translate SimBrief Time to Simulator Time:** Converts SimBrief’s real-world times to match the in-sim time if the simulator’s clock differs. 
- **Allow Negative Timer:** allows countdown timer to show negative values.
- **Enable Auto SimBrief Updates:** if set will automatically pull SimBrief information into the timer without the need to manually open this dialog.
- **Select SimBrief Time:** select if you want the countdown timer to "Estimated In" or "Estimated TOD"
- **Get Time Button:** when clicked will take the SimBrief time and use that to set the countdown timer.

## Template Customization
When the script runs for the first time, it generates a status_bar_templates.py file. This file:
- Defines how the status bar displays information.
- Can be edited to create multiple templates for different aircraft or situations.

The first section defines the visual structure of the template.  VAR, VARIF are template functions that will dynamically call functions such as get_sim_time and show them when the template is drawn.
```python
TEMPLATES = {
    "Default": (
        "VAR(Sim:, get_sim_time, yellow) | "
        "VAR(Zulu:, get_real_world_time, white ) |"
        "VARIF(Sim Rate:, get_sim_rate, white, is_sim_rate_accelerated) VARIF(|, '', white, is_sim_rate_accelerated)  " # Use VARIF on | to show conditionally
        "VAR(remain_label##, get_time_to_future_adjusted, red) | "
        "VAR(, get_temp, cyan)"
    ),
    "Altitude and Temp": (
        "VAR(Altitude:, get_altitude, tomato) | "
        "VAR(Temp:, get_temp, cyan)"
    ),
}
```

Further down it provides functions to allow you to hook in your own custom behavior:
```python
# Runs once per display update (approx. 30 times per second).
def user_update():
    pass

# Runs approx every 500ms for less frequent, CPU-intensive tasks.
def user_slow_update():
    pass

# Runs once during startup for initialization tasks.
def user_init():
    pass
```
## Template Example
The following is a template created by  [@leftos](https://github.com/leftos) that is a great example of how this can be utilized to create custom template behavior on the countdown timer.

The following example dynamically adjusts the countdown timer based on the engine state. It demonstrates how to link SimBrief's "gate out" and "arrival" times to flight phases.
```python
# Runs approx every 500ms for less frequent, CPU-intensive tasks.
def user_slow_update():
    update_target_time_based_on_engine_state()

# Runs once during startup for initialization tasks.
def user_init():
    global simbrief_settings, SIMBRIEF_TIME_OPTION_FUNCTIONS

    # This defines a custom Simbrief datetime load option
    SIMBRIEF_TIME_OPTION_FUNCTIONS["CUSTOM"] = SimBriefFunctions.get_simbrief_ofp_arrival_datetime
    simbrief_settings.selected_time_option = "CUSTOM"
    simbrief_settings.allow_negative_timer = True

was_engine_on = [ None, None, None, None ]
first_update = True

def get_remaining_label():
    if any(x is None for x in was_engine_on):
        return "Remaining"
    return "Remaining" if any(was_engine_on) else "Until OBT"

def update_target_time_based_on_engine_state():
    global was_engine_on, first_update, simbrief_settings, SIMBRIEF_TIME_OPTION_FUNCTIONS
    
    if simbrief_settings.selected_time_option != "CUSTOM":
        return

    if any(x is None for x in was_engine_on):
        for idx in range(4):
            if was_engine_on[idx] is None:
                eng_value = get_simconnect_value(f"GENERAL_ENG_COMBUSTION:{idx+1}", default_value=None, retries=10)
                if eng_value is not None:
                    try:
                        was_engine_on[idx] = int(eng_value) == 1
                    except ValueError:
                        pass
    
    if any(x is None for x in was_engine_on):
        return
    
    is_engine_on = was_engine_on.copy()
    for eng_idx in range(4):
        eng_value = check_cache(f"GENERAL_ENG_COMBUSTION:{eng_idx+1}")
        if eng_value is not None:
            try:
                is_engine_on[eng_idx] = int(eng_value) == 1
            except ValueError:
                pass
    was_any_engine_on = any(was_engine_on)
    is_any_engine_on = any(is_engine_on)
    was_engine_on = is_engine_on.copy()
    if first_update or is_any_engine_on != was_any_engine_on:
        if first_update:
            first_update = False
            print_info("First update of engine state.")
        else:
            print_info(f"Detected change in engine state. Updating target time from SimBrief. Before: {was_any_engine_on}, After: {is_any_engine_on}")
            
        if is_any_engine_on:
            SIMBRIEF_TIME_OPTION_FUNCTIONS["CUSTOM"] = SimBriefFunctions.get_simbrief_ofp_arrival_datetime
        else:
            SIMBRIEF_TIME_OPTION_FUNCTIONS["CUSTOM"] = SimBriefFunctions.get_simbrief_ofp_gate_out_datetime
            
        try:
            # Fetch the latest SimBrief data
            simbrief_json = SimBriefFunctions.get_latest_simbrief_ofp_json(simbrief_settings.username)
            if simbrief_json:
                # Extract the generation time
                current_generated_time = simbrief_json.get("params", {}).get("time_generated")
                if not current_generated_time:
                    print_warning("Unable to determine SimBrief flight plan generation time.")
                else:
                    # Try to reload SimBrief future time
                    success = SimBriefFunctions.update_countdown_from_simbrief(
                        simbrief_json=simbrief_json,
                        simbrief_settings=simbrief_settings,
                        gate_out_entry_value=None  # No manual entry for auto-update
                    )
                    if success:
                        print_info("Countdown timer updated successfully.")
                        # Update the stored generation time only on successful update
                        SimBriefFunctions.last_simbrief_generated_time = current_generated_time
                    else:
                        print_warning("Failed to update countdown timer from SimBrief data.")
            else:
                print_error("Failed to fetch SimBrief data during auto-update.")
        except Exception as e:
            print_error(f"DEBUG: Exception during auto-update: {e}")
```
## Additional Credits
Special thanks to [@leftos](https://github.com/leftos) for their valuable insights, feedback, pull requests, and initial implementations, which significantly contributed to the following features:
- SimBrief connectivity.
- VARIF/## template function.
- Dynamic template functionality.

