# fenix_lights.py: Applies preset lighting to the cockpit lights on the Fenix A320
# Requires the Mobiflight Wasm module
# https://kb.fenixsim.com/example-of-how-to-use-lvars
# https://github.com/Koseng/MSFSPythonSimConnectMobiFlightExtension/

from time import sleep
import os
import json
from simconnect_mobiflight.simconnect_mobiflight import SimConnectMobiFlight
from Lib.extended_mobiflight_variable_requests import ExtendedMobiFlightVariableRequests
import sys
from queue import Queue
import threading

try:
    from Lib.color_print import *
    from Lib.pygame_joy import *
except ImportError:
    print("MSFS-PyScriptManager: Please ensure /Lib dir is present")
    sys.exit(1)

# Initialization Lighting LVARs with default values - these values will be assigned by script
# at start of script
LIGHTING_LVARS = {
    "L:S_OH_INT_LT_DOME": 0,                # Default value for Dome Light (0,1,2)
    "L:A_OH_LIGHTING_OVD": 100,             # Overhead backlighting (0-100)
    "L:A_MIP_LIGHTING_MAP_L": 0.1,          # Default value for Left Map Lighting
    "L:A_MIP_LIGHTING_MAP_R": 0.1,          # Default value for Right Map Lighting
    "L:A_MIP_LIGHTING_FLOOD_MAIN": 0.1,     # FLOOD LT MAIN PNL
    "L:A_MIP_LIGHTING_FLOOD_PEDESTAL": 0.1, # Flood Light - PED
    "L:A_PED_LIGHTING_PEDESTAL": 1,         # INTEG LT MAIN PNL & PED (button backlight)
    "L:A_CHART_LIGHT_TEMP_FO": 0,           # Brightness knob on FO window
    "L:S_CHART_LIGHT_TEMP_FO": 0,           # Switch for chart light (captain)
    "L:A_CHART_LIGHT_TEMP_CAPT": 0,         # Brightness knob on capt window
    "L:S_CHART_LIGHT_TEMP_CAPT": 0,         # Switch for chart light (captain)
    "L:S_MIP_LIGHT_CONSOLEFLOOR_CAPT": 0,   # Console floor light (captain)
    "L:S_MIP_LIGHT_CONSOLEFLOOR_FO": 0      # Console floor light (FO)
}

# List of screen LVARs to control
# These will be linked to far left captain side screen control (PFD Brightness)
# AND/OR joystick bind
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

# Set settings file path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_DIR = os.path.join(BASE_DIR, "Settings")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "fenix_lights.json")

MAX_RETRIES = 5  # Maximum number of retries if a value doesn't set correctly
RETRY_DELAY = 0.1  # Delay in seconds between retries

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

    # Prompt user for joystick axis assignment
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

def set_cockpit_lights(mf_requests):
    """Iterate through cockpit lights and set them to values"""
    for lvar_name, default_value in LIGHTING_LVARS.items():
        # Set to max value then default value
        set_and_verify_lvar(mf_requests, lvar_name, 1.0)
        set_and_verify_lvar(mf_requests, lvar_name, default_value)

def set_and_verify_lvar(mf_requests, lvar, value, tolerance=0.01, max_retries=MAX_RETRIES, retry_delay=RETRY_DELAY):
    """
    Sets an LVAR to a specified value and verifies it within a tolerance. Retries if necessary.
    If tolerance is None, disables the verification step entirely.
    """
    for attempt in range(1, max_retries + 1):
        # Attempt to set the LVAR
        req_str = f"{value} (> {lvar})"
        mf_requests.set(req_str)

        # Skip verification if tolerance is None
        if tolerance is None:
            #print_info(f"[INFO] {lvar} set to {value} (verification disabled).")
            return True

        sleep(retry_delay)  # Allow time for the simulator to apply the value

        # Check if the value was successfully applied within the tolerance
        current_value = mf_requests.get(f"({lvar})")
        if abs(current_value - value) <= tolerance:
            #print_info(f"[SUCCESS] {lvar} set to {value} on attempt {attempt}. Current value: {current_value}")
            return True

        #print_warning(f"[RETRY] {lvar} not set to {value}. Current value: {current_value}. Retrying ({attempt}/{max_retries})...")

    # Enhanced error message with actual vs expected values
    print_error(
        f"[FAILURE] Could not set {lvar} to {value} (current value: {current_value}) "
        f"within tolerance {tolerance} after {max_retries} attempts."
    )
    return False

