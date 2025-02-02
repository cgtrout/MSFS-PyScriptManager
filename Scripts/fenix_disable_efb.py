# fenix_disable_efb.py: Shows an example of how you can disable the Fenix A32x EFBs using a script
#  https://kb.fenixsim.com/example-of-how-to-use-lvars - use this tutorial to see how to find other lvars
# - uses https://github.com/Koseng/MSFSPythonSimConnectMobiFlightExtension/ extension library for reading from Mobiflight
import sys
from time import sleep
from simconnect_mobiflight.simconnect_mobiflight import SimConnectMobiFlight
from Lib.extended_mobiflight_variable_requests import ExtendedMobiFlightVariableRequests, set_and_verify_lvar

try:
    from Lib.color_print import *
except ImportError:
    print("MSFS-PyScriptManager: Please ensure /Lib dir is present")
    sys.exit(1)

# Constants for LVARs
EFB_VISIBLE_CAPT = "L:S_EFB_VISIBLE_CAPT"
EFB_CHARGING_CAPT = "L:S_EFB_CHARGING_CABLE_CAPT"
EFB_VISIBLE_FO = "L:S_EFB_VISIBLE_FO"
EFB_CHARGING_FO = "L:S_EFB_CHARGING_CABLE_FO"

def main():
    try:
        # Initialize the SimConnect connection
        sm = SimConnectMobiFlight()
        mf_requests = ExtendedMobiFlightVariableRequests(sm, "fenix_disable_efb")

        mf_requests.clear_sim_variables()

        # Prime the library - possibly necessary to ensure the connection works properly?
        # TODO determine what causes this
        altitude = mf_requests.get("(A:PLANE ALTITUDE,Feet)")
        print(f"Primed with altitude: {altitude}")

        # Set values for Captain's EFB visibility and charging cable
        # Setting to 0 hides these in this case
        set_and_verify_lvar(mf_requests, EFB_VISIBLE_CAPT, 0)
        set_and_verify_lvar(mf_requests, EFB_CHARGING_CAPT, 0)

        # Set values for First Officer's EFB visibility and charging cable
        # Setting to 0 hides
        set_and_verify_lvar(mf_requests, EFB_VISIBLE_FO, 0)
        set_and_verify_lvar(mf_requests, EFB_CHARGING_FO, 0)

    except ConnectionError as e:
        print_warning(f"Could not connect to Flight Simulator: {e}")
        print("Make sure MSFS is running and try again.")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
