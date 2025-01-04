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
from enum import Enum
from dataclasses import dataclass, field

import threading

from typing import Any, Optional

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

# --- Configurable Variables  ---
alpha_transparency_level = 0.95  # Set transparency (0.0 = fully transparent, 1.0 = fully opaque)
WINDOW_TITLE = "Simulator Time"
DARK_BG = "#000000"
FONT = ("Helvetica", 16)
UPDATE_INTERVAL = 1000  # in milliseconds
RECONNECT_INTERVAL = 1000  # in milliseconds

AUTO_UPDATE_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes in milliseconds

PADDING_X = 20  # Horizontal padding for each label
PADDING_Y = 10  # Vertical padding for the window

sm = None
aq = None
sim_connected = False

# --- Timer Variables  --
# Define epoch value to use as default value
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

@dataclass
class CountdownState:
    future_time_seconds: Optional[int] = None  # Time for countdown in seconds
    is_future_time_manually_set: bool = False  # Flag for manual setting
    last_simbrief_generated_time: Optional[datetime] = None  # Last SimBrief time
    last_entered_time: Optional[str] = None  # Last entered time in HHMM format
    gate_out_time: Optional[datetime] = None  # Store last game out time
    countdown_target_time: datetime = field(default_factory=lambda: UNIX_EPOCH)  # Default target time

    def set_target_time(self, new_time: datetime):
        """Set a new countdown target time with type validation."""
        if not isinstance(new_time, datetime):
            raise TypeError("countdown_target_time must be a datetime object")
        self.countdown_target_time = new_time

# --- SimBrief Data Structures  ---
class SimBriefTimeOption(Enum):
    ESTIMATED_IN = "Estimated In"
    ESTIMATED_TOD = "Estimated TOD"

@dataclass
class SimBriefSettings:
    username: str = ""
    use_adjusted_time: bool = False
    selected_time_option: SimBriefTimeOption = SimBriefTimeOption.ESTIMATED_IN
    allow_negative_timer: bool = False
    auto_update_enabled: bool = False  

    def to_dict(self):
        return {
            "username": self.username,
            "use_adjusted_time": self.use_adjusted_time,
            "selected_time_option": self.selected_time_option.value,
            "allow_negative_timer": self.allow_negative_timer,
            "auto_update_enabled": self.auto_update_enabled,
        }

    @staticmethod
    def from_dict(data):
        return SimBriefSettings(
            username=data.get("username", ""),
            use_adjusted_time=data.get("use_adjusted_time", False),
            selected_time_option=SimBriefTimeOption(data.get("selected_time_option", SimBriefTimeOption.ESTIMATED_IN.value)),
            allow_negative_timer=data.get("allow_negative_timer", False),
            auto_update_enabled=data.get("auto_update_enabled", False),
        )

# Declare gobal instances for shared data
countdown_state = CountdownState()
simbrief_settings = SimBriefSettings()

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

