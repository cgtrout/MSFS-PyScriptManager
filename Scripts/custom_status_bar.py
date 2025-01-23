# custom_status_bar.py: shows a draggable, customizable status bar using SimConnect to display real-time flight simulator metrics like time, altitude, and temperature in a compact GUI.
#   - use instructions below to customize
#   - Uses https://github.com/odwdinc/Python-SimConnect library to obtain values from SimConnect


import faulthandler
import tkinter as tk
from tkinter import messagebox
from SimConnect import SimConnect, AircraftRequests
from datetime import datetime, timezone, timedelta
import os
import json
import importlib
import requests
import time
from enum import Enum
from dataclasses import dataclass, field

import threading
import sys
import traceback
from typing import Any, Optional


try:
    # Import all color print functions
    from Lib.color_print import *

except ImportError:
    print("Failed to import 'Lib.color_print'. Please ensure /Lib/color_print.py is present")
    sys.exit(1)

# Print initial message
print("custom_status_bar: Close this window to close status bar")

# Default templates file - this will be created if it doesn't exist
# in the settings directory as /Settings/status_bar_templates.py
#
# ALL template modification should be done from  /Settings/status_bar_templates.py
DEFAULT_TEMPLATES = """
#  TEMPLATE DOCUMENTATION
# ====================================
#  Template string below defines the content and format of the data shown in the application's window,
#  including dynamic data elements such as:
# ('VAR()' and 'VARIF()' 'functions') and static text.

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

# Define your templates here in the TEMPLATES dictionary.

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

# This shows how you can also define your own functions to fetch dynamic values.
# Functions defined here will be imported so they can be referenced
# PLANE_ALTITUDE is a SimConnect variable
# Further SimConnect variables can be found at https://docs.flightsimulator.com/html/Programming_Tools/SimVars/Simulation_Variables.htm
def get_altitude():
    return get_formatted_value("PLANE_ALTITUDE", "{:.0f} ft")

## USER FUNCTIONS ##
# The following functions are hooks for user-defined behaviors and will be called by the
# custom_status_bar script.

# Runs once per display update (approx. 30 times per second).
def user_update():
    pass

# Runs approx every 500ms for less frequent, CPU-intensive tasks.
def user_slow_update():
    pass

# Runs once during startup for initialization tasks.
def user_init():
    pass
"""
# --- Configurable Variables  ---
ALPHA_TRANSPARENCY_LEVEL = 0.95  # Set transparency (0.0 = fully transparent, 1.0 = fully opaque)
WINDOW_TITLE = "Simulator Time"
DARK_BG = "#000000"
FONT = ("Helvetica", 16)
UPDATE_INTERVAL = 33  # in milliseconds

SIMBRIEF_AUTO_UPDATE_INTERVAL_MS = 5 * 60 * 1000  # 5 minutes in milliseconds
USER_UPDATE_FUNCTION_DEFINED = False
USER_SLOW_UPDATE_FUNCTION_DEFINED = False

PADDING_X = 20  # Horizontal padding for each label
PADDING_Y = 10  # Vertical padding for the window

sim_connect = None
aircraft_requests = None
sim_connected = False

log_file_path = "traceback.log"
traceback_log_file = open(log_file_path, "w")
faulthandler.enable(file=traceback_log_file)

# --- Timer Variables  ---
# Define epoch value to use as default value
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

@dataclass
class CountdownState:
    future_time_seconds: Optional[int] = None  # Time for countdown in seconds
    is_future_time_manually_set: bool = False  # Flag for manual setting
    last_simbrief_generated_time: Optional[datetime] = None  # Last SimBrief time
    last_entered_time: Optional[str] = None  # Last entered time in HHMM format
    gate_out_time: Optional[datetime] = None  # Store last game out time
    countdown_target_time: datetime = field(default_factory=lambda: UNIX_EPOCH)
    last_countdown_time: Optional[float] = None  # Track last countdown time in seconds
    is_negative: bool = False  # Track if the countdown has gone negative

    def set_target_time(self, new_time: datetime):
        """Set a new countdown target time with type validation."""
        if not isinstance(new_time, datetime):
            raise TypeError("countdown_target_time must be a datetime object")
        self.countdown_target_time = new_time

    def reset(self):
        """Reset relevant countdown-related state variables."""
        self.last_countdown_time = None
        self.is_negative = False

# --- SimBrief Data Structures  ---
class SimBriefTimeOption(Enum):
    ESTIMATED_IN = "Estimated In"
    ESTIMATED_TOD = "Estimated TOD"

