# fenix_lights.py: Applies preset lighting to the cockpit lights on the Fenix A320
# Requires the Mobiflight Wasm module
# https://kb.fenixsim.com/example-of-how-to-use-lvars
# https://github.com/Koseng/MSFSPythonSimConnectMobiFlightExtension/

from time import sleep
from simconnect_mobiflight.simconnect_mobiflight import SimConnectMobiFlight
from Lib.extended_mobiflight_variable_requests import ExtendedMobiFlightVariableRequests
import sys

try:
    # Import all color print functions
    from Lib.color_print import *

except ImportError:
    print("Failed to import 'Lib.color_print'. Please ensure /Lib/color_print.py is present")
    sys.exit(1)

# Lighting LVARs with default values
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
}

MAX_RETRIES = 5  # Maximum number of retries if a value doesn't set correctly
RETRY_DELAY = 0.1  # Delay in seconds between retries

def set_and_verify_lvar(mf_requests, lvar, value):
    """
    Sets an LVAR to a specified value and verifies it. Retries if necessary.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        # Attempt to set the LVAR
        req_str = f"{value} (> {lvar})"
        mf_requests.set(req_str)
        sleep(RETRY_DELAY)  # Allow time for the simulator to apply the value

        # Check if the value was successfully applied
        current_value = mf_requests.get(f"({lvar})")
        if current_value == value:
            print_info(f"[SUCCESS] {lvar} set to {value} on attempt {attempt}. Current value: {current_value}")
            return True

        print_warning(f"[RETRY] {lvar} not set to {value}. Current value: {current_value}. Retrying ({attempt}/{MAX_RETRIES})...")

    print_error(f"[FAILURE] Could not set {lvar} to {value} after {MAX_RETRIES} attempts.")
    return False

def main():
    try:
        # Initialize the SimConnect connection
        sm = SimConnectMobiFlight()
        mf_requests = ExtendedMobiFlightVariableRequests(sm, "fenix_set_lighting_defaults")

        mf_requests.clear_sim_variables()

        # Prime the library - possibly necessary to ensure the connection works properly
        altitude = mf_requests.get("(A:PLANE ALTITUDE,Feet)")
        print_info(f"Primed with altitude: {altitude}")

        # Set all lighting LVARs to their default values with retry mechanism
        for lvar_name, default_value in LIGHTING_LVARS.items():
            set_and_verify_lvar(mf_requests, lvar_name, default_value)

    except ConnectionError as e:
        print_info(f"Could not connect to Flight Simulator: {e}")
        print_info("Make sure MSFS is running and try again.")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
