# custom_status_bar.py: shows a draggable, customizable status bar using SimConnect to display real-time flight simulator metrics like time, altitude, and temperature in a compact GUI.
#   - use instructions below to customize
#   - Uses https://github.com/odwdinc/Python-SimConnect library to obtain values from SimConnect

import tkinter as tk
from tkinter import simpledialog, messagebox
from SimConnect import SimConnect, AircraftRequests
from datetime import datetime, timezone, timedelta
import os
import json
import re
import requests
import time

import threading

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
    "VAR(Zulu:, get_real_world_time, white ) |"
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
UPDATE_INTERVAL = 1000  # in milliseconds
RECONNECT_INTERVAL = 1000  # in milliseconds
SIMBRIEF_UPDATE_INTERVAL = 15000  # in milliseconds

PADDING_X = 20  # Horizontal padding for each label
PADDING_Y = 10  # Vertical padding for the window

sm = None
aq = None
sim_connected = False
future_time = None  # Time for countdown in seconds
is_future_time_manually_set = False
last_simbrief_generated_time = None  # Store the last loaded SimBrief time for update checks
last_entered_time = None  # Last entered future time in HHMM format

# Shared data structures for threading
simconnect_cache = {}
variables_to_track = set()
cache_lock = threading.Lock()

# --- SimConnect Lookup  ---
def get_sim_time():
    """Fetch the simulator time from SimConnect, formatted as HH:MM:SS."""
    try:

        if not sim_connected:
            return "Sim Not Running"

        sim_time_seconds = get_simconnect_value("ZULU_TIME")

        if sim_time_seconds == "N/A":
            return "Loading..."

        # Create a datetime object starting from midnight and add the sim time seconds
        sim_time = (datetime.min + timedelta(seconds=int(sim_time_seconds))).time()
        return sim_time.strftime("%H:%M:%S")
    except Exception as e:
        return "Err"

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
        return "00:00:00"

def initialize_simconnect():
    """Initialize the connection to SimConnect."""
    global sm, aq, sim_connected
    try:
        sm = SimConnect()  # Connect to SimConnect
        aq = AircraftRequests(sm, _time=0)
        sim_connected = True
    except Exception:
        sim_connected = False

def get_simconnect_value(variable_name, default_value="N/A", retries=10, retry_interval=0.2):
    """ Fetch a SimConnect variable from the cache with retry logic. """
    if not sim_connected or not sm.ok:
        return "Sim Not Running"

    for attempt in range(retries):
        with cache_lock:
            if variable_name in simconnect_cache:
                value = simconnect_cache[variable_name]
                if value != default_value:  # If value has been updated, return it
                    return value
            else:
                print(f"DEBUG get_simconnect_value: get_simconnect_value Attempt {attempt+1}/{retries} - Adding '{variable_name}' to track list.")
                variables_to_track.add(variable_name)
                simconnect_cache[variable_name] = default_value

        print(f"DEBUG get_simconnect_value: Attempt {attempt+1}/{retries} - Value for '{variable_name}' not updated yet. Retrying...")
        time.sleep(retry_interval)

    print(f"DEBUG: All {retries} retries failed for '{variable_name}'. Returning default: {default_value}")
    return default_value