@dataclass
class SimBriefSettings:
    username: str = ""
    use_adjusted_time: bool = False
    selected_time_option: Any = SimBriefTimeOption.ESTIMATED_IN
    allow_negative_timer: bool = False
    auto_update_enabled: bool = False

    def to_dict(self):
        return {
            "username": self.username,
            "use_adjusted_time": self.use_adjusted_time,
            "selected_time_option": (
                self.selected_time_option.value
                if isinstance(self.selected_time_option, SimBriefTimeOption)
                else SimBriefTimeOption.ESTIMATED_IN.value
            ),
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

# --- Globals  ---
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

def get_simulator_datetime() -> datetime:
    """
    Fetches the absolute time from the simulator and converts it to a datetime object.
    """
    global sim_connected
    try:
        if not sim_connected:
            raise ValueError("SimConnect is not connected.")

        absolute_time = get_simconnect_value("ABSOLUTE_TIME")
        if absolute_time is None:
            raise ValueError("Absolute time is unavailable.")

        base_datetime = datetime(1, 1, 1, tzinfo=timezone.utc)
        return base_datetime + timedelta(seconds=float(absolute_time))

    except ValueError as ve:
        #print(ve)
        pass
    except Exception as e:
        print(f"get_simulator_datetime: Failed to retrieve simulator datetime: {e}")

    # Return the Unix epoch if simulator time is unavailable
    return UNIX_EPOCH

def get_simulator_datetime_old() -> datetime:
    """
    Fetch the current simulator date and time as a datetime object.
    Ensure it is simulator time and timezone-aware (UTC).
    If unavailable, return the Unix epoch as a default.
    """
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

def get_real_world_time():
    """Fetch the real-world Zulu time."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def get_sim_rate():
    """Fetch the sim rate from SimConnect."""
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

def initialize_simconnect():
    """Initialize the connection to SimConnect."""
    global sim_connect, aircraft_requests, sim_connected
    try:
        sim_connect = SimConnect()  # Connect to SimConnect
        aircraft_requests = AircraftRequests(sim_connect, _time=0)
        sim_connected = True
    except Exception:
        sim_connected = False

def get_simconnect_value(variable_name: str, default_value: Any = "N/A",
                         retries: int = 10, retry_interval: float = 0.2) -> Any:
    """Fetch a SimConnect variable with caching and retry logic."""
    if not sim_connected or sim_connect is None or not sim_connect.ok:
        return "Sim Not Running"

    value = check_cache(variable_name)
    if value and value != default_value:
        return value

    add_to_cache(variable_name, default_value)
    for _ in range(retries):
        value = check_cache(variable_name)
        if value is not None and value != default_value:
            return value
        time.sleep(retry_interval)

    print_debug(
        f"All {retries} retries failed for '{variable_name}'. "
        f"Returning default: {default_value}"
    )
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

def get_formatted_value(variable_names, format_string=None):
    """
    Fetch one or more SimConnect variables, apply optional formatting if provided.

    Parameters:
    - variable_names: The SimConnect variable name(s) to retrieve (can be a single name or a list).
    - format_string: An optional string format to apply to the retrieved values.

    Returns:
    - The formatted string, or an error message if retrieval fails.
    """

    if not sim_connected or sim_connect is None or not sim_connect.ok:
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

# --- Background Updater ---
VARIABLE_SLEEP = 0.01  # Sleep for 10ms between each variable looku
MIN_UPDATE_INTERVAL = UPDATE_INTERVAL / 2  # Reduced interval for retry cycles (in milliseconds
STANDARD_UPDATE_INTERVAL = UPDATE_INTERVAL  # Normal interval for successful cycles

last_successful_update_time = time.time()
def simconnect_background_updater():
    """Background thread to update SimConnect variables with small sleep between updates."""
    global sim_connected, last_successful_update_time

    while True:
        lookup_failed = False  # Track if any variable lookup failed

        try:
            if not sim_connected:
                initialize_simconnect()
                continue

            if sim_connected:
                if sim_connect is None or not sim_connect.ok or sim_connect.quit == 1:
                    print_warning("SimConnect state invalid. Disconnecting.")
                    sim_connected = False
                    continue

                # Make a copy of the variables to avoid holding the lock during network calls
                with cache_lock:
                    vars_to_update = list(variables_to_track)

                for variable_name in vars_to_update:
                    try:
                        if aircraft_requests is not None and hasattr(aircraft_requests, 'get'):
                            value = aircraft_requests.get(variable_name)
                            if value is not None:
                                with cache_lock:
                                    simconnect_cache[variable_name] = value
                            else:
                                lookup_failed = True
                        else:
                            print_warning("'aq' is None or does not have a 'get' method.")
                            lookup_failed = True
                    except OSError as e:
                        print_debug(f"Error fetching '{variable_name}': {e}. "
                                     "Will retry in the next cycle.")
                        lookup_failed = True

                    # Introduce a small sleep between variable updates
                    time.sleep(VARIABLE_SLEEP)

            else:
                print_warning("SimConnect not connected. Retrying in 1 second.")
                time.sleep(1)

            # Adjust sleep interval dynamically
            sleep_interval = MIN_UPDATE_INTERVAL if lookup_failed else STANDARD_UPDATE_INTERVAL
            time.sleep(sleep_interval / 1000.0)

        except Exception as e:
            print_error(f"Unexpected error in background updater: {e}")
            print(f"Exception type: {type(e).__name__}")
        finally:
            # Update the last successful update time - used for 'heartbeat' functionality
            last_successful_update_time = time.time()

def background_thread_watchdog_function():
    """Check background thread function to see if it has locked up"""
    now = time.time()
    threshold = 30  # seconds before we consider the updater "stuck"

    if now - last_successful_update_time > threshold:
        print_error(f"Watchdog: Background updater has not completed a cycle in {int(now - last_successful_update_time)} seconds. Possible stall detected.")

    # Reschedule the watchdog to run again after 10 seconds
    root.after(10_000, background_thread_watchdog_function)

# --- Timer Calcuation  ---
def get_time_to_future_adjusted():
    """
    Calculate and return the countdown timer string.
    """
    return get_time_to_future(adjusted_for_sim_rate=True)

def get_time_to_future_unadjusted():
    """
    Calculate and return the countdown timer string without adjusting for sim rate.
    """
    return get_time_to_future(adjusted_for_sim_rate=False)

def get_time_to_future(adjusted_for_sim_rate: bool) -> str:
    """
    Calculate and return the countdown timer string.
    """
    global countdown_state

    if countdown_state.countdown_target_time == UNIX_EPOCH:  # Default unset state
        return "N/A"

    try:
        current_sim_time = get_simulator_datetime()

        if countdown_state.countdown_target_time.tzinfo is None or current_sim_time.tzinfo is None:
            raise ValueError("Target time or simulator time is offset-naive. "
                             "Ensure all times are offset-aware.")

        # Fetch sim rate if we want to adjust for it, otherwise default to 1.0 (normal time progression)
        sim_rate = 1.0
        if adjusted_for_sim_rate:
            sim_rate_str = get_sim_rate()
            sim_rate = float(sim_rate_str) if sim_rate_str.replace('.', '', 1).isdigit() else 1.0

        # Compute the count-down time
        countdown_str, new_last_time, new_is_neg = compute_countdown_timer(
            current_sim_time=current_sim_time,
            target_time=countdown_state.countdown_target_time,
            last_countdown_time=countdown_state.last_countdown_time,
            is_negative=countdown_state.is_negative,
            sim_rate=sim_rate,
        )

        # Update state
        countdown_state.last_countdown_time = new_last_time
        countdown_state.is_negative = new_is_neg

        return countdown_str

    except Exception as e:
        # TODO: investigate if we can handle errors better here
        exception_type = type(e).__name__  # Get the exception type
        print(f"Exception occurred: {e} (Type: {exception_type})")
        return "N/A"

def compute_countdown_timer(
    current_sim_time: datetime,
    target_time: datetime,
    last_countdown_time: Optional[float],
    is_negative: bool,
    sim_rate: float,
    negative_timer_threshold: timedelta = timedelta(hours=-2),
) -> tuple[str, float, bool]:
    """
    Compute the countdown timer string and update its state.

    Parameters:
    - current_sim_time (datetime): Current simulator time.
    - target_time (datetime): Target countdown time.
    - last_countdown_time (Optional[float]): Previously stored countdown time in seconds.
    - is_negative (bool): Whether the last countdown was negative.
    - sim_rate (float): Simulation rate.

    Returns:
    - countdown_str (str): Formatted countdown string "HH:MM:SS".
    - new_last_countdown_time (float): Updated absolute countdown time in seconds.
    - new_is_negative (bool): Whether the countdown has gone negative.
    """
    # Replace date for same-day calculation
    target_time_today = target_time.replace(
        year=current_sim_time.year, month=current_sim_time.month, day=current_sim_time.day
    )

    # Handle midnight rollover logic
    if target_time_today < current_sim_time:
        #print_debug("Target time is earlier than current simulator time.")
        if not is_negative and (last_countdown_time is None or last_countdown_time > 5):
            if target_time_today - current_sim_time < negative_timer_threshold:
                #print_debug("Midnight rollover detected. Adjusting target time to next day.")
                target_time_today += timedelta(days=1)

    # Calculate remaining time
    remaining_time = target_time_today - current_sim_time

    # Adjust for simulation rate
    if sim_rate and sim_rate > 0:
        adjusted_seconds = remaining_time.total_seconds() / sim_rate
    else:
        adjusted_seconds = remaining_time.total_seconds()

    # Enforce allow_negative_timer setting
    if not simbrief_settings.allow_negative_timer and adjusted_seconds < 0:
        adjusted_seconds = 0

    # Update internal tracking
    new_last_countdown_time = abs(remaining_time.total_seconds())
    new_is_negative = remaining_time.total_seconds() < 0

    # Format the adjusted remaining time as HH:MM:SS
    total_seconds = int(adjusted_seconds)
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    countdown_str = f"{sign}{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    return countdown_str, new_last_countdown_time, new_is_negative

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
            print_debug(f"Offset {offset} is within threshold, assuming zero offset.")
            return timedelta(0)
        print_debug(f"Simulator Time Offset: {offset}")
        return offset
    except Exception as e:
        print_error(f"Error calculating simulator time offset: {e}")
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
        print_debug(f"Converted Real-World Time {real_world_time} to Sim Time {sim_time}")
        return sim_time
    except Exception as e:
        print_error(f"Error converting real-world time to sim time: {e}")
        return real_world_time  # Return the original time as fallback

def set_future_time_internal(future_time_input, current_sim_time):
    """Validates and sets a future time."""
    try:
        # Ensure all times are timezone-aware (UTC)
        if current_sim_time.tzinfo is None:
            current_sim_time = current_sim_time.replace(tzinfo=timezone.utc)

        if isinstance(future_time_input, datetime):
            # Validate that the future time is after the current simulator time
            if future_time_input <= current_sim_time and not simbrief_settings.allow_negative_timer:
                raise ValueError("Future time must be later than the current simulator time.")

            countdown_state.reset()

            # Log successful setting of the timer
            print(f"Timer set to: {future_time_input}")
            return True
        else:
            raise TypeError("Unsupported future_time_input type. Must be a datetime object.")

    except ValueError as ve:
        print_error(f"Validation error in set_future_time_internal: {ve}")
    except Exception as e:
        print_error(f"Unexpected error in set_future_time_internal: {str(e)}")

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

# --- Template handling  ---
@dataclass
class TemplateHandler:
    """Class to manage the template file and selected template."""
    templates: dict[str, str] = field(init=False, default_factory=dict)
    selected_template_name: Optional[str] = None
    cached_parsed_blocks: list = field(init=False, default_factory=list)
    pending_template_change: bool = field(init=False, default=False)
    parser: "TemplateParser" = field(init=False)

    def __post_init__(self):
        """Initialize templates and set the default selection."""
        self.parser = TemplateParser()  # Initialize the parser
        self.templates = self.load_templates()
        self.load_template_functions()
        self.selected_template_name = next(iter(self.templates), None)
        if not self.selected_template_name:
            raise ValueError("No templates available to select.")

        # Initially cache the parsed blocks for the first template
        self.cache_parsed_blocks()

    def load_templates(self) -> dict[str, str]:
        """Load templates from the template file, creating the file if necessary."""
        os.makedirs(SETTINGS_DIR, exist_ok=True)

        if not os.path.exists(TEMPLATE_FILE):
            with open(TEMPLATE_FILE, "w") as f:
                f.write(DEFAULT_TEMPLATES.strip())
            print(f"Created default template file at {TEMPLATE_FILE}")

        try:
            spec = importlib.util.spec_from_file_location("status_bar_templates", TEMPLATE_FILE)
            templates_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(templates_module)
            return templates_module.TEMPLATES if hasattr(templates_module, "TEMPLATES") else {}
        except Exception as e:
            print(f"Error loading templates: {e}")
            return {}

    def load_template_functions(self):
        """
        Dynamically import functions from the template file and inject only relevant globals.
        """
        try:
            spec = importlib.util.spec_from_file_location("status_bar_templates", TEMPLATE_FILE)
            templates_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(templates_module)

            # First, filter globals to exclude built-ins and modules
            relevant_globals = {
                k: v for k, v in globals().items()
                if not k.startswith("__") and not isinstance(v, type(importlib))  # Exclude built-ins and modules
            }

            # Debug: Log the filtered globals being injected, grouping functions properly
            self._print_sorted_globals(relevant_globals)

            # Inject filtered globals into the template module
            templates_module.__dict__.update(relevant_globals)

            # Add callable objects to this global namespace
            for name, obj in vars(templates_module).items():
                if callable(obj):
                    globals()[name] = obj

            print_debug("load_template_functions: DONE\n")

        except Exception as e: # pylint: disable=broad-except
            print_error(f"Error loading template functions: {e}")

    def _print_sorted_globals(self, globals_dict):
        """Sorts and prints the provided globals dictionary in two columns with colors."""
        def sort_by_type_and_name(item):
            obj_type = type(item[1]).__name__ if item[1] is not None else "NoneType"
            priority = {"function": 0, "type": 1}.get(obj_type, 2)
            return priority, item[0]

        sorted_globals = sorted(globals_dict.items(), key=sort_by_type_and_name)

        max_name_length = max(len(name) for name, _ in sorted_globals) + 1
        max_type_length = min(8, max(len(type(obj).__name__) for _, obj in sorted_globals))

        mid_index = (len(sorted_globals) + 1) // 2
        left_column = sorted_globals[:mid_index]
        right_column = sorted_globals[mid_index:]

        print_debug("Filtered Globals to Inject:")

        # Helper to format a single column
        def format_column(name, obj):
            obj_type = type(obj).__name__ if obj is not None else "NoneType"
            return f"[green(]{name.ljust(max_name_length)}:[)] {obj_type.ljust(max_type_length)}"

        # Loop and print each row
        for i in range(max(len(left_column), len(right_column))):
            left = left_column[i] if i < len(left_column) else ("", None)
            right = right_column[i] if i < len(right_column) else ("", None)

            left_col = format_column(*left)
            right_col = format_column(*right)

            print_color(f" {left_col} {right_col}")

    def get_current_template(self) -> str:
        """Return the content of the currently selected template."""
        if not self.selected_template_name or self.selected_template_name not in self.templates:
            raise ValueError("No valid template selected.")
        return self.templates[self.selected_template_name]

    def cache_parsed_blocks(self):
        """Cache the parsed blocks for the currently selected template."""
        template_content = self.get_current_template()
        self.cached_parsed_blocks = self.parser.parse_template(template_content)

    def mark_template_change(self):
        """Mark that a template change is pending."""
        self.pending_template_change = True

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
        print_debug(f"get_dynamic_value exception [{type(e).__name__ }]: {e}")
        return "Err"
class WidgetPool:
    """Manages widgets and their order"""
    def __init__(self):
        self.pool = {}

    def add_widget(self, block_id, widget):
        if block_id not in self.pool:
            self.pool[block_id] = widget

    def remove_widget(self, block_id):
        if block_id in self.pool:
            self.pool[block_id].destroy()
            del self.pool[block_id]

    def get_widget(self, block_id):
        return self.pool.get(block_id)

    def has_widget(self, block_id):
        return block_id in self.pool

    def get_widgets_in_order(self, parsed_block_ids):
        return [self.pool[block_id] for block_id in parsed_block_ids if block_id in self.pool]

    def clear(self):
        for widget in self.pool.values():
            if widget and hasattr(widget, "destroy"):
                widget.destroy()
        self.pool.clear()

widget_pool = WidgetPool()

# Frame counters used for slow update frequency
UPDATE_DISPLAY_FRAME_COUNT = 0
SLOW_UPDATE_INTERVAL = 15 # Approx every 500ms

def update_display(template_handler:TemplateHandler):
    """Render the parsed blocks onto the display frame"""
    # Call user update function
    call_user_functions()

    # Update frame counters - used for determining 'slow' updates
    update_frame_counter()

    try:
        # Do not update if drag move is occuring
        if is_moving:
            root.after(UPDATE_INTERVAL, lambda: update_display(template_handler))
            return

        # Re-parse the template if a change is pending
        if template_handler.pending_template_change:
            template_handler.cache_parsed_blocks()
            template_handler.pending_template_change = False

        # Use cached parsed blocks
        parsed_blocks = template_handler.cached_parsed_blocks

        # Track whether a full refresh is needed
        full_refresh_needed = False

        # Process each block and render the widgets
        for block in parsed_blocks:
            needs_refresh = process_block(block, template_handler)
            if needs_refresh:
                full_refresh_needed = True

        # Repack widgets in the correct order
        # This is to avoid a dynamically added VARIF block from being placed at the end

        # Repack widgets only if a full refresh is needed
        if full_refresh_needed:
            parsed_block_ids = [block.get("label", f"block_{id(block)}") for block in parsed_blocks]
            for widget in display_frame.winfo_children():
                widget.pack_forget()
            for widget in widget_pool.get_widgets_in_order(parsed_block_ids):
                widget.pack(side=tk.LEFT, padx=0, pady=0)

            # Force Tkinter to update the display to avoid flickering on VARIF changes
            display_frame.update_idletasks()

        # Dynamically adjust the window size
        new_width = display_frame.winfo_reqwidth() + PADDING_X
        new_height = display_frame.winfo_reqheight() + PADDING_Y

        min_dim = 10
        if new_width < min_dim or new_height < min_dim:
            print_warning(f"Detected an unusually small window size "
                          f"({new_width}x{new_height})")

        # Set to calculated geometry
        root.geometry(f"{new_width}x{new_height}")

    except Exception as e:
        print_error(f"Error in update_display: {e}")

    # Schedule the next update
    root.after(UPDATE_INTERVAL, lambda: update_display(template_handler))

def process_block(block, template_handler):
    """Process one block from the parsed template."""
    block_type = block["type"]
    block_id = block.get("label", f"block_{id(block)}")
    block_metadata = template_handler.parser.block_registry.get(block_type, {})

    # Dynamically handle blocks with conditions
    if "condition" in block_metadata["keys"]:
        condition_function = block.get("condition")
        if condition_function:
            condition = get_dynamic_value(condition_function)
            if not condition:
                # Remove the widget from the pool if the condition fails
                if widget_pool.has_widget(block_id):
                    widget = widget_pool.get_widget(block_id)
                    widget_pool.remove_widget(block_id)
                    return True # Need refresh
                return False

    # Attempt to retrieve an existing widget
    widget = widget_pool.get_widget(block_id)
    render_function = block_metadata.get("render")

    if widget:
        # Use render function to get new configuration
        if render_function:
            config = render_function(block)

            # Check if the render function returned valid data
            if config:
                # Update the existing widget if needed
                if widget.cget("text") != config["text"] or widget.cget("fg") != config["color"]:
                    widget.config(text=config["text"], fg=config["color"])
            else:
                # Remove the widget if the config is invalid (e.g., condition failed)
                widget_pool.remove_widget(block_id)
    else:
        # Create and register a new widget
        if render_function:
            config = render_function(block)
            if config:
                # Create a new widget based on the render function's config
                widget = tk.Label(
                    display_frame,
                    text=config["text"],
                    fg=config["color"],
                    bg=DARK_BG,
                    font=FONT
                )
                widget_pool.add_widget(block_id, widget)
                widget.pack(side=tk.LEFT, padx=5, pady=5)
                return True # Full refresh
        return False

def call_user_functions():
    """Invoke user-defined update functions with exception handling."""
    if USER_UPDATE_FUNCTION_DEFINED:
        try:
            user_update()
        except Exception as e:
            print_error(f"Error in user_update [{type(e).__name__}]: {e}")

    if USER_SLOW_UPDATE_FUNCTION_DEFINED:
        try:
            # Only call this every UPDATE_DISPLAY_FRAME_COUNT cycles
            if UPDATE_DISPLAY_FRAME_COUNT == 0:
                user_slow_update()
        except Exception as e:
            print_error(f"Error in user_slow_update [{type(e).__name__}]: {e}")

def update_frame_counter():
    """Increment and reset the frame counter based on the slow update interval."""
    global UPDATE_DISPLAY_FRAME_COUNT
    UPDATE_DISPLAY_FRAME_COUNT += 1
    if UPDATE_DISPLAY_FRAME_COUNT == SLOW_UPDATE_INTERVAL:
        UPDATE_DISPLAY_FRAME_COUNT = 0

# --- Simbrief functionality ---
class SimBriefFunctions:
    """Contains grouping of static Simbrief Functions mainly for organizational purposes"""
    last_simbrief_generated_time = None

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
            print_debug(f"SimBrief API call failed with status code {response.status_code}")
            return None
        except Exception as e:
            print_debug(f"Error fetching SimBrief OFP: {str(e)}")
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
                    print_debug("'sched_out' not found in SimBrief JSON under 'times'.")
            except Exception as e:
                print_error(f"Error processing SimBrief gate out datetime: {e}")
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
                    print_warning("'est_in' not found in SimBrief JSON under 'times'.")
            except Exception as e:
                print_error(f"Error processing SimBrief arrival datetime: {e}")
        return None

    @staticmethod
    def get_simbrief_ofp_tod_datetime(simbrief_json):
        """Fetch the Top of Descent (TOD) time from SimBrief JSON data."""
        try:
            if "times" not in simbrief_json or "navlog" not in simbrief_json or "fix" not in simbrief_json["navlog"]:
                print_warning("Invalid SimBrief JSON format.")
                return None

            sched_out_epoch = simbrief_json["times"].get("sched_out")
            if not sched_out_epoch:
                print_warning("sched_out (gate out time) not found.")
                return None

            sched_out_epoch = int(sched_out_epoch)

            for waypoint in simbrief_json["navlog"]["fix"]:
                if waypoint.get("ident") == "TOD":
                    time_total_seconds = waypoint.get("time_total")
                    if not time_total_seconds:
                        print_warning("time_total for TOD not found.")
                        return None

                    time_total_seconds = int(time_total_seconds)
                    tod_epoch = sched_out_epoch + time_total_seconds
                    return datetime.fromtimestamp(tod_epoch, tz=timezone.utc)

            print_error("TOD waypoint not found in the navlog.")
            return None
        except Exception as e:
            print_error(f"Error extracting TOD time: {e}")
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

            # Use mapping to fetch the corresponding function
            function_to_call = SIMBRIEF_TIME_OPTION_FUNCTIONS.get(selected_time)

            if function_to_call:
                # Call the selected function
                future_time = function_to_call(simbrief_json)
                if not future_time:
                    return False  # Handle the case where the function returns no time
            else:
                print_error(f"No function mapped for selected_time_option: {selected_time}")
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
            print_error(f"Exception in update_countdown_from_simbrief: {e}")
        return False

    @staticmethod
    def auto_update_simbrief(root):
        """
        Automatically fetch SimBrief data and update the countdown timer if the generation time has changed.
        """
        if not simbrief_settings.auto_update_enabled:
            return  # Exit if auto-update is disabled

        try:
            # Fetch the latest SimBrief data
            simbrief_json = SimBriefFunctions.get_latest_simbrief_ofp_json(simbrief_settings.username)
            if simbrief_json:
                # Extract the generation time
                current_generated_time = simbrief_json.get("params", {}).get("time_generated")
                if not current_generated_time:
                    print_warning("Unable to determine SimBrief flight plan generation time.")
                elif current_generated_time != SimBriefFunctions.last_simbrief_generated_time:
                    print_info(f"New SimBrief flight plan detected. Generation Time: {current_generated_time}")

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
                    print_info("SimBrief flight plan has not changed. Skipping update.")
            else:
                print_error("Failed to fetch SimBrief data during auto-update.")
        except Exception as e:
            print_error(f"DEBUG: Exception during auto-update: {e}")

        # Schedule the next auto-update
        root.after(SIMBRIEF_AUTO_UPDATE_INTERVAL_MS, lambda: SimBriefFunctions.auto_update_simbrief(root))

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

        print_debug(f"UNALTERED SimBrief Gate Time: {simbrief_gate_time}")

        # Adjust SimBrief time for simulator context if required
        if simbrief_settings.use_adjusted_time:
            simulator_to_real_world_offset = get_simulator_time_offset()
            simbrief_gate_time += simulator_to_real_world_offset

        print_debug(f"use_adjusted_time SimBrief Gate Time: {simbrief_gate_time}")

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

            print_debug("Gate Adjustment calculation")
            print_debug(f"user_gate_time_dt: {user_gate_time_dt}")
            print_debug(f"simbrief_gate_time: {simbrief_gate_time}")
            print_debug(f"adjusted_delta: {adjusted_delta}\n")

            # Save user-provided gate-out time
            countdown_state.gate_out_time = user_gate_time_dt
            return adjusted_delta

        # No user-provided gate-out time; use SimBrief defaults
        print_info("No user-provided gate-out time. Using SimBrief default gate-out time.")
        countdown_state.gate_out_time = None
        return timedelta(0)

# MAP SimBriefTimeOption to corresponding functions
SIMBRIEF_TIME_OPTION_FUNCTIONS = {
    SimBriefTimeOption.ESTIMATED_IN: SimBriefFunctions.get_simbrief_ofp_arrival_datetime,
    SimBriefTimeOption.ESTIMATED_TOD: SimBriefFunctions.get_simbrief_ofp_tod_datetime,
}

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

# --- Template Menu ---
def show_template_menu(event, template_handler):
    """
    Display a context menu to allow the user to select a template.
    """
    menu = tk.Menu(root, tearoff=0)

    # Add all templates to the menu
    for template_name in template_handler.templates.keys():
        menu.add_command(
            label=template_name,
            command=lambda name=template_name: switch_template(name, template_handler)
        )

    # Show the menu at the cursor position
    menu.post(event.x_root, event.y_root)

def switch_template(new_template_name, template_handler):
    """
    Switch to a new template and mark it for re-rendering in the next update cycle.
    """
    try:
        # Update the selected template
        template_handler.selected_template_name = new_template_name
        template_handler.mark_template_change()  # Mark the change

        print(f"Switched to template: {new_template_name}")

    except Exception as e:
        print_error(f"Error switching template: {e}")

# --- Settings  ---
SCRIPT_DIR = os.path.dirname(__file__)
SETTINGS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "Settings")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "custom_status_bar.json")
TEMPLATE_FILE = os.path.join(SETTINGS_DIR, "status_bar_templates.py")

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
            print_error("Settings file is corrupted. Using defaults.")
    return {"x": 0, "y": 0}, SimBriefSettings()  # Default position and settings

def save_settings(settings, simbrief_settings):
    """Save settings to the JSON file."""
    try:
        settings["simbrief_settings"] = simbrief_settings.to_dict()
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print_error(f"Error saving settings: {e}")

def is_debugging():
    """Check if the script is running in a debugging environment."""
    try:
        if sys.monitoring.get_tool(sys.monitoring.DEBUGGER_ID) is not None:
            return True
    except Exception:
        return False

def check_user_functions():
    global USER_UPDATE_FUNCTION_DEFINED, USER_SLOW_UPDATE_FUNCTION_DEFINED

    try:
        user_init()
    except NameError:
        print_warning("No user_init function defined in template file")
    except Exception as e:
        print_error(f"Error calling user_init [{type(e).__name__}]: {e}")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)

    # Check for user update function
    function_name = "user_update"
    if function_name in globals() and callable(globals()[function_name]):
        USER_UPDATE_FUNCTION_DEFINED = True
    else:
        USER_UPDATE_FUNCTION_DEFINED = False
        print_warning("No user_update function defined in template file")

    function_name = "user_slow_update"
    if function_name in globals() and callable(globals()[function_name]):
        USER_SLOW_UPDATE_FUNCTION_DEFINED = True
    else:
        USER_SLOW_UPDATE_FUNCTION_DEFINED = False
        print_warning("No user_slow_update function defined in template file")

def main():
    global root, display_frame, simbrief_settings

    print_info("Starting custom status bar...")

    # --- Load initial settings ---
    settings, simbrief_settings_loaded = load_settings()
    simbrief_settings = simbrief_settings_loaded
    initial_x = settings.get("x", 0)
    initial_y = settings.get("y", 0)
    print_debug(f"Loaded window position - x: {initial_x}, y: {initial_y}")

    # --- GUI Setup ---
    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", ALPHA_TRANSPARENCY_LEVEL)
    root.configure(bg=DARK_BG)

     # Start auto-update if enabled
    if simbrief_settings.auto_update_enabled:
        print_info("\nAuto-update is enabled. Starting periodic updates...\n")
        root.after(1000, lambda: SimBriefFunctions.auto_update_simbrief(root))  # Initial delay of 1 second

    # Apply initial geometry after creating the root window
    try:
        # Set initial position
        root.geometry(f"+{initial_x}+{initial_y}")
    except Exception as e:
        print_error(f"Failed to apply geometry - {e}")

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

    # Start the watchdog function to monitor the background thread
    root.after(10_000, background_thread_watchdog_function)

    try:
        # Initialize TemplateHandler
        template_handler = TemplateHandler()

        # Check if user functions are defined
        check_user_functions()

        # Render the initial display
        update_display(template_handler)

        # Bind the right-click menu
        root.bind("<Button-3>", lambda event: show_template_menu(event, template_handler))

        #### FAULT DETECTION ###########
        def reset_traceback_timer():
            """Reset the faulthandler timer to prevent a dump."""
            faulthandler.dump_traceback_later(30, file=traceback_log_file, exit=True)
            root.after(10000, reset_traceback_timer)
        if not is_debugging():
            print_info("Traceback fault timer started")
            reset_traceback_timer()
        else:
            print_info("Traceback fault timer NOT started (debugging detected)")
        #### FAULT DETECTION ########### - END

        # Uncomment to test out traceback timer
        #while True:
        #    pass
        # Run the GUI event loop
        root.mainloop()
    except ValueError as e:
        print_error(f"Error: {e}")
        print("Please check your DISPLAY_TEMPLATE and try again.")

# --- Utility Classes  ---
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

        if isinstance(self.simbrief_settings.selected_time_option, str):
            # If it's already a string, assign it directly
            self.selected_time_option = tk.StringVar(value=self.simbrief_settings.selected_time_option)
        elif isinstance(self.simbrief_settings.selected_time_option, Enum):
            # If it's an Enum, use its value
            self.selected_time_option = tk.StringVar(value=self.simbrief_settings.selected_time_option.value)
        else:
            # Handle unexpected types
            print_warning("Invalid type for selected_time_option")

        # Create the OptionMenu regardless of input type
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
        try:
            print_debug("on_ok---------------------------")

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
            print_debug("pull_time started")

            # Update SimBrief settings from the dialog inputs
            self.update_simbrief_settings()

            # Persist the updated SimBrief settings
            save_settings(load_settings()[0], simbrief_settings)

            # Validate the SimBrief username
            if not self.validate_simbrief_username():
                print_debug("DEBUG: Invalid SimBrief username. Exiting pull_time.")
                return

            # Fetch SimBrief data
            simbrief_json = SimBriefFunctions.get_latest_simbrief_ofp_json(simbrief_settings.username)
            if not simbrief_json:
                messagebox.showerror("Error", "Failed to fetch SimBrief data. Please check your username.")
                print_debug("DEBUG: SimBrief data fetch failed.")
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
                print_error("Countdown timer update failed.")
                return

            print_debug("Countdown timer updated successfully from SimBrief.")
            self.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")
            print_error(f"Exception in pull_time: {e}")

    def update_simbrief_settings(self):
        """Update SimBrief settings from dialog inputs."""
        simbrief_settings.username = self.simbrief_entry.get().strip()
        simbrief_settings.use_adjusted_time = self.simbrief_checkbox_var.get()

        # Validate selected_time_option - ignore custom values
        selected_time = self.selected_time_option.get()
        if selected_time in [option.value for option in SimBriefTimeOption]:
            simbrief_settings.selected_time_option = SimBriefTimeOption(selected_time)

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
        static_text = self.process_label_with_dynamic_functions(block["label"])
        value = get_dynamic_value(block["function"])
        return {
            "text": f"{static_text} {value}",
            "color": block["color"]
        }

    def render_varif(self, block):
        """Render a VARIF block."""
        condition = get_dynamic_value(block["condition"])
        if condition:
            static_text = self.process_label_with_dynamic_functions(block["label"])
            value = get_dynamic_value(block["function"])
            return {
                "text": f"{static_text} {value}",
                "color": block["color"]
            }
        return None

    def render_static_text(self, block):
        """Render a STATIC_TEXT block."""
        return {
            "text": block["value"],
            "color": "white"
        }

    def process_label_with_dynamic_functions(self, text):
        """Replace placeholders in the label with dynamic values."""
        while "##" in text:
            # Find the placeholder
            pos = text.find("##")
            preceding_text = text[:pos].strip()
            function_name = preceding_text.split()[-1]  # Get the last word before "##"

            # Fetch the dynamic value
            dynamic_value = get_dynamic_value(function_name)

            # Replace the placeholder with the fetched value or an empty string
            replacement = str(dynamic_value) if dynamic_value is not None else ""
            text = text.replace(f"{function_name}##", replacement, 1)

        return text

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