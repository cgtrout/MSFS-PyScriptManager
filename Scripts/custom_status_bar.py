# custom_status_bar.py: shows a draggable, customizable status bar using SimConnect to display real-time flight simulator metrics like time, altitude, and temperature in a compact GUI.
#   - use instructions below to customize
#   - Uses https://github.com/odwdinc/Python-SimConnect library to obtain values from SimConnect

import tkinter as tk
from tkinter import simpledialog, messagebox
from SimConnect import SimConnect, AircraftRequests
from datetime import datetime, timezone, timedelta
import os
import json
import requests
import time

# Print initial message
print("custom_status_bar: Close this window to close status bar")

# DISPLAY_TEMPLATE
# Defines the content and format of the data shown in the application's window, including dynamic data elements
# ('VAR()' and 'VARIF()' blocks) and static text.

# Syntax:
# VAR(label, function_name, color)
# - 'label': Static text prefix.
# - 'function_name': Python function to fetch dynamic values.
# - 'color': Text color for label and value.

# VARIF(label, function_name, color, condition_function_name)
# - Same as VAR, but includes:
#   - 'condition_function_name': A Python function that determines if the block should display (True/False).

# Notes:
# - Static text can be included directly in the template.
# - Dynamic function calls in labels (e.g., ## suffix) are supported.
# - VARIF blocks are only displayed if the condition evaluates to True.

DISPLAY_TEMPLATE = (
    "VAR(Sim:, get_sim_time, yellow) | "
    "VAR(Zulu:, get_real_world_time, white) |" 
    "VARIF(Sim Rate:, get_sim_rate, white, is_sim_rate_accelerated) VARIF(|, '', white, is_sim_rate_accelerated)  " # Use VARIF on | to show conditionally
    "VAR(remain_label##, get_time_to_future, red) | "
    "VAR(, get_temp, cyan)"
)

# Other examples that can be placed in template
# VAR(Altitude:, get_altitude, tomato)

# Configurable Variables
SIMBRIEF_USERNAME = ""  # Enter your SimBrief username here to enable automatic lookup of flight arrival times for the countdown timer. Leave blank to disable SimBrief integration.
USE_SIMBRIEF_ADJUSTED_TIME = False  # Set to True for simulator-adjusted time, False for real-world time

alpha_transparency_level = 0.95  # Set transparency (0.0 = fully transparent, 1.0 = fully opaque)
WINDOW_TITLE = "Simulator Time"
DARK_BG = "#000000"
FONT = ("Helvetica", 16)
UPDATE_INTERVAL = 1000  # in milliseconds (1 second)
RECONNECT_INTERVAL = 1000  # in milliseconds (5 seconds)
SIMBRIEF_UPDATE_INTERVAL = 15000  # in milliseconds (15 seconds)

PADDING_X = 20  # Horizontal padding for each label
PADDING_Y = 10  # Vertical padding for the window

sm = None
aq = None
sim_connected = False
future_time = None  # Time for countdown in seconds
is_future_time_manually_set = False
last_simbrief_generated_time = None  # Store the last loaded SimBrief time for update checks
last_entered_time = None  # Last entered future time in HHMM format

# --- SimConnect Lookup  ---
def get_sim_time():
    """Fetch the simulator time from SimConnect, formatted as HH:MM:SS."""
    try:
        sim_time_seconds = get_simconnect_value("ZULU_TIME")
        # Create a datetime object starting from midnight and add the sim time seconds
        sim_time = (datetime.min + timedelta(seconds=int(sim_time_seconds))).time()
        return sim_time.strftime("%H:%M:%S")
    except Exception as e:
        return str(e)