def get_time_to_future() -> str:
    """
    Calculate remaining time to the globally configured countdown target.
    Adjusts for simulator time acceleration if necessary.
    Returns the time difference as HH:MM:SS, optionally allowing negative values.
    """
    global countdown_state, simbrief_settings  # Access global settings and state

    if countdown_state.countdown_target_time == datetime(1970, 1, 1):  # Default unset state
        return "00:00:00"

    try:
        # Fetch current simulator time
        current_sim_time = get_simulator_datetime()

        # Ensure both times are timezone-aware (UTC)
        if countdown_state.countdown_target_time.tzinfo is None or current_sim_time.tzinfo is None:
            raise ValueError("Target time or simulator time is offset-naive. Ensure all times are offset-aware.")

        # Extract only the time components
        target_time_today = countdown_state.countdown_target_time.replace(
            year=current_sim_time.year, month=current_sim_time.month, day=current_sim_time.day
        )

        # Adjust for midnight rollover - Check if the countdown is for tomorrow
        if target_time_today < current_sim_time:
            target_time_today += timedelta(days=1)

        # Calculate remaining time
        remaining_time = target_time_today - current_sim_time

        # Adjust for simulation rate
        sim_rate = get_sim_rate()
        adjusted_seconds = (
            remaining_time.total_seconds() / float(sim_rate)
            if sim_rate and float(sim_rate) > 0
            else remaining_time.total_seconds()
        )

        # Allow or block negative time display based on settings
        if adjusted_seconds < 0 and not simbrief_settings.allow_negative_timer:
            return "00:00:00"

        # Format the adjusted remaining time as HH:MM:SS
        hours, remainder = divmod(abs(adjusted_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)

        # Add a negative sign if the remaining time is negative
        sign = "-" if adjusted_seconds < 0 else ""
        return f"{sign}{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

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

def get_simconnect_value(variable_name: str, default_value: Any = "N/A", retries: int = 10, retry_interval: float = 0.2) -> Any:
    """Fetch a SimConnect variable with caching and retry logic."""
    if not sim_connected or sm is None or not sm.ok:
        return "Sim Not Running"

    value = check_cache(variable_name)
    if value and value != default_value:
        return value

    add_to_cache(variable_name, default_value)
    for _ in range(retries):
        value = check_cache(variable_name)
        if value and value != default_value:
            return value
        time.sleep(retry_interval)

    print(f"DEBUG: All {retries} retries failed for '{variable_name}'. Returning default: {default_value}")
    return default_value

def check_cache(variable_name):
    """Return SimConnect cached value for variable if available, otherwise None."""
    with cache_lock:
        return simconnect_cache.get(variable_name)

def add_to_cache(variable_name, default_value="N/A"):
    """Add SimConnect variable to cache with default value and track it."""
    with cache_lock:
        simconnect_cache[variable_name] = default_value
        variables_to_track.add(variable_name)

def prefetch_variables(*variables, default_value="N/A"):
    """Prefetch variables by initializing them in the cache and tracking list."""
    with cache_lock:
        for variable_name in variables:
            if variable_name not in simconnect_cache:  # Ensure each variable is only added once
                simconnect_cache[variable_name] = default_value
                variables_to_track.add(variable_name)

def is_main_thread_blocked():
    main_thread = threading.main_thread()
    return not main_thread.is_alive() 

def simconnect_background_updater():
    """Background thread to update SimConnect variables with dynamic sleep adjustment."""
    global sim_connected, aq

    MIN_UPDATE_INTERVAL = 500  # in milliseconds, reduced interval for quick retries
    STANDARD_UPDATE_INTERVAL = UPDATE_INTERVAL  # Use existing global update interval

    while True:
        lookup_failed = False  # Flag to track if any variable lookup failed

        try:
            if not sim_connected:
                initialize_simconnect()
                continue

            if is_main_thread_blocked():
                print("DEBUG: Main thread is blocked. Retrying in 1 second.")
                time.sleep(1)
                continue

            if sim_connected:
                # Check to see if in flight
                if sm is None or not sm.ok or sm.quit == 1:
                    sim_connected = False
                    continue

                # Make a copy of the variables to avoid holding the lock during network calls
                with cache_lock:
                    vars_to_update = list(variables_to_track)

                for variable_name in vars_to_update:
                    try:
                        if aq is not None and hasattr(aq, 'get'): 
                            value = aq.get(variable_name)
                            if value is not None:  
                                with cache_lock:
                                    simconnect_cache[variable_name] = value
                            else:
                                print(f"DEBUG: Value for '{variable_name}' is None. Will retry in the next cycle.")
                                lookup_failed = True
                        else:
                            print(f"DEBUG: 'aq' is None or does not have a 'get' method.")
                            lookup_failed = True
                    except Exception as e:
                        print(f"DEBUG: Error fetching '{variable_name}': {e}. Will retry in the next cycle.")
                        lookup_failed = True
            else:
                print(f"DEBUG: SimConnect not connected. Retrying in {RECONNECT_INTERVAL}ms.")
                time.sleep(RECONNECT_INTERVAL / 1000.0)

        except OSError as os_err:
            print(f"DEBUG: OS error occurred: {os_err} - likely a connection issue.")
            sim_connected = False

        except Exception as e:
            print(f"DEBUG: Error in background updater: {e}")

        # Adjust sleep interval dynamically
        sleep_interval = MIN_UPDATE_INTERVAL if lookup_failed else STANDARD_UPDATE_INTERVAL
        time.sleep(sleep_interval / 1000.0)

def get_formatted_value(variable_names, format_string=None):
    """
    Fetch one or more SimConnect variables, apply optional formatting if provided.

    Parameters:
    - variable_names: The SimConnect variable name(s) to retrieve (can be a single name or a list).
    - format_string: An optional string format to apply to the retrieved values.

    Returns:
    - The formatted string, or an error message if retrieval fails.
    """

    if not sim_connected or sm is None or not sm.ok:
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

def get_simulator_datetime() -> datetime:
    """
    Fetch the current simulator date and time as a datetime object.
    Ensure it is simulator time and timezone-aware (UTC).
    If unavailable, return the Unix epoch as a default.
    """
    global sim_connected
    try:
        # Prefetch variables - may speed up access in some cases
        prefetch_variables("ZULU_YEAR", "ZULU_MONTH_OF_YEAR", "ZULU_DAY_OF_MONTH", "ZULU_TIME")

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
        return datetime(zulu_year, zulu_month, zulu_day, hours, minutes, seconds, tzinfo=timezone.utc)

    except ValueError as ve:
        #print(ve)
        pass
    except Exception as e:
        print(f"get_simulator_datetime: Failed to retrieve simulator datetime: {e}")

    # Return the Unix epoch if simulator time is unavailable
    return UNIX_EPOCH

def get_simulator_time_offset():
    """
    Calculate the offset between simulator time and real-world UTC time.
    Returns a timedelta representing the difference (simulator time - real-world time).
    """
    try:
        # Use a threshold for considering the offset as zero
        threshold = timedelta(seconds=5)
        simulator_time = get_simulator_datetime()
        real_world_time = datetime.now(timezone.utc)
        offset = simulator_time - real_world_time

        # Check if the offset is within the threshold
        if abs(offset) <= threshold:
            print(f"DEBUG: Offset {offset} is within threshold, assuming zero offset.")
            return timedelta(0)
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
    """Validates and sets a future time."""
    try:
        # Ensure all times are timezone-aware (UTC)
        if current_sim_time.tzinfo is None:
            current_sim_time = current_sim_time.replace(tzinfo=timezone.utc)

        if isinstance(future_time_input, datetime):
            # Validate that the future time is after the current simulator time
            if future_time_input <= current_sim_time:
                raise ValueError("Future time must be later than the current simulator time.")

            # Log successful setting of the timer
            print(f"Timer manually set to: {future_time_input}")
            return True
        else:
            raise TypeError("Unsupported future_time_input type. Must be a datetime object.")

    except ValueError as ve:
        print(f"Validation error in set_future_time_internal: {ve}")
    except Exception as e:
        print(f"DEBUG: Unexpected error in set_future_time_internal: {str(e)}")

def open_timer_dialog():
    """
    Open the CountdownTimerDialog to prompt the user to set a future countdown time and SimBrief settings.
    """
    try:
        # Open the dialog with current SimBrief settings and last entered time
        dialog = CountdownTimerDialog(
            root,
            simbrief_settings=simbrief_settings,
            initial_time=countdown_state.last_entered_time,
        )
        root.wait_window(dialog)  # Wait for the dialog to close
        # The dialog now handles all time and settings updates
    except Exception as e:
        messagebox.showerror("Error", f"Failed to open timer dialog: {str(e)}")

# --- Display Update  ---
def get_dynamic_value(function_name):
    """ Get a value dynamically from the function name. """
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
            return

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
class SimBriefFunctions:
    @staticmethod
    def get_latest_simbrief_ofp_json(username):
        """Fetch SimBrief OFP JSON data for the provided username."""
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

    @staticmethod
    def get_simbrief_ofp_gate_out_datetime(simbrief_json):
        """Fetch the scheduled gate out time (sched_out) as a datetime object."""
        if simbrief_json:
            try:
                if "times" in simbrief_json and "sched_out" in simbrief_json["times"]:
                    sched_out_epoch = int(simbrief_json["times"]["sched_out"])
                    return datetime.fromtimestamp(sched_out_epoch, tz=timezone.utc)
                else:
                    print("DEBUG: 'sched_out' not found in SimBrief JSON under 'times'.")
            except Exception as e:
                print(f"DEBUG: Error processing SimBrief gate out datetime: {e}")
        return None

    @staticmethod
    def get_simbrief_ofp_arrival_datetime(simbrief_json):
        """Fetch the estimated arrival time as a datetime object."""
        if simbrief_json:
            try:
                if "times" in simbrief_json and "est_in" in simbrief_json["times"]:
                    est_in_epoch = int(simbrief_json["times"]["est_in"])
                    return datetime.fromtimestamp(est_in_epoch, tz=timezone.utc)
                else:
                    print("DEBUG: 'est_in' not found in SimBrief JSON under 'times'.")
            except Exception as e:
                print(f"DEBUG: Error processing SimBrief arrival datetime: {e}")
        return None

    @staticmethod
    def get_simbrief_ofp_tod_datetime(simbrief_json):
        """Fetch the Top of Descent (TOD) time from SimBrief JSON data."""
        try:
            if "times" not in simbrief_json or "navlog" not in simbrief_json or "fix" not in simbrief_json["navlog"]:
                print("Invalid SimBrief JSON format.")
                return None

            sched_out_epoch = simbrief_json["times"].get("sched_out")
            if not sched_out_epoch:
                print("sched_out (gate out time) not found.")
                return None

            sched_out_epoch = int(sched_out_epoch)

            for waypoint in simbrief_json["navlog"]["fix"]:
                if waypoint.get("ident") == "TOD":
                    time_total_seconds = waypoint.get("time_total")
                    if not time_total_seconds:
                        print("time_total for TOD not found.")
                        return None

                    time_total_seconds = int(time_total_seconds)
                    tod_epoch = sched_out_epoch + time_total_seconds
                    return datetime.fromtimestamp(tod_epoch, tz=timezone.utc)

            print("TOD waypoint not found in the navlog.")
            return None
        except Exception as e:
            print(f"Error extracting TOD time: {e}")
            return None
    
    @staticmethod
    def update_countdown_from_simbrief(simbrief_json, simbrief_settings, gate_out_entry_value=None):
        """
        Update the countdown timer based on SimBrief data and optional manual gate-out time.
        """
        try:
            # Adjust gate-out time
            gate_time_offset = SimBriefFunctions.adjust_gate_out_delta(
                simbrief_json=simbrief_json,
                gate_out_entry_value=gate_out_entry_value,
                simbrief_settings=simbrief_settings,
            )

            # Fetch selected SimBrief time
            selected_time = simbrief_settings.selected_time_option
            if selected_time == SimBriefTimeOption.ESTIMATED_IN:
                future_time = SimBriefFunctions.get_simbrief_ofp_arrival_datetime(simbrief_json)
            elif selected_time == SimBriefTimeOption.ESTIMATED_TOD:
                future_time = SimBriefFunctions.get_simbrief_ofp_tod_datetime(simbrief_json)
            else:
                return False

            if not future_time:
                return False

            # Apply gate time offset and time adjustment
            future_time += gate_time_offset
            if simbrief_settings.use_adjusted_time:
                future_time = convert_real_world_time_to_sim_time(future_time)

            # Set countdown timer
            current_sim_time = get_simulator_datetime()
            if set_future_time_internal(future_time, current_sim_time):
                countdown_state.is_future_time_manually_set = gate_out_entry_value is not None
                countdown_state.set_target_time(future_time)
                return True

        except Exception as e:
            print(f"DEBUG: Exception in update_countdown_from_simbrief: {e}")
        return False


    @staticmethod
    def auto_update_simbrief(root):
        """
        Automatically fetch SimBrief data and update the countdown timer.
        """
        if not simbrief_settings.auto_update_enabled:
            return  # Exit if auto-update is disabled

        try:
            # Fetch SimBrief data
            simbrief_json = SimBriefFunctions.get_latest_simbrief_ofp_json(simbrief_settings.username)
            if simbrief_json:
                # Perform the update using the shared method
                success = SimBriefFunctions.update_countdown_from_simbrief(
                    simbrief_json=simbrief_json,
                    simbrief_settings=simbrief_settings,
                    gate_out_entry_value=None  # No manual entry for auto-update
                )
                if success:
                    print("DEBUG: Auto-update completed successfully.")
                else:
                    print("DEBUG: Auto-update failed.")
            else:
                print("DEBUG: Failed to fetch SimBrief data during auto-update.")
        except Exception as e:
            print(f"DEBUG: Exception during auto-update: {e}")

        # Schedule the next auto-update
        root.after(AUTO_UPDATE_INTERVAL_MS, lambda: SimBriefFunctions.auto_update_simbrief(root))

    @staticmethod
    def adjust_gate_out_delta(
        simbrief_json, gate_out_entry_value: Optional[str], simbrief_settings: SimBriefSettings
    ) -> timedelta:
        """
        Adjust the gate-out time based on SimBrief data and user-provided input.
        Returns the calculated gate time offset as a timedelta.
        """
        # Fetch SimBrief gate-out time
        simbrief_gate_time = SimBriefFunctions.get_simbrief_ofp_gate_out_datetime(simbrief_json)
        if not simbrief_gate_time:
            raise ValueError("SimBrief gate-out time not found.")

        print(f"DEBUG: UNALTERED SimBrief Gate Time: {simbrief_gate_time}")

        # Adjust SimBrief time for simulator context if required
        if simbrief_settings.use_adjusted_time:
            simulator_to_real_world_offset = get_simulator_time_offset()
            simbrief_gate_time += simulator_to_real_world_offset

        print(f"DEBUG: use_adjusted_time SimBrief Gate Time: {simbrief_gate_time}")

        # Save SimBrief gate-out time as the default
        countdown_state.gate_out_time = simbrief_gate_time

        # If user-provided gate-out time is available, calculate the offset
        if gate_out_entry_value:
            hours, minutes = int(gate_out_entry_value[:2]), int(gate_out_entry_value[2:])
            current_sim_time = get_simulator_datetime()
            user_gate_time_dt = current_sim_time.replace(hour=hours, minute=minutes, second=0, microsecond=0)

            # Handle next-day adjustment
            if user_gate_time_dt.time() < current_sim_time.time():
                user_gate_time_dt += timedelta(days=1)

            adjusted_delta = user_gate_time_dt - simbrief_gate_time

            print(f"DEBUG: Gate Adjustment calculation")
            print(f"DEBUG: user_gate_time_dt: {user_gate_time_dt}")
            print(f"DEBUG: simbrief_gate_time: {simbrief_gate_time}")
            print(f"DEBUG: adjusted_delta: {adjusted_delta}\n")

            # Save user-provided gate-out time
            countdown_state.gate_out_time = user_gate_time_dt
            return adjusted_delta

        # No user-provided gate-out time; use SimBrief defaults
        print("DEBUG: No user-provided gate-out time. Using SimBrief default gate-out time.")
        countdown_state.gate_out_time = None
        return timedelta(0)
    
    @staticmethod
    def set_countdown_timer_from_simbrief(
        simbrief_json, selected_time_option: SimBriefTimeOption, simbrief_settings: SimBriefSettings, gate_time_offset: timedelta
    ) -> Optional[datetime]:
        """
        Set the countdown timer based on SimBrief data, selected time option, and adjustments.
        Returns the adjusted countdown time or None on failure.
        """
        if selected_time_option == SimBriefTimeOption.ESTIMATED_IN:
            simbrief_time = SimBriefFunctions.get_simbrief_ofp_arrival_datetime(simbrief_json)
        elif selected_time_option == SimBriefTimeOption.ESTIMATED_TOD:
            simbrief_time = SimBriefFunctions.get_simbrief_ofp_tod_datetime(simbrief_json)
        else:
            raise ValueError("Invalid SimBrief time option.")

        if simbrief_time:
            print(f"DEBUG: Original SimBrief time: {simbrief_time}")

            if simbrief_settings.use_adjusted_time:
                simulator_to_real_world_offset = get_simulator_time_offset()
                simbrief_time += simulator_to_real_world_offset
                print(f"DEBUG: Adjusted SimBrief time: {simbrief_time}")

            adjusted_simbrief_time = simbrief_time + gate_time_offset
            print(f"DEBUG: Final SimBrief countdown time: {adjusted_simbrief_time}")
            return adjusted_simbrief_time

        return None

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
    save_settings({"x": root.winfo_x(), "y": root.winfo_y()}, simbrief_settings)

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
                data = json.load(f)
                # Load SimBrief settings
                if "simbrief_settings" in data:
                    simbrief_settings = SimBriefSettings.from_dict(data["simbrief_settings"])
                else:
                    simbrief_settings = SimBriefSettings()
                return data, simbrief_settings
        except json.JSONDecodeError:
            print("Error: Settings file is corrupted. Using defaults.")
    return {"x": 0, "y": 0}, SimBriefSettings()  # Default position and settings

def save_settings(settings, simbrief_settings):
    """Save settings to the JSON file."""
    try:
        settings["simbrief_settings"] = simbrief_settings.to_dict()
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Error saving settings: {e}")

def main():
    global root, display_frame, simbrief_settings

    # --- Load initial settings ---
    settings, simbrief_settings_loaded = load_settings()
    simbrief_settings = simbrief_settings_loaded
    initial_x = settings.get("x", 0)
    initial_y = settings.get("y", 0)
    print(f"Loaded window position - x: {initial_x}, y: {initial_y}")

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
    root.bind("<Double-1>", lambda event: open_timer_dialog())

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

class CountdownTimerDialog(tk.Toplevel):
    """A dialog to set the countdown timer and SimBrief settings"""
    def __init__(self, parent, simbrief_settings: SimBriefSettings, initial_time=None, gate_out_time=None):
        super().__init__(parent)
        
        self.simbrief_settings = simbrief_settings

        # Remove the native title bar
        self.overrideredirect(True)

        # Ensure the window is visible before further actions
        self.wait_visibility()

        # Fix focus and interaction issues
        self.transient(parent)  # Keep the dialog on top of the parent
        self.grab_set()  # Prevent interaction with other windows

        # Window size and positioning
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        self.geometry(f"+{parent_x}+{parent_y}")  

        # Dark mode colors
        self.bg_color = "#2E2E2E"  # Dark background
        self.fg_color = "#FFFFFF"  # Light text
        self.entry_bg_color = "#3A3A3A"  # Slightly lighter background for entries
        self.entry_fg_color = "#FFFFFF"  # Text color for entries
        self.button_bg_color = "#5A5A5A"  # Dark button background
        self.button_fg_color = "#FFFFFF"  # Light button text
        self.title_bar_bg = "#1E1E1E"  # Darker background for title bar

        self.configure(bg=self.bg_color)  # Apply dark background to the dialog

        self.create_title_bar()

        # Font variables
        small_font = ("Helvetica", 10)
        large_font = ("Helvetica", 14)

        # Countdown Time Input
        countdown_frame = tk.Frame(self, bg=self.bg_color)
        countdown_frame.pack(pady=10, anchor="w")
        tk.Label(countdown_frame, text="Enter Countdown Time (HHMM):", bg=self.bg_color, fg=self.fg_color,
                font=large_font).pack(side="left", padx=5)
        self.time_entry = tk.Entry(countdown_frame, justify="center", bg=self.entry_bg_color, fg=self.entry_fg_color,
                                    font=("Helvetica", 16), width=10)  # Larger font for the entry
        if initial_time:
            self.time_entry.insert(0, initial_time)
        self.time_entry.pack(side="left", padx=5)
        
        # Add simbrief section (with collapsable section)
        self.build_simbrief_section(self, small_font)

        # OK and Cancel Buttons
        button_frame = tk.Frame(self, bg=self.bg_color)
        button_frame.pack(pady=20)
        tk.Button(button_frame, text="OK", command=self.on_ok, bg=self.button_bg_color, fg=self.button_fg_color,
                activebackground=self.entry_bg_color, activeforeground=self.fg_color, font=small_font, width=10
                ).pack(side="left", padx=5)

        tk.Button(button_frame, text="Cancel", command=self.on_cancel, bg=self.button_bg_color, fg=self.button_fg_color,
                activebackground=self.entry_bg_color, activeforeground=self.fg_color, font=small_font, width=10
                ).pack(side="right", padx=5)

        # Bind Enter to OK button
        self.bind("<Return>", lambda event: self.on_ok())

        # Ensure the window is always on top
        self.attributes("-topmost", True)

        # Capture the original position and offset
        parent_x = self.winfo_rootx()
        parent_y = self.winfo_rooty()
        x = parent_x + 50
        y = parent_y + 50

        # Reapply geometry with the offset after setting topmost
        self.geometry(f"+{x}+{y}")

        # Ensure the dialog gets focus
        self.focus_force()
        self.time_entry.focus_set()

    def create_title_bar(self):
        """Create a custom title bar for the dialog."""
        # Custom Title Bar
        self.title_bar = tk.Frame(self, bg=self.title_bar_bg, relief="flat", height=30)
        self.title_bar.pack(side="top", fill="x")

        # Title Label
        self.title_label = tk.Label(self.title_bar, text="Set Countdown Timer and SimBrief Settings",
                                    bg=self.title_bar_bg, fg=self.fg_color, font=("Helvetica", 10, "bold"))
        self.title_label.pack(side="left", padx=10)

        # Close Button
        self.close_button = tk.Button(self.title_bar, text="✕", command=self.on_cancel, bg=self.title_bar_bg,
                                    fg=self.fg_color, relief="flat", font=("Helvetica", 10, "bold"),
                                    activebackground="#FF0000", activeforeground=self.fg_color)
        self.close_button.pack(side="right", padx=5)

        # Bind dragging to the title bar
        self.title_bar.bind("<Button-1>", self.start_move)
        self.title_bar.bind("<B1-Motion>", self.do_move)

        # Propagate binds to children
        for widget in self.title_bar.winfo_children():
            widget.bind("<Button-1>", self.start_move)
            widget.bind("<B1-Motion>", self.do_move)

    def build_simbrief_section(self, parent, small_font):
        """Create a collapsible SimBrief section."""
        # Create a collapsible section for SimBrief
        simbrief_section = CollapsibleSection(
            parent,
            "SimBrief Settings",
            lambda frame: self.simbrief_content(
                frame,
                small_font,
                self.simbrief_settings.username,
                self.simbrief_settings.use_adjusted_time,
                countdown_state.gate_out_time,  # Pass the current gate-out time
            ),
        )
        simbrief_section.pack(fill="x", padx=10, pady=5)

        # Expand section if SimBrief username exists
        if self.simbrief_settings.username.strip():
            simbrief_section.expand()

    def simbrief_content(self, frame, small_font, simbrief_username, use_simbrief_adjusted_time, gate_out_time):
        """Build the SimBrief components inside the collapsible section."""
        border_color = "#444444"

        # Outer Frame for Padding
        outer_frame = tk.Frame(frame, bg=self.bg_color)
        outer_frame.pack(fill="x", padx=10, pady=0) 

        # SimBrief Username and Gate Out Time Group
        input_frame = tk.Frame(outer_frame, bg=self.bg_color)
        input_frame.pack(fill="x", pady=2) 

        # SimBrief Username
        tk.Label(
            input_frame, text="SimBrief Username:", bg=self.bg_color, fg=self.fg_color, font=small_font
        ).grid(row=0, column=0, sticky="w", padx=5, pady=2) 

        self.simbrief_entry = tk.Entry(
            input_frame, justify="left", bg=self.entry_bg_color, fg=self.entry_fg_color, font=small_font, width=25
        )
        if simbrief_username:
            self.simbrief_entry.insert(0, simbrief_username)
        self.simbrief_entry.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # Gate Out Time
        tk.Label(
            input_frame, text="Gate Out Time (HHMM):", bg=self.bg_color, fg=self.fg_color, font=small_font
        ).grid(row=1, column=0, sticky="w", padx=5, pady=2) 

        self.gate_out_entry = tk.Entry(
            input_frame, justify="left", bg=self.entry_bg_color, fg=self.entry_fg_color, font=small_font, width=25
        )
        if gate_out_time:
            self.gate_out_entry.insert(0, gate_out_time.strftime("%H%M"))
        self.gate_out_entry.grid(row=1, column=1, sticky="w", padx=5, pady=2) 

        # Checkbox for SimBrief Time Translation
        self.simbrief_checkbox_var = tk.BooleanVar(value=use_simbrief_adjusted_time)
        self.simbrief_checkbox = tk.Checkbutton(
            input_frame,
            text="Translate SimBrief Time to Simulator Time",
            variable=self.simbrief_checkbox_var,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.entry_bg_color,
            font=small_font,
        )
        self.simbrief_checkbox.grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        # Checkbox for allowing negative timer
        self.negative_timer_checkbox_var = tk.BooleanVar(value=simbrief_settings.allow_negative_timer)
        self.negative_timer_checkbox = tk.Checkbutton(
            input_frame,
            text="Allow Negative Timer",
            variable=self.negative_timer_checkbox_var,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.entry_bg_color,
            font=small_font,
        )
        self.negative_timer_checkbox.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=2) 

        # Add checkbox for enabling/disabling auto updates
        self.auto_update_var = tk.BooleanVar(value=simbrief_settings.auto_update_enabled)
        self.auto_update_checkbox = tk.Checkbutton(
            input_frame,
            text="Enable Auto SimBrief Updates",
            variable=self.auto_update_var,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.entry_bg_color,
            font=small_font,
        )
        self.auto_update_checkbox.grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=2)

        # Add separation before SimBrief Time Selection
        separator_frame = tk.Frame(outer_frame, bg=self.bg_color, height=5)  
        separator_frame.pack(fill="x", pady=2)  

        # SimBrief Time Selection Group
        time_selection_frame = tk.Frame(outer_frame, bg=self.bg_color)
        time_selection_frame.pack(fill="x", pady=2, anchor="w")  

        tk.Label(
            time_selection_frame, text="Select SimBrief Time:", bg=self.bg_color, fg=self.fg_color, font=small_font
        ).grid(row=0, column=0, sticky="w", padx=5, pady=2)  

        self.selected_time_option = tk.StringVar(value=self.simbrief_settings.selected_time_option.value)
        self.time_dropdown = tk.OptionMenu(
            time_selection_frame,
            self.selected_time_option,
            *[option.value for option in SimBriefTimeOption],  # Use the enum values for options
        )
        self.time_dropdown.configure(bg=self.entry_bg_color, fg=self.entry_fg_color, highlightthickness=0, font=small_font)
        self.time_dropdown["menu"].configure(bg=self.entry_bg_color, fg=self.fg_color)
        self.time_dropdown.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        pull_time_button = tk.Button(
            time_selection_frame,
            text="Get Time",
            command=self.pull_time,
            bg=self.button_bg_color,
            fg=self.button_fg_color,
            activebackground=self.entry_bg_color,
            activeforeground=self.fg_color,
            font=small_font,
        )
        pull_time_button.grid(row=0, column=2, sticky="w", padx=5, pady=2)

    def get_default_gate_out_time(self):
        """
        Fetch the default gate-out time (sched_out) from SimBrief JSON.
        """
        try:
            simbrief_json = SimBriefFunctions.get_latest_simbrief_ofp_json(self.simbrief_settings.username)
            if not simbrief_json:
                print("DEBUG: Failed to fetch SimBrief JSON.")
                return None
            return SimBriefFunctions.get_simbrief_ofp_gate_out_datetime(simbrief_json)
        except Exception as e:
            print(f"Error fetching default gate-out time: {e}")
            return None

    def on_cancel(self):
        """Cancel the dialog."""
        self.result = None
        self.destroy()

    def on_ok(self):
        """
        Validate user input, update SimBrief settings, and set the countdown timer if time is provided.
        """
        global countdown_state, simbrief_settings

        try:
            print("DEBUG: on_ok---------------------------")

            # Update SimBrief settings from dialog inputs
            self.update_simbrief_settings()

            # Save SimBrief settings regardless of whether a username is provided
            save_settings(load_settings()[0], simbrief_settings)

            # Handle the time input
            time_text = self.time_entry.get().strip()
            if time_text:
                if not self.validate_time_format(time_text):
                    messagebox.showerror("Invalid Input", "Please enter time in HHMM format.")
                    return

                future_time = self.calculate_future_time(time_text)
                if not self.set_countdown_timer(future_time):
                    messagebox.showerror("Error", "Failed to set the countdown timer.")
                    return

            # Close the dialog
            self.result = {"time": time_text}
            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")

    def pull_time(self):
        """
        Pull the selected time from SimBrief and update the countdown timer.
        """
        try:
            print("DEBUG: pull_time started")

            # Update SimBrief settings from the dialog inputs
            self.update_simbrief_settings()

            # Persist the updated SimBrief settings
            save_settings(load_settings()[0], simbrief_settings)

            # Validate the SimBrief username
            if not self.validate_simbrief_username():
                print("DEBUG: Invalid SimBrief username. Exiting pull_time.")
                return

            # Fetch SimBrief data
            simbrief_json = SimBriefFunctions.get_latest_simbrief_ofp_json(simbrief_settings.username)
            if not simbrief_json:
                messagebox.showerror("Error", "Failed to fetch SimBrief data. Please check your username.")
                print("DEBUG: SimBrief data fetch failed.")
                return

            # Get manual gate-out time entry, if provided
            gate_out_entry_value = self.gate_out_entry.get().strip() if self.gate_out_entry else None

            # Update countdown timer using the shared method
            success = SimBriefFunctions.update_countdown_from_simbrief(
                simbrief_json=simbrief_json,
                simbrief_settings=simbrief_settings,
                gate_out_entry_value=gate_out_entry_value
            )

            if not success:
                messagebox.showerror("Error", "Failed to update the countdown timer from SimBrief.")
                print("DEBUG: Countdown timer update failed.")
                return

            print("DEBUG: Countdown timer updated successfully from SimBrief.")
            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")
            print(f"DEBUG: Exception in pull_time: {e}")

    def update_simbrief_settings(self):
        """Update SimBrief settings from dialog inputs."""
        simbrief_settings.username = self.simbrief_entry.get().strip()
        simbrief_settings.use_adjusted_time = self.simbrief_checkbox_var.get()
        simbrief_settings.selected_time_option = SimBriefTimeOption(self.selected_time_option.get())
        simbrief_settings.allow_negative_timer = self.negative_timer_checkbox_var.get()  
        simbrief_settings.auto_update_enabled = self.auto_update_var.get()

    def validate_simbrief_username(self):
        """Validate SimBrief username and show an error if invalid."""
        if not simbrief_settings.username:
            messagebox.showerror("Error", "Please enter a SimBrief username.")
            return False
        return True

    def fetch_simbrief_data(self):
        """Fetch and return SimBrief JSON data."""
        simbrief_json = SimBriefFunctions.get_latest_simbrief_ofp_json(simbrief_settings.username)
        if not simbrief_json:
            messagebox.showerror("Error", "Failed to fetch SimBrief data. Please check the username or try again.")
            return None
        return simbrief_json

    def calculate_future_time(self, time_text):
        """
        Convert HHMM time input into a datetime object.
        Adjust for the next day if the entered time is earlier than the current simulator time.
        """
        hours, minutes = int(time_text[:2]), int(time_text[2:])
        current_sim_time = get_simulator_datetime()
        future_time = datetime(
            year=current_sim_time.year,
            month=current_sim_time.month,
            day=current_sim_time.day,
            hour=hours,
            minute=minutes,
            tzinfo=timezone.utc
        )

        if future_time < current_sim_time:
            future_time += timedelta(days=1)

        return future_time

    def set_countdown_timer(self, future_time):
        """
        Set the countdown timer and update global state.
        """
        global countdown_state
        current_sim_time = get_simulator_datetime()

        if set_future_time_internal(future_time, current_sim_time):
            countdown_state.is_future_time_manually_set = True
            countdown_state.set_target_time(future_time)
            return True
        return False

    @staticmethod
    def validate_time_format(time_text):
        """Validate time format (HHMM)."""
        if len(time_text) != 4 or not time_text.isdigit():
            return False
        hours, minutes = int(time_text[:2]), int(time_text[2:])
        return 0 <= hours < 24 and 0 <= minutes < 60

    def start_move(self, event):
        """Start dragging the window."""
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def do_move(self, event):
        """Handle dragging the window."""
        x = self.winfo_x() + event.x - self._drag_start_x
        y = self.winfo_y() + event.y - self._drag_start_y
        self.geometry(f"+{x}+{y}")

