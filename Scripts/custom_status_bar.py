"""
custom_status_bar.py: shows a draggable, customizable status bar using SimConnect to display
real-time flight simulator metrics like time, altitude, and temperature in a compact GUI.
   - Please consult the github documentation (MSFS-PyScriptManager) for more information.
   - Uses https://github.com/odwdinc/Python-SimConnect library to obtain values from SimConnect
"""

import faulthandler
import importlib
from io import StringIO
import json
import os
import sys
import threading
import time
import tkinter as tk
import traceback
from tkinter import messagebox
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional
import subprocess

import csv
import requests
from SimConnect import SimConnect, AircraftRequests


try:
    # Import all color print functions
    from Lib.color_print import *  # pylint: disable=unused-wildcard-import, wildcard-import
    from Lib.dark_mode import DarkmodeUtils
    from Lib.gc_tweak import optimize_gc

except ImportError:
    print("Failed to import Lib directory. Please ensure /Lib/* is present")
    sys.exit(1)

# Default templates file - this will be created if it doesn't exist
# in the settings directory as /Settings/status_bar_templates.py
#
# ALL template modification should be done from  /Settings/status_bar_templates.py
DEFAULT_TEMPLATES = """
from Scripts.custom_status_bar import * # Get typing IDE support
#  TEMPLATE DOCUMENTATION
# ====================================
#  Template string below defines the content and format of the data shown in the application's window,
#  including dynamic data elements such as:
# ('VAR()' and 'VARIF()' 'functions') and static text.

# Syntax:`
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

# NOTE: get_formatted_value will return as a string.  In cases where you want to get direct value
#       (as a float) you may want to use get_simconnect_value("PLANE_ALTITUDE") to get the actual
#       value rather than a formatted value.

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

# Runs once every 500ms. If this returns a SimBriefTimeOption, this will set the count down timer
# to a preset.
def user_simbrief():
    # Uncomment next line (and remove 'pass') to use @Leftos idea - this will set countdown timer
    # to EOBT (gate out time) if engine is not running

    #return leftos_engineoff_sets_EOBT()
    pass

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
"""

#### NOTE ####
# This is a fairly large file, I recommend collapsing the headers when browsing this file.
# I've left it as one large file to try to keep it self contained relative to the other scripts.

# pylint: disable=too-many-lines

# --- Globals  -----------------------------------------------------------------------------------
state: Optional["AppState"] = None                      # Main Script State
countdown_state : Optional["CountdownState"] = None     # Countdown timer State

# --- CONFIG Global Variables  -------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    """Immutable configuration settings for the application."""

    ALPHA_TRANSPARENCY: ClassVar[float] = 0.95
    WINDOW_TITLE: ClassVar[str] = "Simulator Time"
    DARK_BG: ClassVar[str] = "#000000"
    FONT: ClassVar[tuple] = ("Helvetica", 16)
    SIMBRIEF_AUTO_UPDATE_INTERVAL_SECONDS: ClassVar[int] = 5 * 60
    PADDING_X: ClassVar[int] = 20
    PADDING_Y: ClassVar[int] = 10
    UNIX_EPOCH: ClassVar[datetime] = datetime(1970, 1, 1, tzinfo=timezone.utc)

    SCRIPT_DIR: ClassVar[str] = os.path.dirname(__file__)
    ROOT_DIR: ClassVar[str] = os.path.dirname(SCRIPT_DIR)
    SETTINGS_DIR: ClassVar[str] = os.path.join(ROOT_DIR, "Settings")
    SETTINGS_FILE: ClassVar[str] = os.path.join(SETTINGS_DIR, "custom_status_bar.json")
    TEMPLATE_FILE: ClassVar[str] = os.path.join(SETTINGS_DIR, "status_bar_templates.py")
CONFIG = Config()       # Global configuration

# --- SimBrief Data Structures  ------------------------------------------------------------------
class SimBriefTimeOption(Enum):
    """Type of time to pull from SimBrief"""
    EST_IN = "Est In"
    TOD = "Est TOD"
    EOBT = "Gate out time (EOBT)"

# --- Settings Handling  -------------------------------------------------------------------------
@dataclass
class SimBriefSettings:
    """Contains settings related to Simbrief functionality"""
    username: str = ""
    use_adjusted_time: bool = False
    selected_time_option: Any = SimBriefTimeOption.EST_IN
    allow_negative_timer: bool = True
    auto_update_enabled: bool = False
    gate_out_time: Optional[datetime] = None

    def to_dict(self):
        """Create dictionary from values"""
        return {
            "username": self.username,
            "use_adjusted_time": self.use_adjusted_time,
            "selected_time_option": (
                self.selected_time_option.value
                if isinstance(self.selected_time_option, SimBriefTimeOption)
                else SimBriefTimeOption.EST_IN.value
            ),
            "allow_negative_timer": self.allow_negative_timer,
            "auto_update_enabled": self.auto_update_enabled,
        }

    @staticmethod
    @staticmethod
    def from_dict(data):
        """Take values from dictionary and ensure proper type conversion"""

        # Retrieve values from dictionary
        username = data.get("username", "")
        use_adjusted_time = data.get("use_adjusted_time", False)
        allow_negative_timer = data.get("allow_negative_timer", False)
        auto_update_enabled = data.get("auto_update_enabled", False)

        # Handle `selected_time_option`
        selected_time_option = data.get("selected_time_option", SimBriefTimeOption.EST_IN.value)

        if isinstance(selected_time_option, str):
            try:
                selected_time_option = SimBriefTimeOption(selected_time_option)
            except ValueError:
                print(f"Warning: Invalid value '{selected_time_option}' for 'selected_time_option'. Resetting to default (ESTIMATED_IN).")
                selected_time_option = SimBriefTimeOption.EST_IN
        elif not isinstance(selected_time_option, SimBriefTimeOption):
            print(f"Warning: Unexpected type for 'selected_time_option'. Resetting to default.")
            selected_time_option = SimBriefTimeOption.EST_IN

        # Return instance of SimBriefSettings with corrected values
        return SimBriefSettings(
            username=username,
            use_adjusted_time=use_adjusted_time,
            selected_time_option=selected_time_option,
            allow_negative_timer=allow_negative_timer,
            auto_update_enabled=auto_update_enabled,
        )

@dataclass
class ApplicationSettings:
    """Script settings definitions - used by SettingsManager"""
    pos: dict = field(default_factory=lambda: {"x": 0, "y": 0})
    simbrief_settings: "SimBriefSettings" = field(default_factory=SimBriefSettings)

    def get_window_position(self):
        """Get x, y window position returned as tuple"""
        return self.pos["x"], self.pos["y"]

    def to_dict(self):
        """Create dictionary from values"""
        return {
            "pos": self.pos,
            "simbrief_settings": self.simbrief_settings.to_dict(),
        }

    @staticmethod
    def from_dict(data: dict):
        """Take values from dictionary"""
        return ApplicationSettings(
            pos=data.get("pos", {"x": 0, "y": 0}),
            simbrief_settings=SimBriefSettings.from_dict(data.get("simbrief_settings", {})),
        )

