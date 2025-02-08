# Custom Status Bar (custom_status_bar.py)
![image](https://github.com/user-attachments/assets/05786688-b542-4050-95eb-1e85bf8d673d)
- This script displays a fully customizable status bar that dynamically retrieves information from SimConnect and SimBrief.
- A key feature of this is a dynamic countdown timer which can either be manually set or set to a SimBrief time.  See: [Setting the Countdown Timer](#setting-the-countdown-timer).
- This script uses an easily modifiable 'template' system to define the variables that show on the bar.
    - On first run, a file will be created at /Settings/status_bar_templates.py that defines these templates.
    - For more info see: [Template Customization](#template-customization)

## How to Run the Script
- To open this script, ensure MSFS-PyScriptManager.exe is running, click "Run Script" and then open "custom_status_bar.py".

## Potential Issues
- One user has reported to me that the status bar can randomly dissapear([#23](https://github.com/cgtrout/MSFS-PyScriptManager/issues/23)).
- Note that in my own extensive use of this script, I have never seen this issue, but if you do see it, the workaround is to restart the script with the "Restart" button on the bottom of the selected tab.
- To fix this issue I need to get more data:
  - If you do see this I would appreciate it if you can send me some log files to help me troubleshoot the issue.
  - A log file can be generated with ctrl+shift+alt+L (while the script is running).  The file generated is called "detailed_state_log.log".
  
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
When the script runs for the first time, it generates a status_bar_templates.py file in /Settings directory. This file:
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

# Runs once every 500ms. If this returns a SimBriefTimeOption, this will set the count down timer
# to a preset.
def user_simbrief():
    pass
```
## 

## Leftos SimBrief Timer Automation Example
There are a couple of lines you can change in the generated template file to automate the countdown timer in the following way:
- When engines are off the countdown timer will be based EOBT (Gate leave time).
- Otherwise it will select the saved timer preset.
This easily allows you to see if you are ahead or behind schedule on EOBT before engine-startup.

To enable this functionality change these lines to match:
```python
# Runs once every 500ms. If this returns a SimBriefTimeOption, this will set the count down timer
# to a preset.
def user_simbrief():
    return leftos_engineoff_sets_EOBT() # UNCOMMENT THIS LINE
    #pass # REMOVE OR COMMENT THIS LINE OUT

# This will return None / SimBriefTimeOption.EOBT to automate setting the timer according to engine
# state. Original idea/implementation by @leftos
def leftos_engineoff_sets_EOBT():
    is_engine_on = [ None, None, None, None ]

    for eng_idx in range(4):
        eng_value = get_simconnect_value(f"GENERAL_ENG_COMBUSTION:{eng_idx+1}")
        if eng_value is not None:
            try:
                is_engine_on[eng_idx] = int(eng_value) == 1
            except ValueError:
                pass
    is_any_engine_on = any(is_engine_on)
    if is_any_engine_on:
        return None # This will cause saved timer setting to be used (SimBriefTimeOption)
    else:
        return SimBriefTimeOption.EOBT
```
This is based on the initial idea / implementation provided by Leftos.  This has been added to the default template with his permission.

## Additional Credits
Special thanks to [@leftos](https://github.com/leftos) for his valuable insights, feedback, pull requests, and initial implementations, which significantly contributed to the following features:
- SimBrief connectivity.
- VARIF/## template function.
- Dynamic template functionality.