def propagate_lvars(mf_requests, co_value):
    """
    Propagate 'L:A_DISPLAY_BRIGHTNESS_CO' value to other LVARs.
    This is so display brightness can be used to control all screen values
    """
    for lvar in DISPLAY_LVARS:
        if lvar != "L:A_DISPLAY_BRIGHTNESS_CO":  # Skip the master variable
            set_and_verify_lvar(mf_requests, lvar, co_value, tolerance=None,
                max_retries=1, retry_delay=0, )

def joystick_init(settings):
    # Joystick initialization if enabled in settings
    joystick = None
    axis_to_use = None
    if settings.get("joystick_enabled", True):
        joystick = PygameJoy(joystick_name=settings["joystick_name"])
        axis_to_use = settings["axis_id"]
        print_info(f"Joystick initialized: {joystick.get_joystick_name()} (Axis: {axis_to_use})")
    else:
        print_info("Joystick control is disabled in settings.")
    return joystick, axis_to_use

def main_screen_update_loop(mf_requests, joystick:PygameJoy, axis_to_use, settings):
    """Continuously update cockpit screen lighting either based on axis or on left disp knob"""
    # Variables to track changes
    previous_axis_value = None
    previous_co_value = None

    while True:
        # Get the current value of "L:A_DISPLAY_BRIGHTNESS_CO"
        current_co_value = mf_requests.get("(L:A_DISPLAY_BRIGHTNESS_CO)")

        if settings["joystick_enabled"]:
            # Update joystick state
            joystick.update()

            # Read the joystick axis value
            axis_value = joystick.get_axis_value(axis_to_use)

            # Scale the joystick axis value to the LVAR range
            scaled_value = -axis_value

        # Detect joystick axis change
        if settings["joystick_enabled"] and (previous_axis_value is None or scaled_value != previous_axis_value):
            # Update "L:A_DISPLAY_BRIGHTNESS_CO" from joystick
            set_and_verify_lvar( mf_requests,"L:A_DISPLAY_BRIGHTNESS_CO",
                scaled_value, tolerance=None, max_retries=1, retry_delay=0, )

            # Propagate the updated value to all other LVARs
            propagate_lvars(mf_requests, scaled_value)

            # Update previous values
            previous_axis_value = scaled_value
            previous_co_value = scaled_value

        # Detect independent "L:A_DISPLAY_BRIGHTNESS_CO" change
        elif previous_co_value is None or current_co_value != previous_co_value:
            # Propagate the new "L:A_DISPLAY_BRIGHTNESS_CO" value to all other LVARs
            propagate_lvars(mf_requests, current_co_value)

            # Update the previous "L:A_DISPLAY_BRIGHTNESS_CO" value
            previous_co_value = current_co_value

        sleep(0.1)

def main():
    try:
        # Load Settings
        settings = load_settings()
        if settings is None:
            settings = setup()

        # Initialize the SimConnect connection
        client_name = "fenix_set_lighting_defaults"
        sm = SimConnectMobiFlight()
        mf_requests = ExtendedMobiFlightVariableRequests(sm, client_name)
        mf_requests.clear_sim_variables()

        # Prime the library - possibly necessary to ensure the connection works properly
        _ = mf_requests.get("(A:PLANE ALTITUDE,Feet)")

        # Set all lighting LVARs to their default values with retry mechanism
        print_info("Setting interior light values...")
        set_cockpit_lights(mf_requests)
        print_info("Setting interior light values... DONE")

        # Initialize joystick
        joystick, axis_to_use = joystick_init(settings)

        # Main lighting update loop
        main_screen_update_loop(mf_requests, joystick, axis_to_use, settings)

    except ConnectionError as e:
        print_info(f"Could not connect to Flight Simulator: {e}")
        print_info("Make sure MSFS is running and try again.")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
