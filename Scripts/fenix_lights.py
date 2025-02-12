"""
fenix_lights.py: Applies preset lighting to the cockpit lights on the Fenix A320
Requires the Mobiflight Wasm module
https://kb.fenixsim.com/example-of-how-to-use-lvars
https://github.com/Koseng/MSFSPythonSimConnectMobiFlightExtension/
"""

import logging
import os
import json
import sys
import time
from time import sleep
from queue import Queue
import threading

from Lib.mobiflight_connection import MobiflightConnection, set_and_verify_lvar
from Lib.color_print import print_info, print_error
from Lib.pygame_joy import PygameJoy

# Disable warnings - still shows errors
logging.getLogger("SimConnect.SimConnect").setLevel(logging.ERROR)

# --- Constants & Global Variables ---

# Lighting LVARs with default values (will be assigned at start)
LIGHTING_LVARS = {
    "L:S_OH_INT_LT_DOME": 0,                # Dome Light (0,1,2)
    "L:A_OH_LIGHTING_OVD": 100,             # Overhead backlighting (0-100)
    "L:A_MIP_LIGHTING_MAP_L": 0.1,          # Left Map Lighting
    "L:A_MIP_LIGHTING_MAP_R": 0.1,          # Right Map Lighting
    "L:A_MIP_LIGHTING_FLOOD_MAIN": 0.1,     # Flood Light - Main Panel
    "L:A_MIP_LIGHTING_FLOOD_PEDESTAL": 0.1, # Flood Light - Pedestal
    "L:A_PED_LIGHTING_PEDESTAL": 1,         # Panel & Pedestal (button backlight)
    "L:A_CHART_LIGHT_TEMP_FO": 0,           # FO window brightness knob
    "L:S_CHART_LIGHT_TEMP_FO": 0,           # FO chart light switch
    "L:A_CHART_LIGHT_TEMP_CAPT": 0,         # Capt window brightness knob
    "L:S_CHART_LIGHT_TEMP_CAPT": 0,         # Capt chart light switch
    "L:S_MIP_LIGHT_CONSOLEFLOOR_CAPT": 0,   # Console floor light (capt)
    "L:S_MIP_LIGHT_CONSOLEFLOOR_FO": 0      # Console floor light (FO)
}

# List of screen LVARs to control (for display brightness propagation)
DISPLAY_LVARS = [
    "L:A_DISPLAY_BRIGHTNESS_CO",
    "L:A_DISPLAY_BRIGHTNESS_FO",
    "L:A_DISPLAY_BRIGHTNESS_CI",
    "L:A_DISPLAY_BRIGHTNESS_CI_OUTER",
    "L:A_DISPLAY_BRIGHTNESS_FI",
    "L:A_DISPLAY_BRIGHTNESS_FI_OUTER",
    "L:A_DISPLAY_BRIGHTNESS_ECAM_L",
    "L:A_DISPLAY_BRIGHTNESS_ECAM_U"
]

# Settings file paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_DIR = os.path.join(BASE_DIR, "Settings")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "fenix_lights.json")

# Default LVAR wait condition (e.g., ground power)
DEFAULT_WAIT_LVAR = "L:S_OH_ELEC_EXT_PWR"
DEFAULT_WAIT_VALUE = 1

# --- Settings & Setup Functions ---

def load_settings():
    """Load user settings from the settings file."""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as file:
            return json.load(file)
    return None

def save_settings(settings):
    """Save user settings to the settings file."""
    with open(SETTINGS_FILE, "w") as file:
        json.dump(settings, file, indent=4)

def setup():
    """Initial setup to collect user preferences."""
    settings = {}
    print_info("Welcome to the Fenix A320 Lighting Manager setup!")
    assign_joystick = input("Do you want to assign a joystick axis to control screen brightness? (y/n): ").strip().lower()
    if assign_joystick == "y":
        joystick = PygameJoy()
        joystick.prompt_for_joystick()
        axis_to_use = joystick.input_get_axis(msg="Move an axis to assign to screen brightness:")
        settings["joystick_enabled"] = True
        settings["joystick_name"] = joystick.get_joystick_name()
        settings["axis_id"] = axis_to_use
    else:
        settings["joystick_enabled"] = False
    save_settings(settings)
    print_info("Setup complete! Settings saved.")
    return settings

