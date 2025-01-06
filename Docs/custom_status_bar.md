# Custom Status Bar (custom_status_bar.py)
![image](https://github.com/user-attachments/assets/05786688-b542-4050-95eb-1e85bf8d673d)
- This script will show a customizable status bar that pulls information dynamically from SimConnect and Simbrief.
- A key feature of this is a dynamic countdown timer which can either be manually set or set to a Simbrief time.  Further details provided below.
- To open this script, ensure MSFS-PyScriptManager.exe is running, click "Run Script" and then open "custom_status_bar.py".
- This script uses an easily modifiable 'template' system to define the variables that show on the bar.  On first run, a file will be created at /Settings/status_bar_templates.py that defines these templates.
    - This file can be modified to create multiple templates.  Documentation for these templates is provided in the status_bar_templates.py file.
    - To change the displayed template (when the script is running), right click the status bar - this will bring up a menu allowing you to select a different template.
## Setting the Countdown Timer 
If the status bar is double-clicked, it will bring up a settings dialog for the countdown timer:

![image](https://github.com/user-attachments/assets/b3271a5d-6cf6-48f9-b2c1-1aed4832bb73)
- If you want a simple countdown timer set to a specific time, type it in the top field and click OK (or hit enter on keyboard).
- Alternatively if you would like to have the timer based on a Simbrief time click the "Simbrief Settings" to expand the Simbrief Settings page.
- The settings for this will be explained below:

## Basic Simbrief Usage Example
- Set to your simbrief user name.
- Ensure you have filed a flight with Simbrief.
- Select either "Estimated In" or "Estimated TOD".
- Click "Get Time" - this will set timer using the settings provided on the page.  The dialog will be closed.

## Detailed Simbrief Timer Settings
- **Simbrief UserName:** Simbrief Id used to optionally pull time (for countdown timer)
- **Gate Out Time**: Set this if your gate leave time is behind or ahead of schedule.  If not set, the gate out time from the Simbrief report will be used
- **Translate Simbrief Time to Simulator Time:** Converts Simbrief’s real-world times to match the in-sim time if the simulator’s clock differs. 
- **Allow Negative Timer:** allows countdown timer to show negative values.
- **Enable Auto SimBrief Updates:** if set will automatically pull Simbrief information into the timer without the need to manually open this dialog.
- **Select SimBrief Time:** select if you want the countdown timer to "Estimated In" or "Estimated TOD"
- **Get Time Button:** when clicked will take the Simbrief time and use that to set the countdown timer.

### Additional Credits
Thanks [@leftos](https://github.com/leftos) for the valuable feedback and ideas/initial implementations for:
- Simbrief connectivity
- VARIF template function.