def simconnect_background_updater():
    """Background thread to update SimConnect variables with retry logic, including retries for 'None' values."""
    global sim_connected, aq
    MAX_RETRIES = 5  # Maximum number of retries for each variable

    print("DEBUG: simconnect_background_updater start\n")

    while True:
        try:
            if not sim_connected:
                initialize_simconnect()
                continue

            if sim_connected:
                # Check to see if in flight
                if not sm.ok or sm.quit == 1:
                    sim_connected = False
                    continue

                # Make a copy of the variables to avoid holding the lock during network calls
                with cache_lock:
                    vars_to_update = list(variables_to_track)

                for variable_name in vars_to_update:
                    retries = 0
                    success = False
                    while retries < MAX_RETRIES and not success:
                        try:
                            value = aq.get(variable_name)
                            if value is not None:  # Check if a valid value is returned
                                with cache_lock:
                                    simconnect_cache[variable_name] = value
                                success = True
                            else:
                                retries += 1
                                time.sleep(0.1)  # Small delay before retrying
                        except Exception as e:
                            retries += 1
                            time.sleep(0.1)  # Small delay before retrying

                    if not success:
                        # If all retries fail, set a default or error value
                        with cache_lock:
                            simconnect_cache[variable_name] = "Err"
            else:
                print("DEBUG: SimConnect not connected. Retrying in {RECONNECT_INTERVAL}ms.")
                time.sleep(RECONNECT_INTERVAL / 1000.0)

        except OSError as os_err:
            print(f"DEBUG: OS error occurred: {os_err} - likely a connection issue")
            sim_connected = False

        except Exception as e:
            print(f"DEBUG: Error in background updater: {e}")

        # Sleep for the update interval
        time.sleep(UPDATE_INTERVAL / 1000.0)

def get_formatted_value(variable_names, format_string=None):
    """
    Fetch one or more SimConnect variables, apply optional formatting if provided.

    Parameters:
    - variable_names: The SimConnect variable name(s) to retrieve (can be a single name or a list).
    - format_string: An optional string format to apply to the retrieved values.

    Returns:
    - The formatted string, or an error message if retrieval fails.
    """

    if not sim_connected or not sm.ok:
        return "Sim Not Running"

    if isinstance(variable_names, str):
        variable_names = [variable_names]

    # Fetch values for the given variables
    values = [get_simconnect_value(var) for var in variable_names]

    # Format the values if a format string is provided
    if format_string:
        formatted_values = format_string.format(*values)
        return formatted_values

    # Return raw value(s) if no format string is provided
    result = values[0] if len(values) == 1 else values
    return result