# --- Lighting & Joystick Functions ---

def set_cockpit_lights(mf_requests):
    """Set all cockpit lighting LVARs to their default values."""
    for lvar_name, default_value in LIGHTING_LVARS.items():
        # First set to a known (max) value then to the default
        set_and_verify_lvar(mf_requests, lvar_name, 1)
        set_and_verify_lvar(mf_requests, lvar_name, 0)
        set_and_verify_lvar(mf_requests, lvar_name, default_value)

def propagate_lvars(mf_requests, co_value):
    """
    Propagate the 'L:A_DISPLAY_BRIGHTNESS_CO' value to other display LVARs.
    This ensures all screen brightness values are synchronized.
    """
    for lvar in DISPLAY_LVARS:
        if lvar != "L:A_DISPLAY_BRIGHTNESS_CO":  # Skip the master variable
            set_and_verify_lvar(mf_requests, lvar, co_value, tolerance=None, max_retries=1, retry_delay=0)

def joystick_init(settings):
    """Initialize joystick control if enabled."""
    joystick = None
    axis_to_use = None
    if settings.get("joystick_enabled", True):
        joystick = PygameJoy(joystick_name=settings["joystick_name"])
        axis_to_use = settings["axis_id"]
        print_info(f"Joystick initialized: {joystick.get_joystick_name()} (Axis: {axis_to_use})")
    else:
        print_info("Joystick control is disabled in settings.")
    return joystick, axis_to_use

def main_screen_update_loop(mf_requests, joystick, axis_to_use, settings):
    """Continuously update cockpit screen brightness based on joystick or knob changes."""
    previous_axis_value = None
    previous_co_value = None
    while True:
        try:
            current_co_value = mf_requests.get("(L:A_DISPLAY_BRIGHTNESS_CO)")

            if settings["joystick_enabled"]:
                joystick.update()
                axis_value = joystick.get_axis_value(axis_to_use)
                # Scale the joystick axis value appropriately
                scaled_value = -axis_value

            # If the joystick value has changed, update the master LVAR and propagate
            if settings["joystick_enabled"] and (previous_axis_value is None or scaled_value != previous_axis_value):
                set_and_verify_lvar(mf_requests, "L:A_DISPLAY_BRIGHTNESS_CO", scaled_value,
                                    tolerance=None, max_retries=1, retry_delay=0)
                propagate_lvars(mf_requests, scaled_value)
                previous_axis_value = scaled_value
                previous_co_value = scaled_value

            # If the master LVAR has been independently changed, propagate that change
            elif previous_co_value is None or current_co_value != previous_co_value:
                propagate_lvars(mf_requests, current_co_value)
                previous_co_value = current_co_value

            sleep(0.1)

        except Exception as e:
            print_error(f"Error in main screen update loop: {e}")
            raise  # Propagate the error to trigger a full restart

# --- Main Routine ---

def main():
    try:
        # Load settings (or run setup if none exist)
        settings = load_settings()
        if settings is None:
            settings = setup()

        # Create a MobiflightConnection instance and connect
        mobiflight = MobiflightConnection(client_name="fenix_set_lighting_defaults")
        mobiflight.connect()
        mf_requests = mobiflight.get_request_handler()

        # Prime the library by reading the altitude
        altitude = mf_requests.get("(A:PLANE ALTITUDE,Feet)")
        print_info(f"Primed with altitude: {altitude}")

        # Wait for the required LVAR (ground power) to be active
        mobiflight.wait_for_lvar(DEFAULT_WAIT_LVAR, DEFAULT_WAIT_VALUE)

        print_info("Setting interior light values...")
        set_cockpit_lights(mf_requests)
        print_info("Setting interior light values... DONE")

        # Initialize joystick if enabled
        joystick, axis_to_use = joystick_init(settings)

        # Enter the main update loop for cockpit display brightness
        main_screen_update_loop(mf_requests, joystick, axis_to_use, settings)

    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        raise  # Allow the exception to bubble up for the outer loop to restart

if __name__ == "__main__":
    # Outer loop: if main() fails (e.g., connection lost), restart after a short delay.
    while True:
        try:
            main()
        except Exception as e:
            print_error(f"Restarting main loop due to error: {e}")
            time.sleep(10)
