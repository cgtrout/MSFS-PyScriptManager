"""
fenix_disable_efb.py: Shows an example of how you can disable the Fenix A32x EFBs using a script
 https://kb.fenixsim.com/example-of-how-to-use-lvars - use this tutorial to see how to find other lvars
 - uses https://github.com/Koseng/MSFSPythonSimConnectMobiFlightExtension/ extension library for reading from Mobiflight
"""
import sys
import time
import logging
from Lib.mobiflight_connection import MobiflightConnection
from Lib.color_print import print_info, print_error

# Disable warnings - still shows errors
logging.getLogger("SimConnect.SimConnect").setLevel(logging.ERROR)

# Constants for LVARs
EFB_VISIBLE_CAPT = "L:S_EFB_VISIBLE_CAPT"
EFB_CHARGING_CAPT = "L:S_EFB_CHARGING_CABLE_CAPT"
EFB_VISIBLE_FO = "L:S_EFB_VISIBLE_FO"
EFB_CHARGING_FO = "L:S_EFB_CHARGING_CABLE_FO"

# Default LVAR to wait for before execution
DEFAULT_WAIT_LVAR = ""  # Can be changed
DEFAULT_WAIT_VALUE = 1

def main():
    try:
        # Initialize Mobiflight connection
        mobiflight = MobiflightConnection(client_name="fenix_disable_efb")
        mobiflight.connect()
        mf_requests = mobiflight.get_request_handler()

        # Prime the library
        altitude = mf_requests.get("(A:PLANE ALTITUDE,Feet)")
        print_info(f"Primed with altitude: {altitude}")

        # Wait for the required LVAR before proceeding
        mobiflight.wait_for_lvar("L:S_OH_ELEC_EXT_PWR")

        # Disable EFBs
        mobiflight.set_and_verify_lvar(EFB_VISIBLE_CAPT, 0)
        mobiflight.set_and_verify_lvar(EFB_CHARGING_CAPT, 0)
        mobiflight.set_and_verify_lvar(EFB_VISIBLE_FO, 0)
        mobiflight.set_and_verify_lvar(EFB_CHARGING_FO, 0)

        print_info("EFBs disabled successfully.")
        print_info("This script will now shut down - restart if if you need to disable again.")

    except Exception as e:
        print_error(f"Error detected, restarting script: {e}")

if __name__ == "__main__":
    main()