def get_simulator_datetime():
    """
    Fetch the current simulator date and time as a datetime object.
    Ensure it is simulator time and timezone-aware (UTC).
    """
    global sim_connected
    try:
        # Fetch simulator date and time from SimConnect (ZULU time assumed as UTC)
        zulu_year = get_simconnect_value("ZULU_YEAR")
        zulu_month = get_simconnect_value("ZULU_MONTH_OF_YEAR")
        zulu_day = get_simconnect_value("ZULU_DAY_OF_MONTH")
        zulu_time_seconds = get_simconnect_value("ZULU_TIME")

        # Ensure all fetched values are valid
        if any(value is None or str(value) == "N/A" for value in [zulu_year, zulu_month, zulu_day, zulu_time_seconds]):
            raise ValueError("SimConnect values are not available yet.")

        # Convert values to integers and calculate datetime
        zulu_year = int(zulu_year)
        zulu_month = int(zulu_month)
        zulu_day = int(zulu_day)
        zulu_time_seconds = float(zulu_time_seconds)

        # Convert ZULU_TIME (seconds since midnight) into hours, minutes, seconds
        hours, remainder = divmod(int(zulu_time_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)

        # Construct and return the current datetime object with UTC timezone
        simulator_datetime = datetime(zulu_year, zulu_month, zulu_day, hours, minutes, seconds, tzinfo=timezone.utc)
        return simulator_datetime

    except ValueError as ve:
        print(f"DEBUG: Simulator datetime not ready: {ve}")
        return None  # Return None if data is not ready
    except Exception as e:
        print(f"get_simulator_datetime: Failed to retrieve simulator datetime: {e}")
        return None  # Return None for other exceptions

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

# --- Display Update  ---
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
        return "Err"

def update_display(parser, parsed_blocks):
    """
    Render the parsed blocks onto the display frame
    """
    try:
        if is_moving:
            root.after(UPDATE_INTERVAL, lambda: update_display(parser, parsed_blocks))

        # Clear the existing display
        for widget in display_frame.winfo_children():
            widget.destroy()

        # Render each block
        for block in parsed_blocks:
            block_type = block["type"]

            # Find the render function for the block type in the parser's block registry
            render_function = parser.block_registry.get(block_type, {}).get("render")

            # If a valid render function exists, use it to create and pack the widget
            if render_function:
                widget = render_function(block)
                if widget:
                    widget.pack(side=tk.LEFT, padx=0, pady=0)

        # Adjust the window size to fit the rendered content
        root.update_idletasks()
        root.geometry(f"{display_frame.winfo_reqwidth() + PADDING_X}x{display_frame.winfo_reqheight() + PADDING_Y}")

    except Exception as e:
        print(f"Error in update_display: {e}")

    # Reschedule the display update
    root.after(UPDATE_INTERVAL, lambda: update_display(parser, parsed_blocks))

# --- Simbrief functionality ---
def get_latest_simbrief_ofp_json(username):
    """
    Fetch SimBrief OFP JSON data for the provided username.
    Returns None if the username is not set or if an error occurs.
    """
    if not username.strip():
        return None

    simbrief_url = f"https://www.simbrief.com/api/xml.fetcher.php?username={username}&json=1"
    try:
        response = requests.get(simbrief_url, timeout=5)
        if response.status_code == 200:
            return response.json()
        print(f"DEBUG: SimBrief API call failed with status code {response.status_code}")
        return None
    except Exception as e:
        print(f"DEBUG: Error fetching SimBrief OFP: {str(e)}")
        return None

def get_simbrief_ofp_arrival_datetime(username):
    """
    Fetch the estimated arrival time from SimBrief as a datetime object.
    Returns None if the username is not set or SimBrief data is unavailable.
    """
    if not username.strip():
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
    Returns True if successful, False otherwise.
    """
    global future_time

    if not SIMBRIEF_USERNAME.strip():
        return False

    try:
        # Fetch the latest SimBrief OFP JSON data for the provided username
        simbrief_arrival_datetime = get_simbrief_ofp_arrival_datetime(SIMBRIEF_USERNAME)
        if simbrief_arrival_datetime:
            # Fetch simulator datetime
            current_sim_datetime = get_simulator_datetime()
            if current_sim_datetime is None:
                print("DEBUG: Simulator datetime not available yet. Retrying later.")
                return False  # Retry later

            # Adjust time if needed
            if USE_SIMBRIEF_ADJUSTED_TIME:
                sim_time = convert_real_world_time_to_sim_time(simbrief_arrival_datetime)
                print(f"DEBUG: Adjusted SimBrief arrival time to simulator time: {sim_time}")
                return set_future_time_internal(sim_time, current_sim_datetime)
            else:
                print(f"DEBUG: Using SimBrief real-world time directly: {simbrief_arrival_datetime}")
                return set_future_time_internal(simbrief_arrival_datetime, current_sim_datetime)
        else:
            print("DEBUG: SimBrief arrival time not available.")
            return False
    except Exception as e:
        print(f"ERROR: Failed to set SimBrief Future Time: {e}")
        return False

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
            if ofp_json:
                # Extract the generation time
                current_generated_time = ofp_json.get("params", {}).get("time_generated")
                if not current_generated_time:
                    print("DEBUG: Unable to determine SimBrief flight plan generation time.")
                elif current_generated_time != last_simbrief_generated_time:
                    print(f"DEBUG: New SimBrief flight plan detected. Generation Time: {current_generated_time}")

                    # Try to reload SimBrief future time
                    if load_simbrief_future_time():  # Update only if successful
                        last_simbrief_generated_time = current_generated_time
                    else:
                        print("DEBUG: Failed to load SimBrief future time. Will retry later.")
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

def main():
    global root, display_frame

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

    # Start the background thread
    background_thread = threading.Thread(target=simconnect_background_updater, daemon=True)
    background_thread.start()

    try:
        # Template parser stores block definitions and handles parsing
        template_parser = TemplateParser()
        # Parse the template string
        parsed_blocks = template_parser.parse_template(DISPLAY_TEMPLATE)

        # Start the update loop
        update_display(template_parser, parsed_blocks)

        # Run the GUI event loop
        root.mainloop()
    except ValueError as e:
        print(f"Error: {e}")
        print("Please check your DISPLAY_TEMPLATE and try again.")

class TemplateParser:
    """
    A parser for template strings that validates block names and parentheses,
    and converts them into structured blocks for rendering.
    """

    def __init__(self):
        """Initialize the parser with a block registry."""
        self.block_registry = {
            "VAR": {
                "keys": ["label", "function", "color"],
                "render": self.render_var,
            },
            "VARIF": {
                "keys": ["label", "function", "color", "condition"],
                "render": self.render_varif,
            },
            "STATIC_TEXT": {
                "keys": ["value"],
                "render": self.render_static_text,
            },
        }

    def parse_template(self, template_string):
        """Parse a template string into structured blocks."""
        # Validate parentheses and block names first
        self.validate_blocks_and_parentheses(template_string)

        parsed_blocks = []
        index = 0

        while index < len(template_string):
            # Find the next block type and its position
            next_block_type, next_index = self.get_next_block(template_string, index)

            # Handle STATIC_TEXT: Capture everything between recognized blocks
            static_text = template_string[index:next_index].strip()
            if static_text:
                parsed_blocks.append({"type": "STATIC_TEXT", "value": static_text})

            if next_block_type is None:
                break

            # Locate and validate the closing parenthesis for the block
            end_index = end_index = self.find_closing_parenthesis(template_string, next_index)

            # Extract and parse the block content
            block_content = template_string[next_index + len(next_block_type) + 1 : end_index]
            parsed_blocks.append(self.parse_block(next_block_type, block_content))

            index = end_index + 1

        return parsed_blocks

    def get_next_block(self, template_string, index):
        """Find the next block type and its position."""
        next_block_type = None
        next_index = len(template_string)

        for block_type in self.block_registry:
            if block_type != "STATIC_TEXT":
                block_start = self.find_next_occurrence(template_string, f"{block_type}(", index)
                if block_start != -1 and block_start < next_index:
                    next_block_type = block_type
                    next_index = block_start

        return next_block_type, next_index

    def find_next_occurrence(self, template_string, pattern, start_index):
        """Find the next occurrence of a pattern in the template."""
        return template_string.find(pattern, start_index)

    def find_closing_parenthesis(self, template_string, start_index):
        """Find the next closing parenthesis after the given start index."""
        for i in range(start_index, len(template_string)):
            if template_string[i] == ")":
                return i
        raise RuntimeError("No closing parenthesis found—this should have been validated earlier.")

    def parse_block(self, block_type, content):
        """Parse a block's content dynamically."""
        keys = self.block_registry[block_type]["keys"]
        values = list(map(str.strip, content.split(",")))

        # Validate block arguments
        if len(values) != len(keys):
            raise ValueError(
                f"Invalid number of arguments for {block_type}. "
                f"Expected {len(keys)}, got {len(values)}. Content: {values}"
            )

        for key, value in zip(keys, values):
            value = value.strip("'")
            if ("function" in key or "condition" in key) and value and value not in globals():
                raise ValueError(f"Function '{value}' does not exist for block {block_type}.")
            if key == "color" and not self.is_valid_color(value):
                raise ValueError(f"Invalid color '{value}' for block {block_type}.")

        return {"type": block_type, **dict(zip(keys, values))}

    def is_valid_color(self, color):
        """Validate a Tkinter color."""
        try:
            tk.Label(bg=color)  # Test if the color is valid in Tkinter
            return True
        except tk.TclError:
            return False

    def render_var(self, block):
        """Render a VAR block."""
        label = self.process_label_with_dynamic_functions(block["label"])
        value = get_dynamic_value(block["function"])
        text = f"{label} {value}"
        return tk.Label(display_frame, text=text, fg=block["color"], font=FONT, bg=DARK_BG)

    def render_varif(self, block):
        """Render a VARIF block."""
        condition = get_dynamic_value(block["condition"])
        if condition:
            label = self.process_label_with_dynamic_functions(block["label"])
            value = get_dynamic_value(block["function"])
            text = f"{label} {value}"
            return tk.Label(display_frame, text=text, fg=block["color"], font=FONT, bg=DARK_BG)
        return None

    def render_static_text(self, block):
        """Render a STATIC_TEXT block."""
        return tk.Label(display_frame, text=block["value"], fg="white", font=FONT, bg=DARK_BG)

    def process_label_with_dynamic_functions(self, label):
        """Replace occurrences of `function_name##` in the label with dynamic values."""
        while "##" in label:
            pos = label.find("##")
            before = label[:pos].strip()
            function_name = before.split()[-1]
            replacement_value = get_dynamic_value(function_name)
            label = label.replace(f"{function_name}##", str(replacement_value) if replacement_value is not None else "", 1)
        return label

    def validate_blocks_and_parentheses(self, template_string):
        """Ensure parentheses are correctly balanced and block names are valid."""
        def raise_error(message, position):
            """Helper function to raise a ValueError with context."""
            snippet = template_string[max(0, position - 20):position + 20]
            marker = ' ' * (position - max(0, position - 20)) + '^'
            raise ValueError(f"{message} at position {position}:\n\n{snippet}\n{marker}\n")

        stack = []  # Tracks opening parentheses and their block names

        # This loop scans the template string character by character to ensure:
        # 1. All opening parentheses `(` are matched with valid block names directly before them.
        #    - Example: "VAR(" requires "VAR" to be recognized as a valid block type.
        # 2. All closing parentheses `)` have a matching opening parenthesis `(`.
        #    - Ensures the parentheses are balanced.
        # 3. Any unmatched parentheses or invalid block names raise clear, actionable errors.
        # We use a stack to keep track of unmatched `(` and validate each `)` as we encounter them.

        i = 0
        while i < len(template_string):
            char = template_string[i]

            if char == "(":
                # Handle an opening parenthesis
                # Look backward to find the block name before '('
                name_start = i - 1
                while name_start >= 0 and (template_string[name_start].isalnum() or template_string[name_start] == "_"):
                    name_start -= 1
                block_name = template_string[name_start + 1:i].strip()

                # Raise an error if no block name is found before '('
                if not block_name:
                    raise_error("Missing block name before '('", i)

                # Raise an error if the block name is not recognized
                if block_name not in self.block_registry:
                    raise_error(f"Unsupported or misnamed block type: '{block_name}'", i)

                # Push the block name and its position onto the stack
                stack.append((block_name, i))

            elif char == ")":
                # Handle a closing parenthesis
                # Raise an error if there's no matching opening parenthesis
                if not stack:
                    raise_error("Unexpected ')'", i)

                # Pop the stack to match this closing parenthesis with the most recent '('
                block_name, start_position = stack.pop()

            # Increment the position to process the next character
            i += 1

        # After parsing, check for any unmatched opening parentheses left in the stack
        if stack:
            error_messages = []
            for block_name, position in stack:
                # For each unmatched '(', show its block name and position
                snippet = template_string[max(0, position - 20):position + 20]
                marker = ' ' * (position - max(0, position - 20)) + '^'
                error_messages.append(f"Unmatched '(' for block '{block_name}' at position {position}:\n\n{snippet}\n{marker}")

            # Raise a single error summarizing all unmatched opening parentheses
            raise ValueError("\n\n".join(error_messages))


if __name__ == "__main__":
    main()