class CollapsibleSection(tk.Frame):
    """A collapsible Tkinter section with a toggle button and content frame."""
    def __init__(self, parent, title, content_builder, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        # Colors
        self.bg_color = "#2E2E2E"
        self.fg_color = "#FFFFFF"
        self.border_color = "#444444"

        # Frame styling to reduce white padding
        self.configure(bg=self.bg_color, highlightbackground=self.border_color, highlightthickness=1)

        # Toggle button (with an arrow)
        self.toggle_button = tk.Button(
            self, text="▲ " + title, command=self.toggle, bg=self.bg_color, fg=self.fg_color,
            anchor="w", relief="flat", font=("Helvetica", 12), bd=0
        )
        self.toggle_button.pack(fill="x", pady=2, padx=2)

        # Frame to hold the content
        self.content_frame = tk.Frame(self, bg=self.bg_color, highlightthickness=0)
        self.content_frame.pack(fill="x", padx=2, pady=2)

        # Build the content using the provided function
        content_builder(self.content_frame)

        # Initial collapsed state
        self.collapsed = True
        if self.collapsed:
            self.collapse()

    def toggle(self):
        """Toggle visibility of the content frame."""
        if self.collapsed:
            self.expand()
        else:
            self.collapse()
        self.collapsed = not self.collapsed

    def collapse(self):
        """Collapse the section."""
        self.content_frame.pack_forget()
        self.toggle_button.config(text="▼ " + self.toggle_button.cget("text")[2:])

    def expand(self):
        """Expand the section."""
        self.content_frame.pack(fill="x", padx=2, pady=2)
        self.toggle_button.config(text="▲ " + self.toggle_button.cget("text")[2:])

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