def get_real_world_time():
    """Fetch the real-world Zulu time."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def get_altitude():
    """Fetch the altitude from SimConnect, formatted in feet."""
    return get_formatted_value("PLANE_ALTITUDE", "{:.0f} ft")

def get_sim_rate():
    """Fetch the sim rate from SimConnect, formatted in feet."""
    return get_formatted_value("SIMULATION_RATE", "{:.1f}")

def is_sim_rate_accelerated():
    """Check if the simulator rate is accelerated (not 1.0)."""
    try:
        rate = get_simconnect_value("SIMULATION_RATE")
        if rate is None:
            return False
        return float(rate) != 1.0  # True if the rate is not 1.0
    except Exception:
        return False  # Default to False in case of an error

def get_temp():
    """Fetch both TAT and SAT temperatures from SimConnect, formatted with labels."""
    return get_formatted_value(["AMBIENT_TEMPERATURE", "TOTAL_AIR_TEMPERATURE"], "TAT {1:.0f}°C  SAT {0:.0f}°C")

def remain_label():
    """
    Returns the full 'Remaining' label dynamically.
    Includes '(adj)' if time adjustment for acceleration is active, otherwise 'Remaining'.
    """
    if is_sim_rate_accelerated():
        return "Rem(adj):"
    return "Remaining:"

def get_time_to_future():
    """
    Calculate remaining time to the globally configured future event.
    Adjusts for simulator time acceleration if necessary.
    Returns '00:00:00' if the future time has not been set or an error occurs.
    """
    global future_time

    # If future_time is not set, return "00:00:00"
    if future_time is None:
        return "00:00:00"

    try:
        # Fetch current simulator time
        current_sim_time = get_simulator_datetime()

        # Ensure both times are timezone-aware (UTC)
        if future_time.tzinfo is None or current_sim_time.tzinfo is None:
            raise ValueError("Future time or simulator time is offset-naive. Ensure all times are offset-aware.")

        # Calculate remaining time
        remaining_time = future_time - current_sim_time
        if remaining_time.total_seconds() <= 0:
            return "00:00:00"  # If remaining time is zero or negative

        # Fetch simulation rate
        sim_rate = get_sim_rate()
        if sim_rate is not None:
            sim_rate = float(sim_rate)  # Ensure simulation rate is numeric
            if sim_rate > 0:  # Avoid division by zero or invalid rates
                adjusted_seconds = remaining_time.total_seconds() / sim_rate
            else:
                print(f"DEBUG: Invalid simulation rate ({sim_rate}); using unadjusted time.")
                adjusted_seconds = remaining_time.total_seconds()
        else:
            print("DEBUG: Simulation rate unavailable; using unadjusted time.")
            adjusted_seconds = remaining_time.total_seconds()

        # Format the adjusted remaining time as HH:MM:SS
        hours, remainder = divmod(adjusted_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    except Exception as e:
        print(f"DEBUG: Error in get_time_to_future: {e}")
        return "00:00:00"

def initialize_simconnect():
    """Initialize the connection to SimConnect."""
    global sm, aq, sim_connected
    try:
        sm = SimConnect()  # Connect to SimConnect
        aq = AircraftRequests(sm)
        sim_connected = True
    except Exception:
        sim_connected = False
        root.after(RECONNECT_INTERVAL, initialize_simconnect)

def get_simconnect_value(variable_name, max_retries=3):
    """
    Generalized function to fetch a SimConnect variable with retry logic.
    Retries fetching the value if it fails or returns None.
    Handles disconnection gracefully and prevents excessive log spamming.
    """
    global sim_connected

    if not sim_connected:
        print(f"DEBUG: SimConnect not connected. Skipping variable '{variable_name}'.")
        raise ConnectionError("NO_CONNECTION")

    for attempt in range(max_retries):
        try:
            value = aq.get(variable_name)
            if value is not None:  # Valid value received
                return value
        except WindowsError as e:  # Handle Windows-specific errors
            print(f"DEBUG: WindowsError fetching '{variable_name}' (Attempt {attempt + 1}/{max_retries}): {e}")
            sim_connected = False  # Mark SimConnect as disconnected
            raise ConnectionError("ConnectionError") from e
        except Exception as e:
            print(f"DEBUG: Error fetching '{variable_name}' (Attempt {attempt + 1}/{max_retries}): {e}")

    # If all retries fail, raise an exception
    sim_connected = False  # Mark SimConnect as disconnected after multiple failures
    raise ValueError(f"Unable to fetch value for '{variable_name}' after {max_retries} attempts.")

def get_formatted_value(variable_names, format_string=None):
    """
    Fetch one or more SimConnect variables, apply optional formatting if provided.
    
    Parameters:
    - variable_names: The SimConnect variable name(s) to retrieve (can be a single name or a list).
    - format_string: An optional string format to apply to the retrieved values.
    
    Returns:
    - The formatted string, or an error message if retrieval fails.
    """
    if isinstance(variable_names, str):
        variable_names = [variable_names]

    try:
        values = [get_simconnect_value(var) for var in variable_names]
        if format_string:
            return format_string.format(*values)
        return values[0] if len(values) == 1 else values  # Return raw value(s) if no format specified
    except Exception as e:
        print( "get_formatted_value caught exception: " + str(e) )
        return "Err"

def get_simulator_datetime():
    """
    Fetch the current simulator date and time as a datetime object.
    Ensure it is simulator time and timezone-aware (UTC).
    """
    try:
        # Fetch simulator date and time from SimConnect (ZULU time assumed as UTC)
        zulu_year = int(get_simconnect_value("ZULU_YEAR"))
        zulu_month = int(get_simconnect_value("ZULU_MONTH_OF_YEAR"))
        zulu_day = int(get_simconnect_value("ZULU_DAY_OF_MONTH"))
        zulu_time_seconds = float(get_simconnect_value("ZULU_TIME"))

        # Convert ZULU_TIME (seconds since midnight) into hours, minutes, seconds
        hours, remainder = divmod(int(zulu_time_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)

        # Construct and return the current datetime object with UTC timezone
        simulator_datetime = datetime(zulu_year, zulu_month, zulu_day, hours, minutes, seconds, tzinfo=timezone.utc)
        return simulator_datetime

    except Exception as e:
        raise ValueError(f"get_simulator_datetime: Failed to retrieve simulator datetime: {str(e)}")

def get_simulator_time_offset():
    """
    Calculate the offset between simulator time and real-world UTC time.
    Returns a timedelta representing the difference (simulator time - real-world time).
    """
    try:
        # Get simulator Zulu time (simulator time in UTC)
        simulator_time = get_simulator_datetime()

        # Get real-world UTC time
        real_world_time = datetime.now(timezone.utc)

        # Calculate the offset
        offset = simulator_time - real_world_time
        print(f"DEBUG: Simulator Time Offset: {offset}")
        return offset
    except Exception as e:
        print(f"Error calculating simulator time offset: {e}")
        return timedelta(0)  # Default to no offset if error occurs

def convert_real_world_time_to_sim_time(real_world_time):
    """
    Convert a real-world datetime (UTC) to simulator time using the calculated offset.
    """
    try:
        # Get the simulator time offset
        offset = get_simulator_time_offset()

        # Adjust the real-world time to simulator time
        sim_time = real_world_time + offset
        print(f"DEBUG: Converted Real-World Time {real_world_time} to Sim Time {sim_time}")
        return sim_time
    except Exception as e:
        print(f"Error converting real-world time to sim time: {e}")
        return real_world_time  # Return the original time as fallback

def set_future_time_internal(future_time_input, current_sim_time):
    """
    Internal helper function to process and set the future time.
    Assumes the input time is already in the correct format.
    """
    global future_time
    try:
        # Ensure all times are timezone-aware (UTC)
        if current_sim_time.tzinfo is None:
            current_sim_time = current_sim_time.replace(tzinfo=timezone.utc)

        if isinstance(future_time_input, datetime):
            # Validate that the future time is after the current simulator time
            if future_time_input <= current_sim_time:
                raise ValueError("Future time must be later than the current simulator time.")

            # Set the future time
            future_time = future_time_input
            print(f"DEBUG: Future time set to: {future_time}")
            return True
        else:
            raise TypeError("Unsupported future_time_input type. Must be a datetime object.")

    except ValueError as ve:
        print(f"Validation error in set_future_time_internal: {ve}")
    except Exception as e:
        print(f"DEBUG: Unexpected error in set_future_time_internal: {str(e)}")
    return False

def set_future_time():
    """
    Prompt the user to set a future countdown time based on Sim Time.
    If no input is provided, use SimBrief time based on the global `USE_SIMBRIEF_ADJUSTED_TIME` flag.
    """
    global future_time, is_future_time_manually_set, last_entered_time
    try:
        # Get current simulator datetime
        current_sim_time = get_simulator_datetime()
        sim_time_str = current_sim_time.strftime("%H:%M:%S")

        # Prompt the user to enter the future time in HHMM format
        prompt_message = f"Enter future time based on Sim Time (HHMM)\nCurrent Sim Time: {sim_time_str}"
        future_time_input = simpledialog.askstring("Input", prompt_message, initialvalue=last_entered_time, parent=root)

        # If user provides input, convert it to a datetime object
        if future_time_input:
            last_entered_time = future_time_input  # Save the entered time for the next prompt
            try:
                # Convert HHMM to hours and minutes
                hours = int(future_time_input[:2])
                minutes = int(future_time_input[2:])

                # Create a new datetime object with the entered time
                future_time_candidate = datetime(
                    year=current_sim_time.year,
                    month=current_sim_time.month,
                    day=current_sim_time.day,
                    hour=hours,
                    minute=minutes,
                    tzinfo=timezone.utc
                )

                # Adjust for times past midnight
                if future_time_candidate < current_sim_time:
                    # If the entered time is earlier than the current time, assume it's for the next day
                    future_time_candidate += timedelta(days=1)

                # Validate and set the future time
                is_future_time_manually_set = True
                if set_future_time_internal(future_time_candidate, current_sim_time):
                    print(f"DEBUG: Future time manually set to: {future_time}")
                else:
                    print("DEBUG: Failed to set future time.")
            except (ValueError, IndexError):
                messagebox.showerror("Error", "Invalid time format. Please enter time in HHMM format.")
        else:
            # If no input is provided, fallback to SimBrief time
            load_simbrief_future_time()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to set future time: {str(e)}")

# --- Template Parsing  ---
def get_dynamic_value(function_name):
    try:
        if not function_name.strip():  # If function name is empty, return an empty string
            return ""
        if function_name in globals():
            func = globals()[function_name]
            if callable(func):
                return func()
        return ""  # Return an empty string if the function doesn't exist
    except Exception as e:
        print(f"Error executing function '{function_name}': {str(e)}")
        return ""

# --- Display Update  ---
def update_display():
    """Update the display based on the user-defined template."""
    global is_moving  # Ensure dragging doesn't interrupt updates

    if is_moving:
        root.after(UPDATE_INTERVAL, update_display)
        return

    try:
        # Clear the frame
        for widget in display_frame.winfo_children():
            widget.destroy()

        index = 0
        while index < len(DISPLAY_TEMPLATE):
            # Handle VAR or VARIF blocks
            if DISPLAY_TEMPLATE[index:index + 4] == "VAR(" or DISPLAY_TEMPLATE[index:index + 6] == "VARIF(":
                is_varif = DISPLAY_TEMPLATE[index:index + 6] == "VARIF("
                block_type = "VARIF" if is_varif else "VAR"
                end_index = DISPLAY_TEMPLATE.find(")", index)
                if end_index == -1:
                    break  # Malformed block, exit

                content = DISPLAY_TEMPLATE[index + len(block_type) + 1:end_index]
                index = end_index + 1  # Move to next block

                parts = content.split(",")
                if is_varif and len(parts) == 4:  # VARIF(label, function, color, condition)
                    label, func_name, color, condition_func = map(str.strip, parts)
                    condition = get_dynamic_value(condition_func)
                    if not condition:  # Skip this block if the condition is False
                        continue
                elif not is_varif and len(parts) == 3:  # VAR(label, function, color)
                    label, func_name, color = map(str.strip, parts)
                else:
                    continue  # Skip malformed blocks

                # Process the label for ## functionality
                if "##" in label:
                    label = process_label_with_dynamic_functions(label)

                # Handle empty functions gracefully (e.g., conditional |)
                if not func_name:  # If function is empty, show the label only
                    value_str = ""
                else:
                    # Fetch the value for the block
                    value = get_dynamic_value(func_name)
                    value_str = str(value) if value is not None else ""

                # Skip empty dynamic values (but not labels)
                if not label.strip() and value_str == "":
                    continue

                # Add the label and value
                label_text = f"{label} {value_str}".strip()
                label_widget = tk.Label(display_frame, text=label_text, fg=color, font=FONT, bg=DARK_BG)
                label_widget.pack(side=tk.LEFT, padx=0, pady=0)
            else:
                # Handle static text outside of VAR or VARIF blocks
                next_var_index = DISPLAY_TEMPLATE.find("VAR(", index)
                next_varif_index = DISPLAY_TEMPLATE.find("VARIF(", index)
                next_index = min(next_var_index if next_var_index != -1 else len(DISPLAY_TEMPLATE),
                                    next_varif_index if next_varif_index != -1 else len(DISPLAY_TEMPLATE))

                static_text = DISPLAY_TEMPLATE[index:next_index].strip()
                index = next_index

                # Display the static text as-is
                if static_text:
                    static_text_widget = tk.Label(display_frame, text=static_text, fg="white", font=FONT, bg=DARK_BG)
                    static_text_widget.pack(side=tk.LEFT, padx=0, pady=0)

        # Adjust window size
        root.update_idletasks()
        root.geometry(f"{display_frame.winfo_reqwidth() + PADDING_X}x{display_frame.winfo_reqheight() + PADDING_Y}")
    except Exception as e:
        print(f"Error in update_display: {e}")

    # Schedule next update
    root.after(UPDATE_INTERVAL, update_display)

def process_label_with_dynamic_functions(label):
    """
    Replace occurrences of function_name## in the label with the evaluated result of the function.
    """
    while "##" in label:
        # Find the position of the first ##
        pos = label.find("##")
        # Extract the text before ##
        before = label[:pos].strip()
        # Find the last "word" (function name) before ##
        function_name = before.split()[-1]  # Last word in the preceding text
        # Fetch the dynamic value
        replacement_value = get_dynamic_value(function_name)
        # Replace `function_name##` with the result of the function call
        label = label.replace(f"{function_name}##", str(replacement_value) if replacement_value is not None else "", 1)
    return label

# --- Simbrief functionality ---
def get_latest_simbrief_ofp_json(username):
    """
    Fetch SimBrief OFP JSON data for the provided username.
    Returns None if the username is not set or if an error occurs.
    """
    if not username.strip():
        print("DEBUG: SimBrief username is not set. Skipping SimBrief lookup.")
        return None

    simbrief_url = f"https://www.simbrief.com/api/xml.fetcher.php?username={username}&json=1"
    try:
        response = requests.get(simbrief_url)
        if response.status_code == 200:
            return response.json()
        print(f"DEBUG: SimBrief API call failed with status code {response.status_code}")
        return None
    except Exception as e:
        print(f"DEBUG: Error fetching SimBrief OFP: {str(e)}")
        return None

    
def decode_timestamps(ofp_json):
    """
    Decode relevant SimBrief timestamps into datetime objects.
    """
    try:
        # Decode key timestamps
        sched_out = datetime.fromtimestamp(int(ofp_json["sched_out"]), tz=timezone.utc) if "sched_out" in ofp_json else None
        sched_in = datetime.fromtimestamp(int(ofp_json["sched_in"]), tz=timezone.utc) if "sched_in" in ofp_json else None
        est_in = datetime.fromtimestamp(int(ofp_json["est_in"]), tz=timezone.utc) if "est_in" in ofp_json else None

        return {
            "sched_out": sched_out,
            "sched_in": sched_in,
            "est_in": est_in,
        }
    except Exception as e:
        print(f"Error decoding timestamps: {e}")
        return None

def get_simbrief_ofp_arrival_datetime(username):
    """
    Fetch the estimated arrival time from SimBrief as a datetime object.
    Returns None if the username is not set or SimBrief data is unavailable.
    """
    if not username.strip():
        print("DEBUG: SimBrief username is not set. Cannot retrieve arrival datetime.")
        return None

    ofp_json = get_latest_simbrief_ofp_json(username)
    if ofp_json:
        try:
            # Access the nested "times" dictionary and extract "est_in"
            if "times" in ofp_json and "est_in" in ofp_json["times"]:
                est_in_epoch = int(ofp_json["times"]["est_in"])
                est_in_datetime = datetime.fromtimestamp(est_in_epoch, tz=timezone.utc)
                return est_in_datetime
            else:
                print("DEBUG: 'est_in' not found in SimBrief JSON under 'times'.")
        except Exception as e:
            print(f"DEBUG: Error processing SimBrief arrival datetime: {e}")
    return None

def load_simbrief_future_time():
    """
    Load SimBrief's arrival time and set it as the future time.
    Adjusts the time if `USE_SIMBRIEF_ADJUSTED_TIME` is enabled.
    """
    global future_time

    if not SIMBRIEF_USERNAME.strip():
        print("DEBUG: SimBrief username is not set; skipping load.")
        return

    try:
        # Fetch the latest SimBrief OFP JSON data for the provided username
        simbrief_arrival_datetime = get_simbrief_ofp_arrival_datetime(SIMBRIEF_USERNAME)
        if simbrief_arrival_datetime:
            # Adjust time if needed
            if USE_SIMBRIEF_ADJUSTED_TIME:
                sim_time = convert_real_world_time_to_sim_time(simbrief_arrival_datetime)
                print(f"DEBUG: Adjusted SimBrief arrival time to simulator time: {sim_time}")
                set_future_time_internal(sim_time, get_simulator_datetime())
            else:
                print(f"DEBUG: Using SimBrief real-world time directly: {simbrief_arrival_datetime}")
                set_future_time_internal(simbrief_arrival_datetime, get_simulator_datetime())
        else:
            print("DEBUG: SimBrief arrival time not available.")
    except Exception as e:
        print(f"ERROR: Failed to set SimBrief Future Time: {e}")

def periodic_simbrief_update():
    """
    Periodically update the future time using SimBrief data if no user-set time exists.
    Detects and reloads only if the SimBrief plan's generation time has changed.
    """
    global future_time, is_future_time_manually_set, last_simbrief_generated_time

    try:
        # Skip if the user has manually set a time
        if not is_future_time_manually_set:
            # Fetch the latest SimBrief data
            ofp_json = get_latest_simbrief_ofp_json(SIMBRIEF_USERNAME)
            if not ofp_json:
                print("DEBUG: No SimBrief data available.")
            else:
                # Extract the generation time
                current_generated_time = ofp_json.get("params", {}).get("time_generated")
                if not current_generated_time:
                    print("DEBUG: Unable to determine SimBrief flight plan generation time.")
                elif current_generated_time != last_simbrief_generated_time:
                    print(f"DEBUG: New SimBrief flight plan detected. Generation Time: {current_generated_time}")
                    last_simbrief_generated_time = current_generated_time  # Update to the new generation time

                    # Reload SimBrief future time
                    load_simbrief_future_time()
    except Exception as e:
        print(f"DEBUG: Error in periodic SimBrief update: {e}")

    # Schedule the next update
    root.after(SIMBRIEF_UPDATE_INTERVAL, periodic_simbrief_update)

# --- Drag functionality ---
is_moving = False

def start_move(event):
    """Start moving the window."""
    global is_moving, offset_x, offset_y
    is_moving = True
    offset_x = event.x
    offset_y = event.y

def do_move(event):
    """Handle window movement."""
    if is_moving:
        deltax = event.x - offset_x
        deltay = event.y - offset_y
        new_x = root.winfo_x() + deltax
        new_y = root.winfo_y() + deltay
        root.geometry(f"+{new_x}+{new_y}")

def stop_move(event):
    """Stop moving the window."""
    global is_moving
    is_moving = False
    save_settings({"x": root.winfo_x(), "y": root.winfo_y()})

# --- Settings  ---
SCRIPT_DIR = os.path.dirname(__file__)
SETTINGS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "Settings")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "custom_status_bar.json")

# Ensure the Settings directory exists
os.makedirs(SETTINGS_DIR, exist_ok=True)

def load_settings():
    """Load settings from the JSON file."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Error: Settings file is corrupted. Using defaults.")
    return {"x": 0, "y": 0}  # Default position