class SettingsManager:
    """Handles loading, saving, and managing application settings."""

    def __init__(self):
        # Ensure the directory exists
        os.makedirs(CONFIG.SETTINGS_DIR, exist_ok=True)

    def load_settings(self) -> ApplicationSettings:
        """Load settings from the JSON file."""
        if os.path.exists(CONFIG.SETTINGS_FILE):
            try:
                with open(CONFIG.SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return ApplicationSettings.from_dict(data)
            except json.JSONDecodeError:
                print_error("Settings file is corrupted. Using defaults.")
        # Return default settings if the file doesn't exist or is corrupted
        return ApplicationSettings()

    def save_settings(self, settings: ApplicationSettings):
        """Save settings to the JSON file."""
        try:
            with open(CONFIG.SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings.to_dict(), f, indent=4)
        except Exception as e:
            print_error(f"Error saving settings: {e}")

# --- Main operational classes -------------------------------------------------------------------
class AppState:
    """Manages core application state like SimConnect, logging, and settings."""
    def __init__(self):
        self.sim_connect = None
        self.aircraft_requests = None
        self.sim_connected = False

        self.template_menu_open = False

        # Load Settings
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.load_settings()

        # User functions
        self.user_update_function_defined = False
        self.user_slow_update_function_defined = False
        self.user_simbrief_function_defined = False

        # Initialize TickManager
        self.tick_manager = TickManager()

        # Subscribe to ticks for user functions
        self.tick_manager.subscribe_to_tick(self)
        self.tick_manager.subscribe_to_slow_tick(self)

        # Initialize SimBrief Auto Timer Manager
        self.simbrief_timer = SimBriefAutoTimer(self)

        self.root = None

    def start(self, root):
        """
        Start tick loop - this 'tick' is used to clock user functions
        Based on a Tkinter .after scheduler so it needs root
        """
        # This calls user_init - do it here to ensure TemplateHandler has been initialized
        self.check_user_functions()
        self.tick_manager.start(root)

    def check_user_functions(self):
        """Check to see if user functions have been defined"""
        try:
            user_init()  # type: ignore  # pylint: disable=undefined-variable
        except NameError:
            print_warning("No user_init function defined in template file")
        except Exception as e:  # pylint: disable=broad-except # Is valid case to catch all
            print_error(f"Error calling user_init [{type(e).__name__}]: {e}")
            traceback.print_exc(file=sys.stdout)
            sys.exit(1)

        # Check for user update function
        function_name = "user_update"
        if function_name in globals() and callable(globals()[function_name]):
            self.user_update_function_defined = True
        else:
            self.user_update_function_defined = False
            print_warning("No user_update function defined in template file")

        function_name = "user_slow_update"
        if function_name in globals() and callable(globals()[function_name]):
            self.user_slow_update_function_defined = True
        else:
            self.user_slow_update_function_defined = False
            print_warning("No user_slow_update function defined in template file")

        function_name = "user_simbrief"
        if function_name in globals() and callable(globals()[function_name]):
            self.user_simbrief_function_defined = True
        else:
            self.user_simbrief_function_defined = False
            print_warning("No user_simbrief function defined in template file")

    def tick(self):
        """Normal tick (tick manager)"""
        self.call_user_update()

    def slow_tick(self):
        """Slow tick (tick manager)"""
        self.call_user_slow_update()
        self.auto_update_simbrief()

    def call_user_update(self):
        """Invoke user-defined update function (if it exists)."""
        if self.user_update_function_defined:
            try:
                user_update() # type: ignore  # pylint: disable=undefined-variable
            except Exception as e:  # pylint: disable=broad-exception-caught
                print_error(f"Error in user_update [{type(e).__name__}]: {e}")

    def call_user_slow_update(self):
        """Invoke slow update function every 500ms."""
        if self.user_slow_update_function_defined:
            try:
                user_slow_update() # type: ignore  # pylint: disable=undefined-variable
            except Exception as e:  # pylint: disable=broad-exception-caught
                print_error(f"Error in user_slow_update [{type(e).__name__}]: {e}")

    def auto_update_simbrief(self):
        """Update timer based on SimBrief settings (along with user function if provided)."""
        user_setting = None

        # Call user simbrief handler function
        # User can set a SimBriefTimeOption to force that to be used as timer setting
        if self.user_simbrief_function_defined:
            try:
                user_setting = user_simbrief()  # type: ignore  # pylint: disable=undefined-variable
            except Exception as e:  # pylint: disable=broad-exception-caught
                print_error(f"Error calling user_simbrief(): {e}")

        # Pass user_setting to SimBriefAutoTimer
        self.simbrief_timer.update_countdown(user_setting)

class SimBriefAutoTimer:
    """Handles automatic countdown timer updates based on SimBrief data."""

    def __init__(self, app_state):
        self.app_state = app_state
        self.last_simbrief_json = None
        self.last_simbrief_load = CONFIG.UNIX_EPOCH
        self.last_user_setting = None

    def update_countdown(self, user_setting):
        """Update countdown timer based on SimBrief settings."""
        simbrief_updated = False

        simbrief_settings = self.app_state.settings.simbrief_settings
        if not simbrief_settings.auto_update_enabled:
            return  # Exit if auto-update is disabled

        # Check if SimBrief needs to be updated (every 5 minutes)
        elapsed_time = datetime.now(timezone.utc) - self.last_simbrief_load
        if elapsed_time.total_seconds() > CONFIG.SIMBRIEF_AUTO_UPDATE_INTERVAL_SECONDS:
            self.last_simbrief_load = datetime.now(timezone.utc)
            print_debug("SimBriefAutoTimer: Checking SimBrief (elapsed time has passed)")
            simbrief_updated = self.update_simbrief_json()

        # Update countdown timer only if necessary
        if ( user_setting != self.last_user_setting or simbrief_updated ) \
            and not countdown_state.timer_source == CountdownState.TimerSource.USER_TIMER:
            print_debug("SimBriefAutoTimer: updating timer user_setting:"
                        f" {user_setting} simbrief_updated: {simbrief_updated}")

            try:
                SimBriefFunctions.update_countdown_from_simbrief(
                    simbrief_json=self.last_simbrief_json,
                    simbrief_settings=simbrief_settings,
                    gate_out_datetime=simbrief_settings.gate_out_time,
                    custom_time_option=user_setting
                )
                self.last_user_setting = user_setting
            except RuntimeError as re:
                print_warning(f"Failed to update countdown timer from SimBrief data - {re}")
            except ValueError as e:
                print_warning(f"Failed to update countdown timer from SimBrief data - {e}")

    def update_simbrief_json(self) -> bool:
        """Fetch SimBrief JSON and return True if 'time_generated' has changed."""
        new_json = SimBriefFunctions.get_latest_simbrief_ofp_json(self.app_state.settings.simbrief_settings.username)

        if not new_json:
            print_warning("SimBrief JSON fetch failed or returned empty data.")
            return False

        new_time = new_json.get("params", {}).get("time_generated")
        old_time = self.last_simbrief_json.get("params", {}).get("time_generated") if self.last_simbrief_json else None

        if new_time and new_time != old_time:
            self.last_simbrief_json = new_json
            return True

        return False


class UIManager:
    """Manages UI-specific state, such as dragging and widget updates."""
    def __init__(self, app_state: AppState):
        self.root = tk.Tk()
        self.app_state = app_state
        self.settings = app_state.settings
        self.drag_handler = DragHandler(self.root)
        self.template_handler = TemplateHandler()
        self.display_updater = DisplayUpdater( self.root, self.app_state,
                                               self.template_handler, self.drag_handler )

        # These define if user functions are defined or not
        self.user_update_function_defined = False
        self.user_slow_update_function_defined = False

        # Last known UI position (loaded from settings)
        self.window_x, self.window_y = 0, 0

        self.tkinter_setup()

    def get_root(self):
        """Provide access to the Tk root window for other components."""
        return self.root

    def tkinter_setup(self):
        """Setup Tkinter related functionality"""
        self.root.title(CONFIG.WINDOW_TITLE)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", CONFIG.ALPHA_TRANSPARENCY)
        self.root.configure(bg=CONFIG.DARK_BG)

        # Load window position
        initial_x, initial_y = self.settings.get_window_position()
        self.root.geometry(f"+{initial_x}+{initial_y}")

        # --- Double click functionality for setting timer ---
        self.root.bind("<Double-1>", lambda event: self.open_timer_dialog())

        # Bind the right-click menu
        self.root.bind("<Button-3>", self.show_template_menu)

    def open_timer_dialog(self):
        """
        Open the CountdownTimerDialog to prompt the user to set a future countdown time and
        SimBrief settings.
        """
        # Open the dialog with current SimBrief settings and last entered time
        dialog = CountdownTimerDialog(self.root, self.app_state)
        self.root.wait_window(dialog)  # Wait for dialog to close

    def show_template_menu(self, event):
        """Display a context menu and track when it closes."""
        self.app_state.template_menu_open = True

        self.menu = tk.Menu(
            self.root,
            tearoff=0,
            bg="#333333",
            fg="white",
            activebackground="#555555",
            activeforeground="white"
        )

        for template_name in self.template_handler.templates.keys():
            self.menu.add_command(
                label=template_name,
                command=lambda name=template_name: self.switch_template(name)
            )

        # Post the menu
        self.menu.post(event.x_root, event.y_root)

        # Start polling to detect when the menu is gone
        self.check_menu_closed()

    def check_menu_closed(self):
        """Repeatedly check if the menu is still open."""
        if self.menu and not self.menu.winfo_ismapped():
            self.app_state.template_menu_open = False
        else:
            self.root.after(100, self.check_menu_closed)  # Check again in 100ms

    def switch_template(self, new_template_name):
        """Switch to a new template and mark it for re-rendering in the next update cycle."""
        try:
            # Update the selected template
            self.template_handler.selected_template_name = new_template_name
            self.template_handler.mark_template_change()  # Mark the change

            print(f"Switched to template: {new_template_name}")

        except Exception as e:
            print_error(f"Error switching template: {e}")

    def start(self):
        """Start any UI related functions"""
        # Start display update
        self.display_updater.update_display()

class ServiceManager:
    """Handles background services like SimConnect updates and SimBrief auto-update."""
    def __init__(self, app_state, settings: "ApplicationSettings", root):
        self.app_state = app_state
        self.background_updater = BackgroundUpdater(self.app_state, root)

        # Log File
        self.log_file_path = "traceback.log"
        self.traceback_log_file = open(self.log_file_path, "w", encoding="utf-8")
        faulthandler.enable(file=self.traceback_log_file)

        self.settings = settings
        self.root = root

    def start(self):
        """Start service manager tasks"""
        self.background_updater.start()
        self.start_debugging_utils()

    def start_debugging_utils(self):
        """Start debug related utilites"""
        def reset_traceback_timer():
            """Reset the faulthandler timer to prevent a dump."""
            faulthandler.dump_traceback_later(60, file=self.traceback_log_file)
            self.root.after(10000, reset_traceback_timer)
        if not self.is_debugging():
            print_info("Traceback fault timer started")
            reset_traceback_timer()
        else:
            print_info("Traceback fault timer NOT started (debugging detected)")

        # Bind log that can be executed during runtime
        try:
            import keyboard # pylint: disable=import-outside-toplevel
            keyboard.add_hotkey("ctrl+alt+shift+l", self.log_global_state)
            print_info("Global hotkey 'Ctrl+Alt+Shift+L' registered for logging state.")
        except ImportError:
            print_warning("Please 'pip install keyboard' for dynamic logging")

    def is_debugging(self):
        """Check if the script is running in a debugging environment."""
        try:
            if sys.monitoring.get_tool(sys.monitoring.DEBUGGER_ID) is not None:
                return True
        except Exception: # pylint: disable=broad-exception-caught
            return False

    def log_global_state(self, event=None, log_path="detailed_state_log.log", max_depth=2):
        """
        Log the global state and nested attributes to a file, prioritizing user-defined globals.

        Args:
            event: Tkinter event (passed automatically when bound to a shortcut).
            log_path (str): Path to save the log file.
            max_depth (int): Maximum recursion depth for nested attributes.
        """
        import inspect # pylint: disable=import-outside-toplevel # Deliberate lazy load

        def is_user_defined(var_name, var_value):
            """
            Determine if a global variable is user-defined.
            A variable is considered user-defined if:
            - It is not a module.
            - It is not a built-in function or object.
            - It is not imported (i.e., it was declared in the current script).
            """
            if var_name.startswith("__"):  # Skip dunder (magic) variables
                return False
            # Check if the variable is a module or built-in
            if inspect.ismodule(var_value):
                return False
            if inspect.isbuiltin(var_value):
                return False
            # Check if the variable's module is the current script
            if hasattr(var_value, "__module__") and var_value.__module__ == "__main__":
                return True
            # Fallback for non-callable objects
            return not callable(var_value)

        def log_variable(var_name, var_value, depth=0):
            """Recursively log a variable and its attributes up to max_depth."""
            indent = "  " * depth
            if depth > max_depth:
                return  # Stop recursion if max depth is exceeded

            try:
                log_file.write(f"{indent}{var_name}: {repr(var_value)}\n")

                # Recurse into attributes if the variable is a custom object or dict
                if hasattr(var_value, "__dict__"):
                    for attr_name, attr_value in vars(var_value).items():
                        log_variable(f"{var_name}.{attr_name}", attr_value, depth + 1)
                elif isinstance(var_value, dict):
                    for key, value in var_value.items():
                        log_variable(f"{var_name}[{repr(key)}]", value, depth + 1)
                elif isinstance(var_value, (list, set, tuple)):
                    for idx, value in enumerate(var_value):
                        log_variable(f"{var_name}[{idx}]", value, depth + 1)
            except Exception as e:
                log_file.write(f"{indent}{var_name}: [ERROR: {str(e)}]\n")

        # Separate user-defined and external globals
        user_globals = {k: v for k, v in globals().items() if is_user_defined(k, v)}
        external_globals = {k: v for k, v in globals().items() if k not in user_globals}

        # Start logging
        with open(log_path, "w", encoding="utf-8") as log_file:
            log_file.write(f"--- Global State Log: {datetime.now()} ---\n\n")

            # Tkinter state
            log_file.write("winfo_geometry="
                           f"{self.root.winfo_geometry()}, state={self.root.state()}\n")

            # Log user-defined globals first
            log_file.write("### User-Defined Globals ###\n")
            for name, value in user_globals.items():
                log_variable(name, value)

            # Log external globals next
            log_file.write("\n### External Globals ###\n")
            for name, value in external_globals.items():
                log_variable(name, value)

        print(f"Global state logged to {log_path}")

# --- Timer Variables  ---------------------------------------------------------------------------
@dataclass
class CountdownState:
    """Countdown timer state"""

    class TimerSource(Enum):
        """Which source set the timer last"""
        AUTO_TIMER = "auto_timer"
        USER_TIMER = "user_timer"
        USER_SELECTED_PRESET = "user_selected_preset"

    timer_source: Optional[TimerSource] = None  # Tracks the source of the timer
    last_entered_time: Optional[str] = None     # Last entered time in HHMM format
    countdown_target_time: datetime = field(default_factory=lambda: CONFIG.UNIX_EPOCH)

    def set_future_time(self, new_time: datetime, simulator_time: datetime, simbrief_settings,
                        timer_source: TimerSource):
        """Set a new countdown target time"""
        self._validate_future_time(new_time, simulator_time, simbrief_settings)
        self.countdown_target_time = new_time
        self.timer_source = timer_source
        return True

    def _validate_future_time(self, future_time_input, current_sim_time, simbrief_settings) -> bool:
        """Validates a future time (countdown timer time)"""
        # Ensure all times are timezone-aware (UTC)
        if current_sim_time.tzinfo is None:
            current_sim_time = current_sim_time.replace(tzinfo=timezone.utc)

        if isinstance(future_time_input, datetime):
            # Validate that the future time is after the current simulator time
            if future_time_input <= current_sim_time and \
            not simbrief_settings.allow_negative_timer:
                raise ValueError("Set timer time must be later than the current simulator time.")

            # Log successful setting of the timer
            print(f"Timer set to: {future_time_input}")
            return True
        else:
            raise TypeError("Unsupported future_time_input type. Must be a datetime object.")

# --- SimConnect Template Functions --------------------------------------------------------------
def get_sim_time():
    """Fetch the simulator time from SimConnect, formatted as HH:MM:SS."""
    try:

        if not is_simconnect_available():
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
    """Fetches the absolute time from the simulator and converts it to a datetime object."""
    try:
        if state is None or not is_simconnect_available():
            return CONFIG.UNIX_EPOCH

        absolute_time = get_simconnect_value("ABSOLUTE_TIME")
        if absolute_time is None:
            return CONFIG.UNIX_EPOCH

        base_datetime = datetime(1, 1, 1, tzinfo=timezone.utc)
        return base_datetime + timedelta(seconds=float(absolute_time))

    except Exception as e:
        print(f"get_simulator_datetime: Failed to retrieve simulator datetime: {e}")

    # Return the Unix epoch if simulator time is unavailable
    return CONFIG.UNIX_EPOCH

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
    return get_formatted_value(["AMBIENT_TEMPERATURE", "TOTAL_AIR_TEMPERATURE"],
                               "TAT {1:.0f}°C  SAT {0:.0f}°C")

def remain_label():
    """
    Returns the full 'Remaining' label dynamically.
    Includes '(adj)' if time adjustment for acceleration is active, otherwise 'Remaining'.
    """
    if is_sim_rate_accelerated():
        return "Rem(adj):"

    # Show label based on the source of the timer
    if countdown_state.timer_source == CountdownState.TimerSource.USER_TIMER:
        return "Rem(user):"
    elif countdown_state.timer_source == CountdownState.TimerSource.USER_SELECTED_PRESET:
        simbrief_option = state.settings.simbrief_settings.selected_time_option.name
        if isinstance(simbrief_option, str):
            return f"Rem({simbrief_option}):"
    elif countdown_state.timer_source == CountdownState.TimerSource.AUTO_TIMER:
        # Dynamically fetch the SimBrief option if it was set by the auto timer
        if state and state.simbrief_timer:
            simbrief_option = state.simbrief_timer.last_user_setting
            if isinstance(simbrief_option, SimBriefTimeOption):
                return f"Rem({simbrief_option.name}):"
        return "Auto:"
    else:
        return "Remaining:"

# --- Timer Calculation Functions------------------------------------------------------------------
def get_time_to_future_adjusted():
    """Calculate and return the countdown timer string."""
    return get_time_to_future(adjusted_for_sim_rate=True)

def get_time_to_future_unadjusted():
    """Calculate and return the countdown timer string without adjusting for sim rate."""
    return get_time_to_future(adjusted_for_sim_rate=False)

def get_time_to_future(adjusted_for_sim_rate: bool) -> str:
    """Calculate and return the countdown timer string."""
    if countdown_state is None or countdown_state.countdown_target_time == CONFIG.UNIX_EPOCH:
        return "N/A"

    current_sim_time = get_simulator_datetime()

    if current_sim_time == CONFIG.UNIX_EPOCH:
        return "N/A"

    if countdown_state.countdown_target_time.tzinfo is None or current_sim_time.tzinfo is None:
        raise ValueError("Target time or simulator time is offset-naive. "
                            "Ensure all times are offset-aware.")

    # Fetch sim rate if we want to adjust for it,
    # otherwise default to 1.0 (normal time progression)
    sim_rate = 1.0
    if adjusted_for_sim_rate:
        raw_sim_rate = get_simconnect_value("SIMULATION_RATE", default_value=1.0)
        try:
            sim_rate = float(raw_sim_rate) if raw_sim_rate is not None else 1.0
        except (TypeError, ValueError):
            print_warning("get_time_to_future: Exception on sim_rate")
            sim_rate = 1.0

    # Compute the count-down time
    countdown_str = compute_countdown_timer(
        current_sim_time=current_sim_time,
        target_time=countdown_state.countdown_target_time,
        sim_rate=sim_rate,
    )

    return countdown_str

def compute_countdown_timer(
    current_sim_time: datetime,
    target_time: datetime,
    sim_rate: float
) -> str:
    """
    Compute the countdown timer string and update its state.

    Parameters:
    - current_sim_time (datetime): Current simulator time.
    - target_time (datetime): Target countdown time.
    - sim_rate (float): Simulation rate.

    Returns:
    - countdown_str (str): Formatted countdown string "HH:MM:SS".
    """
    # Early out if we have no current sim time
    if current_sim_time == CONFIG.UNIX_EPOCH:
        return "N/A"

    # Calculate remaining time
    remaining_time = target_time - current_sim_time

    # Adjust for simulation rate
    if sim_rate and sim_rate > 0:
        adjusted_seconds = remaining_time.total_seconds() / sim_rate
    else:
        adjusted_seconds = remaining_time.total_seconds()

    # Enforce allow_negative_timer setting
    if state is not None and state.settings.simbrief_settings is not None:
        if not state.settings.simbrief_settings.allow_negative_timer and adjusted_seconds < 0:
            adjusted_seconds = 0

    # Format the adjusted remaining time as HH:MM:SS
    total_seconds = int(adjusted_seconds)
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    countdown_str = f"{sign}{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

    return countdown_str

def get_simulator_time_offset():
    """
    Calculate the offset between simulator time and real-world UTC time.
    Returns a timedelta representing the difference (simulator time - real-world time).
    """
    try:
        # Use a threshold for considering the offset as zero
        threshold = timedelta(seconds=5)
        simulator_time = get_simulator_datetime()

        if simulator_time == CONFIG.UNIX_EPOCH:
            print_debug("get_simulator_time_offset: skipping since time is == UNIX_EPOCH")
            return timedelta()

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
    """Convert a real-world datetime (UTC) to simulator time using the calculated offset."""
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

# --- SimConnect Lookup Functions ----------------------------------------------------------------
def is_sim_running(min_runtime=120):
    """Return True if an MSFS process has been running for at least min_runtime seconds."""
    try:
        cmd = (
            'wmic process where "name like \'FlightSimulator%%.exe\'" '
            'get Name,CreationDate,ProcessId /format:csv'
        )
        raw_output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
        output = raw_output.decode(errors="ignore").strip()
        if "No Instance(s) Available" in output:
            output = ""

        if output:
            print_debug("MSFS is running")
    except subprocess.CalledProcessError:
        return False

    now = time.time()
    reader = csv.DictReader(StringIO(output))

    for row in reader:
        name = row.get("Name", "").strip()
        creation = row.get("CreationDate", "").split('.')[0].strip()
        pid = row.get("ProcessId", "").strip()

        if not (name.startswith("FlightSimulator") and creation and pid.isdigit()):
            continue

        try:
            start_time = time.mktime(time.strptime(creation, "%Y%m%d%H%M%S"))
        except ValueError:
            print(f"[ERROR] Could not parse creation time: {creation}")
            continue

        runtime = now - start_time
        if runtime >= min_runtime:
            print_info(f"Found MSFS process: {name} (PID: {pid}, Running for {runtime:.1f} sec)")
            return True
        else:
            print_info(f"Found {name} (PID: {pid}), but only running for {runtime:.1f} sec (Waiting...)")
            return False

    return False

def initialize_simconnect():
    """Initialize the connection to SimConnect."""
    try:
        if not is_sim_running():
            return
        print_info("Connecting to SimConnect...")
        state.sim_connect = SimConnect()
        print_info("Connecting to SimConnect... DONE")
        state.aircraft_requests = AircraftRequests(state.sim_connect, _time=10, _attemps=2)
        state.sim_connected = True
        print_debug("Sim is Connected")
    except Exception as e:
        print_debug(f"Sim could not connect {e}")
        state.sim_connected = False

def is_simconnect_available() -> bool:
    """Check if SimConnect is available and running."""
    return (
        state is not None and
        state.sim_connected and
        state.sim_connect is not None and
        state.sim_connect.ok
    )

# --- Cache Lookup Functions ---------------------------------------------------------------------

# These will lookup values from cache values which are updated from Background-Updater

@dataclass
class SimVarLookup:
    """Tracks an individual SimConnect lookup - used by cache system"""
    name: str
    last_update: float = field(default_factory=lambda: 0.0)
    _value: Any = "N/A"  # Default value before it's updated

    def needs_update(self, update_frequency: float) -> bool:
        """Check if the variable needs an update based on its last refresh time."""
        return (time.time() - self.last_update) >= update_frequency

    def mark_updated(self):
        """Update the last update timestamp."""
        self.last_update = time.time()

    def set_value(self, v: Any):
        """Set internal value based on type"""

        # Note that SimConnect lib only returns floats or strings
        if isinstance(v, bytes):
            try:
                decoded_string = v.decode("utf-8").strip("\x00")
                self._value = decoded_string
                self.mark_updated()
            except UnicodeDecodeError as e:
                print_error(f"set_value: Decode error on {self.name}")
                raise ValueError(f"Failed to decode bytes for {self.name}: {e}") from e
        elif isinstance(v, float):
            self._value = v
            self.mark_updated()
        else:
            print_error(f"set_value: Unexpected value type: {type(v)} for {self.name}")
            raise TypeError(f"Unexpected value type: {type(v)} for {self.name}")

    def get_value(self, max_age=5.0):
        """Retrieve the value, marking it stale if too old."""
        if self.needs_update(max_age):
           self._value = None
        return self._value

sim_variables: dict[str, SimVarLookup] = {}     # Cache of looked up SimConnect variables
cache_lock = threading.Lock()                   # Lock used by cache system

def get_simconnect_value(variable_name: str, default_value: Any = "N/A",
                         retries: int = 10, retry_interval: float = 0.2) -> Any:
    """
    Fetch a SimConnect variable from the cache
    Retries is intended to deal with first time calls - gives a chance for value to be loaded
    by Simconnect module rather than returning None
    Note: for faster lookups it may be preferable to call check_cache which will return value
    from cache
    """
    if not is_simconnect_available():
        return "Sim Not Running"

    def is_value_valid(value: Any, default_value: Any) -> bool:
        return value is not None

    # Check cache value
    value = get_cache_value(variable_name)
    if is_value_valid(value, default_value):
        return value
    else:
        # Add/reset cache value since value isn't valid
        add_to_cache(variable_name, default_value)

    # Retry lookup loop - purpose is to handle first lookup to give it a chance for it to be
    # captured in background updater
    for _ in range(retries):
        value = get_cache_value(variable_name)
        if is_value_valid(value, default_value):
            return value
        time.sleep(retry_interval)

    print_debug(
        f"All {retries} retries failed for '{variable_name}'. "
        f"Returning default: {default_value}"
    )
    return default_value

def get_cache_value(variable_name):
    """Return cached value if available, otherwise None."""
    with cache_lock:
        lookup = sim_variables.get(variable_name)
        return lookup.get_value() if lookup else None  # Get cached value from SimVarLookup

def add_to_cache(variable_name, default_value="N/A"):
    """Ensure a SimConnect variable is tracked and initialized in `sim_variables`."""
    with cache_lock:
        if variable_name not in sim_variables:
            sim_variables[variable_name] = SimVarLookup(name=variable_name)

def prefetch_variables(*variables):
    """Ensure SimConnect variables are tracked without fetching them yet."""
    with cache_lock:
        for variable_name in variables:
            if variable_name not in sim_variables:
                sim_variables[variable_name] = SimVarLookup(name=variable_name)

def reset_cache():
    """Reset all cached SimConnect variables."""
    # TODO: possibly have flag to represent empty?
    with cache_lock:
        sim_variables.clear()
    if state.sim_connected:
        print_warning("SimConnect cache reset!")

def get_formatted_value(variable_names, format_string=None):
    """
    Fetch one or more SimConnect variables, apply optional formatting if provided.

    Parameters:
    - variable_names: The SimConnect variable name(s) to retrieve (can be a single name or a list).
    - format_string: An optional string format to apply to the retrieved values.

    Returns:
    - The formatted string, or an error message if retrieval fails.
    """

    if not is_simconnect_available():
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

# --- Background Updater -------------------------------------------------------------------------
class BackgroundUpdater:
    """
    Continously updates cached values from Simconnect
    Purpose: Ensures that all cached requests are updated continously as the
             default SimConnect library caching does not update its own cached
             values until get is called.
    """

    MIN_UPDATE_INTERVAL = 33 / 2  # Retry interval
    STANDARD_UPDATE_INTERVAL = 33  # Normal interval

    def __init__(self, app_state, root):
        self.state = state
        self.variable_sleep = 0.001  # Sleep time between variable lookups

        self.last_successful_update_time = time.time()
        self.running = False
        self.thread = None

        self.root = root

    def start(self):
        """Start the background update thread."""
        if self.running:
            print_warning("BackgroundUpdater Already running.")
            return

        self.running = True
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        print_info("BackgroundUpdater Started.")

        self.background_thread_watchdog_function()

    def stop(self):
        """Stop the background update thread cleanly."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
            print_info("BackgroundUpdater Stopped.")

    def run(self):
        """Main background update loop - pulls data from SimConnect and saves it to cache"""
        while self.running:
            lookup_failed = False  # Track if any variable lookup failed

            try:
                if not self.state.sim_connected:
                    initialize_simconnect()
                    # Allow execution to continue so we can detect if connection was successful or
                    # not

                if self.state.sim_connected:
                    # Detect if sim_connect lib is reporting issue or quit status
                    if not self.state.sim_connect.ok or self.state.sim_connect.quit == 1:
                        print_warning("SimConnect state invalid. Disconnecting.")
                        self.state.sim_connected = False
                        continue

                    # Make a copy of the variables to avoid holding the lock during network calls
                    # Prioritize by last_update
                    with cache_lock:
                        vars_to_update = sorted( sim_variables.values(), key=lambda v: v.last_update )

                    for variable in vars_to_update:
                        try:
                            if self._is_aircraft_requests_defined():
                                value = self.state.aircraft_requests.get(variable.name)
                                if value is not None:
                                    with cache_lock:
                                        sim_variables[variable.name].set_value(value)
                                        sim_variables[variable.name].mark_updated()
                                else:
                                    lookup_failed = True
                            else:
                                print_warning("'aq' is None or does not have a 'get' method.")
                                lookup_failed = True
                        except OSError as e:
                            print_debug(f"Error fetching '{variable.name}': {e}. "
                                            "Will retry in the next cycle.")
                            lookup_failed = True

                        # Add a small sleep to allow main thread to not be blocked (due to GIL
                        # thread restrictions)
                        time.sleep(self.variable_sleep)

                else: # sim_connected == False
                    reset_cache()
                    time.sleep(5)

                # Adjust sleep interval dynamically
                sleep_interval = self.MIN_UPDATE_INTERVAL \
                                    if lookup_failed else self.STANDARD_UPDATE_INTERVAL
                time.sleep(sleep_interval / 1000.0)

            except Exception as e:
                print_error(f"Unexpected error in background updater: {e}")
                print(f"Exception type: {type(e).__name__}")
            finally:
                # Update the last successful update time - used for 'heartbeat' functionality
                self.last_successful_update_time = time.time()

    def _is_aircraft_requests_defined(self):
        """Helper function to see if aircraft_requests is valid as an object"""
        return self.state.aircraft_requests is not None and hasattr(self.state.aircraft_requests, 'get')

    def background_thread_watchdog_function(self):
        """Check background thread function to see if it has locked up"""
        now = time.time()
        threshold = 30  # seconds before we consider the updater "stuck"

        # Increase threshold if sim not connected.  Waiting for connection to occur during sim load
        # can cause warnings to appear otherwise
        if not state.sim_connected:
            threshold = 240

        if now - self.last_successful_update_time > threshold:
            print_error(f"Watchdog: Background updater has not completed a cycle in "
                        f"{int(now - self.last_successful_update_time)} seconds. "
                        "Possible stall detected.")

        # Reschedule the watchdog to run again after 10 seconds
        self.root.after(10_000, self.background_thread_watchdog_function)

# --- Display Update  ----------------------------------------------------------------------------
def get_dynamic_value(function_name: str):
    """
    Retrieve a value dynamically from a globally defined function.

    Args:
        function_name (str): The name of the global function to call.

    Returns:
        Any:
            - The function's return value if found and callable.
            - "" (empty string) if `function_name` is empty.
            - "Err-DE" if the function does not exist.
            - "Err" if an exception occurs.
    """
    try:
        if not function_name.strip():  # If function name is empty, return an empty string
            return ""
        if function_name in globals():
            func = globals()[function_name]
            if callable(func):
                return func()
        print_warning(f"get_dynamic_value: {function_name} not found!")
        return "Err-DE" # Error 'doesn't exist'
    except Exception as e:  # pylint: disable=broad-except
        print_error(f"get_dynamic_value: ({function_name}) exception [{type(e).__name__ }]: {e}")
        return "Err"

class DisplayUpdater:
    """Handles the rendering and updating of the status bar display."""

    # Do slow update every 15 normal updates (approx 500ms)
    SLOW_UPDATE_INTERVAL = 15

    def __init__(self, root, app_state, template_handler, drag_handler):
        self.root = root
        self.state = app_state
        self.template_handler = template_handler
        self.drag_handler = drag_handler

        self.display_frame = tk.Frame(root, bg=CONFIG.DARK_BG)
        self.display_frame.pack(padx=10, pady=5)

        self.widget_pool = WidgetPool()
        self.update_display_frame_count = 0

        # Subscribe to tick manager
        self.state.tick_manager.subscribe_to_tick(self)
        self.state.tick_manager.subscribe_to_slow_tick(self)

    def tick(self):
        """Handles fast tick updates."""
        self.update_display()

    def slow_tick(self):
        """Handles slow tick updates."""
        if self.update_display_frame_count == 0:
            if not self.state.template_menu_open:
                self.root.attributes("-topmost", False)
                self.root.attributes("-topmost", True)
                if self.root.state() != "normal":
                    print_warning("Restoring minimized window!")
                    self.root.deiconify()

    def update_display(self):
        """Render and update the display based on the parsed template."""

        # Prevent updates while dragging
        if self.drag_handler.is_moving:
            return

        # Handle template updates
        if self.template_handler.pending_template_change:
            self.template_handler.cache_parsed_blocks()
            self.template_handler.pending_template_change = False

        parsed_blocks = self.template_handler.cached_parsed_blocks
        full_refresh_needed = False

        # Process each block
        for block in parsed_blocks:
            if self.process_block(block):
                full_refresh_needed = True

        # Only repack widgets if necessary
        if full_refresh_needed:
            self.repack_widgets(parsed_blocks)

        # Adjust window size dynamically
        self.adjust_window_size()

    def repack_widgets(self, parsed_blocks):
        """Repack widgets (for order preservation)"""
        parsed_block_ids = [block.get("label", f"block_{id(block)}") for block in parsed_blocks]
        for widget in self.display_frame.winfo_children():
            widget.pack_forget()
        for widget in self.widget_pool.get_widgets_in_order(parsed_block_ids):
            widget.pack(side=tk.LEFT, padx=0, pady=0)

    def process_block(self, block):
        """
        Processes a UI block by evaluating conditions, updating existing widgets, or creating
        new ones.

        If the block has a `condition`, it is evaluated, and the widget is removed if the condition
        fails.

        Otherwise, the function updates an existing widget or creates a new one if needed.

        Args:
            block (dict): Parsed template block containing type, label, function, and styling info.

        Returns:
            bool: True if a UI refresh is needed (widget added/removed), False otherwise.
        """
        block_type = block["type"]
        block_id = block.get("label", f"block_{id(block)}")
        block_metadata = self.template_handler.parser.block_registry.get(block_type, {})

        # Dynamically handle blocks with conditions
        if "condition" in block_metadata["keys"]:
            condition_function = block.get("condition")
            if condition_function:
                condition = get_dynamic_value(condition_function)
                if not condition:
                    # Remove the widget from the pool if the condition fails
                    if self.widget_pool.has_widget(block_id):
                        widget = self.widget_pool.get_widget(block_id)
                        self.widget_pool.remove_widget(block_id)
                        return True # Need refresh
                    return False

        # Attempt to retrieve an existing widget
        widget = self.widget_pool.get_widget(block_id)
        render_data_function = block_metadata.get("render")

        if widget: # Case: Widget exists, check for updates
            # Use render data function to get new configuration
            if render_data_function:
                render_config = render_data_function(block)

                # Check if the render function returned valid data
                if render_config:
                    # Update the existing widget if needed
                    if widget.cget("text") != render_config["text"] \
                    or widget.cget("fg") != render_config["color"]:
                        widget.config(text=render_config["text"], fg=render_config["color"])
                else:
                    # Remove the widget if the config is invalid (e.g., condition failed)
                    self.widget_pool.remove_widget(block_id)
        else: # Case: No existing widget, create a new one
            if render_data_function:
                render_config = render_data_function(block)
                if render_config:
                    # Create a new widget based on the render function's config
                    widget = tk.Label( self.display_frame, text=render_config["text"],
                                    fg=render_config["color"], bg=CONFIG.DARK_BG, font=CONFIG.FONT )
                    self.widget_pool.add_widget(block_id, widget)
                    widget.pack(side=tk.LEFT, padx=5, pady=5)
                    return True # Full refresh
            return False

    def adjust_window_size(self):
        """Adjust the window size dynamically based on content."""
        new_width = self.display_frame.winfo_reqwidth() + CONFIG.PADDING_X
        new_height = self.display_frame.winfo_reqheight() + CONFIG.PADDING_Y

        if new_width < 10 or new_height < 10:
            print_warning(f"Detected unusually small window size ({new_width}x{new_height})")

        self.root.geometry(f"{new_width}x{new_height}")

# --- Simbrief functionality --------------------------------------------------------------------
class SimBriefFunctions:
    """Contains grouping of static Simbrief Functions mainly for organizational purposes"""
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
            if "times" not in simbrief_json \
                or "navlog" not in simbrief_json \
                or "fix" not in simbrief_json["navlog"]:
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
    def update_countdown_from_simbrief(simbrief_json, simbrief_settings,
                                       gate_out_datetime=None, custom_time_option=None):
        """Update the countdown timer based on SimBrief data and optional manual gate-out time."""
        timer_source = CountdownState.TimerSource.USER_SELECTED_PRESET

        # Adjust gate-out time
        gate_time_offset = SimBriefFunctions.adjust_gate_out_delta(
            simbrief_json=simbrief_json,
            user_gate_time_dt=gate_out_datetime,
            simbrief_settings=simbrief_settings,
        )

        # Fetch selected SimBrief time
        # If custom_time_option is provided use that, otherwise use saved simbrief setting
        if custom_time_option is not None:
            selected_time = custom_time_option
            timer_source = CountdownState.TimerSource.AUTO_TIMER
        else:
            selected_time = simbrief_settings.selected_time_option

        # Use mapping to fetch the corresponding function
        function_to_call = SIMBRIEF_TIME_OPTION_FUNCTIONS.get(selected_time)

        if function_to_call:
            # Call the selected function
            future_time = function_to_call(simbrief_json)
            if not future_time:
               raise ValueError(f"No function mapped for selected_time_option: {selected_time}")
        else:
            raise ValueError(f"No function mapped for selected_time_option: {selected_time}")

        if not future_time:
             raise ValueError(f"Failed to extract '{selected_time.name}' from SimBrief data.")

        # Apply gate time offset and time adjustment
        future_time += gate_time_offset
        if simbrief_settings.use_adjusted_time:
            future_time = convert_real_world_time_to_sim_time(future_time)

        # Set countdown timer
        current_sim_time = get_simulator_datetime()
        print_debug(f"Simulator Datetime {current_sim_time}")
        countdown_state.set_future_time(future_time, current_sim_time,
                                            simbrief_settings, timer_source)

    @staticmethod
    def adjust_gate_out_delta(
        simbrief_json, user_gate_time_dt: datetime, simbrief_settings: SimBriefSettings
    ) -> timedelta:
        """
        Adjust the gate-out time based on SimBrief data and user-provided input.
        Returns the calculated gate time offset as a timedelta.
        """
        # Return zero if count_down state not yet set
        if countdown_state is None:
            return timedelta(0)

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

        # If user-provided gate-out time is available, calculate the offset
        if user_gate_time_dt:

            adjusted_delta = user_gate_time_dt - simbrief_gate_time

            print_debug("Gate Adjustment calculation")
            print_debug(f"user_gate_time_dt: {user_gate_time_dt}")
            print_debug(f"simbrief_gate_time: {simbrief_gate_time}")
            print_debug(f"adjusted_delta: {adjusted_delta}\n")

            # Save user-provided gate-out time
            simbrief_settings.gate_out_time = user_gate_time_dt
            return adjusted_delta

        # No user-provided gate-out time; use SimBrief defaults
        print_info("No user-provided gate-out time. Using SimBrief default gate-out time.")
        simbrief_settings.gate_out_time = None
        return timedelta(0)

    @staticmethod
    def parse_gate_out(gate_out_entry_value, simbrief_gate_time):
        """Parse gate out datetime from text, based on simbrief_gate_time"""

        print_debug(f"parse_gate_out: Received gate_out_entry_value: {gate_out_entry_value}")
        print_debug(f"parse_gate_out: SimBrief gate time: {simbrief_gate_time}")

        # Parse the user input (HHMM format)
        hours, minutes = int(gate_out_entry_value[:2]), int(gate_out_entry_value[2:])
        print_debug(f"parse_gate_out: Parsed user-entered time: {hours:02}:{minutes:02}")

        # Basic idea here is to check same day, prev day, next day and see which is closest to
        # given simbrief_gate_time
        candidate_same = simbrief_gate_time.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        candidate_prev = candidate_same - timedelta(days=1)
        candidate_next = candidate_same + timedelta(days=1)
        print_debug(f"parse_gate_out: Candidate (Same Day): {candidate_same}")
        print_debug(f"parse_gate_out: Candidate (Previous Day): {candidate_prev}")
        print_debug(f"parse_gate_out: Candidate (Next Day): {candidate_next}")
        candidates = [candidate_prev, candidate_same, candidate_next]
        best_candidate = min(candidates, key=lambda candidate: abs(candidate - simbrief_gate_time))

        print_debug(f"parse_gate_out: Best candidate selected: {best_candidate}")
        return best_candidate

# MAP SimBriefTimeOption to corresponding functions
SIMBRIEF_TIME_OPTION_FUNCTIONS = {
    SimBriefTimeOption.EST_IN:          SimBriefFunctions.get_simbrief_ofp_arrival_datetime,
    SimBriefTimeOption.TOD:             SimBriefFunctions.get_simbrief_ofp_tod_datetime,
    SimBriefTimeOption.EOBT:            SimBriefFunctions.get_simbrief_ofp_gate_out_datetime
}

# --- Drag functionality ------------------------------------------------------------------------
class DragHandler:
    """Handles window dragging."""

    def __init__(self, root):
        self.root = root
        self.is_moving = False
        self.offset_x = 0
        self.offset_y = 0

        # Bind events
        self.root.bind("<Button-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.do_move)
        self.root.bind("<ButtonRelease-1>", self.stop_move)

    def start_move(self, event):
        """Start moving the window."""
        self.is_moving = True
        self.offset_x = event.x
        self.offset_y = event.y

    def do_move(self, event):
        """Handle window movement."""
        if self.is_moving:
            deltax = event.x - self.offset_x
            deltay = event.y - self.offset_y
            new_x = self.root.winfo_x() + deltax
            new_y = self.root.winfo_y() + deltay
            self.root.geometry(f"+{new_x}+{new_y}")

    def stop_move(self, event):
        """Stop moving the window."""
        self.is_moving = False

# --- MAIN Function -----------------------------------------------------------------------------
def main():
    """Main entry point to script"""
    # Globals here necessary for template support
    global state, countdown_state  # pylint: disable=global-statement
    print_info("Starting custom status bar...")

    try:
        countdown_state = CountdownState()

        state = AppState()
        ui_manager = UIManager(state)

        # Root is used for scheduling (after call)
        root = ui_manager.get_root()

        service_manager = ServiceManager(state, state.settings, root)

        # Load template once all globals are initialized to ensure template file has proper scope
        ui_manager.template_handler.load_template_file()

        DarkmodeUtils.apply_dark_mode(root)
        optimize_gc(allocs=10_000, show_data=False)

        service_manager.start()     # Starts service tasks (background updater)
        state.start(root)           # Clocks user updates
        ui_manager.start()          # Clocks display updates

        root.mainloop()
    except ValueError as e:
        print_error(f"Error: {e}")
        print("Please check your DISPLAY_TEMPLATE and try again.")

# --- Utility Classes  --------------------------------------------------------------------------
class CountdownTimerDialog(tk.Toplevel):
    """A dialog to set the countdown timer and SimBrief settings"""
    def __init__(self, parent, app_state: AppState):
        super().__init__(parent)

        self.app_state = app_state
        self.simbrief_settings = app_state.settings.simbrief_settings

        # Fetch times from global count_down_state
        if countdown_state is not None:
            self.initial_time = countdown_state.last_entered_time
            self.gate_out_time = self.simbrief_settings.gate_out_time
        else:
            raise ValueError("CountdownTimerDialog: countdown_state not set!")

        # Forward declarations of UI components
        self.title_bar: Optional[tk.Frame] = None
        self.title_label: Optional[tk.Label] = None
        self.close_button: Optional[tk.Button] = None
        self.simbrief_entry: Optional[tk.Entry] = None
        self.gate_out_entry: Optional[tk.Entry] = None
        self.simbrief_checkbox_var: Optional[tk.BooleanVar] = None
        self.simbrief_checkbox: Optional[tk.Checkbutton] = None
        self.negative_timer_checkbox_var: Optional[tk.BooleanVar] = None
        self.negative_timer_checkbox: Optional[tk.Checkbutton] = None
        self.auto_update_var: Optional[tk.BooleanVar] = None
        self.auto_update_checkbox: Optional[tk.Checkbutton] = None
        self.selected_time_option: Optional[tk.StringVar] = None
        self.time_dropdown: Optional[tk.OptionMenu] = None
        self._drag_start_x: int = 0
        self._drag_start_y: int = 0

        self._setup_window(parent)

    def _setup_window(self, parent: tk.Tk):
        """Configure window properties (positioning, colors, focus, etc.)"""
        # Remove native title bar
        self.overrideredirect(True)

        # Ensure visibility before further actions
        self.wait_visibility()

        # Fix focus and interaction issues
        self.transient(parent)  # Keep the dialog on top of the parent
        self.grab_set()  # Prevent interaction with other windows

        # Window positioning
        parent_x, parent_y = parent.winfo_rootx(), parent.winfo_rooty()
        self.geometry(f"+{parent_x}+{parent_y}")

        # Define color themes
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
        tk.Label(countdown_frame, text="Enter Countdown Time (HHMM):",
                 bg=self.bg_color, fg=self.fg_color, font=large_font).pack(side="left", padx=5)
        self.time_entry = tk.Entry(countdown_frame, justify="center", bg=self.entry_bg_color,
                                    fg=self.entry_fg_color, font=("Helvetica", 16), width=10)
        if self.initial_time:
            self.time_entry.insert(0, self.initial_time)
        self.time_entry.pack(side="left", padx=5)

        # Add simbrief section (with collapsable section)
        self.build_simbrief_section(self, small_font)

        # OK and Cancel Buttons
        button_frame = tk.Frame(self, bg=self.bg_color)
        button_frame.pack(pady=20)
        tk.Button(  button_frame, text="OK", command=self.on_ok, bg=self.button_bg_color,
                    fg=self.button_fg_color, activebackground=self.entry_bg_color,
                    activeforeground=self.fg_color, font=small_font, width=10
                ).pack(side="left", padx=5)

        tk.Button(  button_frame, text="Cancel", command=self.on_cancel, bg=self.button_bg_color,
                    fg=self.button_fg_color, activebackground=self.entry_bg_color,
                    activeforeground=self.fg_color, font=small_font, width=10
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
        self.title_label = tk.Label(self.title_bar,
                                    text="Set Countdown Timer and SimBrief Settings",
                                    bg=self.title_bar_bg, fg=self.fg_color,
                                    font=("Helvetica", 10, "bold"))
        self.title_label.pack(side="left", padx=10)

        # Close Button
        self.close_button = tk.Button(self.title_bar, text="✕", command=self.on_cancel,
                                      bg=self.title_bar_bg, fg=self.fg_color, relief="flat",
                                      font=("Helvetica", 10, "bold"), activebackground="#FF0000",
                                      activeforeground=self.fg_color)
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
                self.simbrief_settings.gate_out_time,
            ),
        )
        simbrief_section.pack(fill="x", padx=10, pady=5)

        # Expand section if SimBrief username exists
        if self.simbrief_settings.username.strip():
            simbrief_section.expand()

    def simbrief_content(self, frame, small_font, simbrief_username,
                         use_simbrief_adjusted_time, gate_out_time):
        """Build the SimBrief components inside the collapsible section."""
        # Outer Frame for Padding
        outer_frame = tk.Frame(frame, bg=self.bg_color)
        outer_frame.pack(fill="x", padx=10, pady=0)

        # SimBrief Username and Gate Out Time Group
        input_frame = tk.Frame(outer_frame, bg=self.bg_color)
        input_frame.pack(fill="x", pady=2)

        # SimBrief Username
        tk.Label(
            input_frame, text="SimBrief Username:", bg=self.bg_color,
            fg=self.fg_color, font=small_font).grid(row=0, column=0, sticky="w", padx=5, pady=2)

        self.simbrief_entry = tk.Entry(
            input_frame, justify="left", bg=self.entry_bg_color, fg=self.entry_fg_color,
            font=small_font, width=25
        )
        if simbrief_username:
            self.simbrief_entry.insert(0, simbrief_username)
        self.simbrief_entry.grid(row=0, column=1, sticky="w", padx=5, pady=2)

        # Gate Out Time
        tk.Label(
            input_frame, text="Gate Out Time (HHMM):", bg=self.bg_color, fg=self.fg_color,
              font=small_font).grid(row=1, column=0, sticky="w", padx=5, pady=2)

        self.gate_out_entry = tk.Entry(
            input_frame, justify="left", bg=self.entry_bg_color, fg=self.entry_fg_color,
            font=small_font, width=25 )
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
        self.negative_timer_checkbox_var = tk.BooleanVar(
            value=self.simbrief_settings.allow_negative_timer)
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
        self.auto_update_var = tk.BooleanVar(value=self.simbrief_settings.auto_update_enabled)
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
            time_selection_frame, text="Select SimBrief Time:", bg=self.bg_color,
            fg=self.fg_color, font=small_font
        ).grid(row=0, column=0, sticky="w", padx=5, pady=2)

        if isinstance(self.simbrief_settings.selected_time_option, str):
            # If it's already a string, assign it directly
            self.selected_time_option = tk.StringVar(
                                            value=self.simbrief_settings.selected_time_option )
        elif isinstance(self.simbrief_settings.selected_time_option, Enum):
            # If it's an Enum, use its value
            self.selected_time_option = tk.StringVar(
                value=self.simbrief_settings.selected_time_option.value )
        else:
            # Handle unexpected types
            print_warning("Invalid type for selected_time_option")

        # Create the OptionMenu regardless of input type
        self.time_dropdown = tk.OptionMenu(
            time_selection_frame,
            self.selected_time_option,
            *[option.value for option in SimBriefTimeOption],  # Use the enum values for options
        )
        self.time_dropdown.configure(bg=self.entry_bg_color, fg=self.entry_fg_color,
                                     highlightthickness=0, font=small_font)
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

    def on_cancel(self):
        """Cancel the dialog."""
        self.destroy()

    def on_ok(self):
        """
        Validate user input, update SimBrief settings, and set the countdown timer if time
        is provided.
        """
        print_debug("on_ok---------------------------")

        # Update SimBrief settings from dialog inputs
        self.update_simbrief_settings()

        # Save SimBrief settings regardless of whether a username is provided
        settings = self.app_state.settings
        self.app_state.settings_manager.save_settings(settings)

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

            # Save last entered time so it shows next time
            countdown_state.last_entered_time = time_text

        # Close the dialog
        self.destroy()

    def pull_time(self):
        """Pull the selected time from SimBrief and update the countdown timer."""
        try:
            print_debug("pull_time started")

            # Update SimBrief settings from the dialog inputs
            self.update_simbrief_settings()

            # Save the updated SimBrief settings
            settings = self.app_state.settings
            self.app_state.settings_manager.save_settings(settings)

            # Validate the SimBrief username
            if not self.validate_simbrief_username():
                print_debug("DEBUG: Invalid SimBrief username. Exiting pull_time.")
                return

            # Fetch SimBrief data
            simbrief_json = SimBriefFunctions.get_latest_simbrief_ofp_json(
                self.simbrief_settings.username)
            if not simbrief_json:
                messagebox.showerror("Error", "Failed to fetch SimBrief data. "
                                     "Please check your username.")
                print_debug("DEBUG: SimBrief data fetch failed.")
                return

            # Get manual gate-out time entry, if provided
            gate_out_entry_value = (
                self.gate_out_entry.get().strip() if self.gate_out_entry else None
            )

            gate_out_datetime = None

            # Parse datetime
            if gate_out_entry_value is not None and not gate_out_entry_value == "":
                simbrief_gate_out = SimBriefFunctions \
                                            .get_simbrief_ofp_gate_out_datetime(simbrief_json)
                gate_out_datetime = SimBriefFunctions \
                                            .parse_gate_out(gate_out_entry_value, simbrief_gate_out)

            # Update countdown timer using the shared method
            SimBriefFunctions.update_countdown_from_simbrief(
                simbrief_json=simbrief_json,
                simbrief_settings=self.simbrief_settings,
                gate_out_datetime=gate_out_datetime
            )

            print_debug("Countdown timer updated successfully from SimBrief.")

            self.destroy()
        except RuntimeError as re:
            messagebox.showerror("Error", f"Failed to update the countdown timer from SimBrief. {re}")
        except ValueError as ve:
            messagebox.showerror("Error", f"Failed to update the countdown timer from SimBrief. {ve}")
            print_error("Countdown timer update failed.")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")
            print_error(f"Exception in pull_time: {e}")

    def update_simbrief_settings(self):
        """Update SimBrief settings from dialog inputs."""
        self.simbrief_settings.username = self.simbrief_entry.get().strip()
        self.simbrief_settings.use_adjusted_time = self.simbrief_checkbox_var.get()

        # Validate selected_time_option - ignore custom values
        selected_time = self.selected_time_option.get()
        if selected_time in [option.value for option in SimBriefTimeOption]:
            self.simbrief_settings.selected_time_option = SimBriefTimeOption(selected_time)

        self.simbrief_settings.allow_negative_timer = self.negative_timer_checkbox_var.get()
        self.simbrief_settings.auto_update_enabled = self.auto_update_var.get()

        self.simbrief_settings.gate_out_time = self.gate_out_time

    def validate_simbrief_username(self):
        """Validate SimBrief username and show an error if invalid."""
        if not self.simbrief_settings.username:
            messagebox.showerror("Error", "Please enter a SimBrief username.")
            return False
        return True

    def fetch_simbrief_data(self):
        """Fetch and return SimBrief JSON data."""
        simbrief_json = SimBriefFunctions.get_latest_simbrief_ofp_json(
                                                                self.simbrief_settings.username)
        if not simbrief_json:
            messagebox.showerror("Error", "Failed to fetch SimBrief data. "
                                 "Please check the username or try again.")
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
        """Set the countdown timer and update global state."""
        current_sim_time = get_simulator_datetime()
        simbrief_settings = self.app_state.settings.simbrief_settings
        timer_source = CountdownState.TimerSource.USER_TIMER
        if countdown_state.set_future_time(future_time, current_sim_time,
                                           simbrief_settings, timer_source):
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
        self.configure( bg=self.bg_color, highlightbackground=self.border_color,
                        highlightthickness=1)

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

class TickManager:
    """
    Handles scheduling and notifying tick subscribers.
    Used to handle timing for user calls and display update
    """
    UPDATE_INTERVAL = 33
    SLOW_UPDATE_INTERVAL = 500
    SLOW_UPDATE_TICKS = SLOW_UPDATE_INTERVAL // UPDATE_INTERVAL

    def __init__(self):
        """Initialize tick tracking and subscriber lists."""
        self.tick_count = 0
        self.root = None  # Assigned when `start()` is called

        # Crate tick subscriber sets
        self.tick_subscribers = set()
        self.slow_tick_subscribers = set()

    def start(self, root):
        """Start ticking using Tkinter's scheduler."""
        self.root = root
        self.tick()

    def tick(self):
        """Called every `update_interval` to notify subscribers."""
        self.tick_count += 1

        # Notify fast tick subscribers
        for subscriber in self.tick_subscribers:
            subscriber.tick()

        # If slow tick interval is reached
        if self.tick_count >= self.SLOW_UPDATE_TICKS:
            for subscriber in self.slow_tick_subscribers:
                subscriber.slow_tick()
            self.tick_count = 0  # Reset tick count

        # Schedule the next tick
        self.root.after(self.UPDATE_INTERVAL, self.tick)

    def subscribe_to_tick(self, subscriber):
        """Register a component for fast tick updates."""
        self._validate_subscriber(subscriber, "tick")
        self.tick_subscribers.add(subscriber)

    def subscribe_to_slow_tick(self, subscriber):
        """Register a component for slow tick updates."""
        self._validate_subscriber(subscriber, "slow_tick")
        self.slow_tick_subscribers.add(subscriber)

    @staticmethod
    def _validate_subscriber(subscriber, method_name):
        """Ensure the subscriber implements the required method."""
        if not hasattr(subscriber, method_name) or not callable(getattr(subscriber, method_name)):
            raise TypeError(f"Subscriber {subscriber.__class__.__name__} "
                            f"must implement '{method_name}()'")

class WidgetPool:  # pylint: disable=missing-function-docstring
    """Manages Tkinter widgets and their order - used by DisplayUpdater"""
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

# --- Template handling  ------------------------------------------------------------------------
class TemplateHandler:
    """Class to manage the template file and selected template."""
    def __init__(self):
        """Initialize the TemplateHandler with the given settings."""
        self.parser = TemplateParser()  # Initialize the parser

        self.templates = self.load_templates()  # Load templates from file
        self.selected_template_name = next(iter(self.templates), None)

        self.cached_parsed_blocks = []  # Cache parsed blocks for the selected template
        self.pending_template_change = False  # Track if the template was changed

    def load_template_file(self):
        """Initialization - separated so we can carefully determine injection point of template"""
        if not self.selected_template_name:
            raise ValueError("No templates available to select.")

        self.load_template_functions()
        self.cache_parsed_blocks()

    def load_templates(self) -> dict[str, str]:
        """Load templates from the template file, creating the file if necessary."""
        os.makedirs(CONFIG.SETTINGS_DIR, exist_ok=True)

        if not os.path.exists(CONFIG.TEMPLATE_FILE):
            with open(CONFIG.TEMPLATE_FILE, "w", encoding="utf-8") as f:
                f.write(DEFAULT_TEMPLATES.strip())
            print(f"Created default template file at {CONFIG.TEMPLATE_FILE}")

        try:
            spec = importlib.util.spec_from_file_location("status_bar_templates",
                                                          CONFIG.TEMPLATE_FILE)
            templates_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(templates_module)
            return templates_module.TEMPLATES if hasattr(templates_module, "TEMPLATES") else {}
        except Exception as e:
            print(f"Error loading templates: {e}")
            return {}

    def load_template_functions(self):
        """Dynamically import functions from the template file and inject only relevant globals."""
        try:
            spec = importlib.util.spec_from_file_location("status_bar_templates",
                                                          CONFIG.TEMPLATE_FILE)
            templates_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(templates_module)

            # First, filter globals to exclude built-ins and modules
            relevant_globals = {
                k: v for k, v in globals().items()
                if not k.startswith("__") and not isinstance(v, type(importlib))  # Exclude built-ins and modules
            }

            # Debug: Log the filtered globals being injected, grouping functions properly
            #self._print_sorted_globals(relevant_globals)

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
                "render": self.get_var_data,
            },
            "VARIF": {
                "keys": ["label", "function", "color", "condition"],
                "render": self.get_varif_data,
            },
            "STATIC_TEXT": {
                "keys": ["value"],
                "render": self.get_static_text_data,
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

    def get_var_data(self, block):
        """Obtain render data for a VAR block"""
        static_text = self.process_label_with_dynamic_functions(block["label"])
        value = str(get_dynamic_value(block["function"]))

        return {
            "text": f"{static_text} {value}",
            "color": block["color"]
        }

    def get_varif_data(self, block):
        """Obtain render data for a varif block"""
        condition = bool(get_dynamic_value(block["condition"]))
        if condition:
            static_text = self.process_label_with_dynamic_functions(block["label"])
            # If function is not set then ignore it
            if block["function"] == "''" or not block["function"].strip():
                value = ""
            else:
                value = get_dynamic_value(block["function"])
            return {
                "text": f"{static_text} {value}",
                "color": block["color"]
            }
        return None

    def get_static_text_data(self, block):
        """Obtain static text render data"""
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
                while name_start >= 0 and (template_string[name_start].isalnum()
                or template_string[name_start] == "_"):
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