def save_settings(settings):
    """Save settings to the JSON file."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Error saving settings: {e}")

# --- Load initial settings ---
settings = load_settings()
initial_x = settings.get("x", 0)
initial_y = settings.get("y", 0)

print(f"DEBUG: Loaded settings - x: {initial_x}, y: {initial_y}")

# --- GUI Setup ---
root = tk.Tk()
root.title(WINDOW_TITLE)
root.overrideredirect(True)
root.attributes("-topmost", True)
root.attributes("-alpha", alpha_transparency_level)
root.configure(bg=DARK_BG)

# Apply initial geometry after creating the root window
try:
    # Set initial position
    root.geometry(f"+{initial_x}+{initial_y}")
    print(f"DEBUG: Applied geometry - x: {initial_x}, y: {initial_y}")
except Exception as e:
    print(f"DEBUG: Failed to apply geometry - {e}")

# Bind mouse events to enable dragging of the window
root.bind("<Button-1>", start_move)
root.bind("<B1-Motion>", do_move)
root.bind("<ButtonRelease-1>", stop_move)

# Frame to hold the labels
display_frame = tk.Frame(root, bg=DARK_BG)
display_frame.pack(padx=10, pady=5)

# --- Double click functionality for setting timer ---
root.bind("<Double-1>", lambda event: set_future_time())

# Initialize SimConnect
initialize_simconnect()

# Start the time update loop
periodic_simbrief_update()
update_display()

# Run the GUI event loop
root.mainloop()
