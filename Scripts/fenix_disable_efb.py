# fenix_disable_efb.py: Shows an example of how you can disable the Fenix A32x EFBs using a script

from time import sleep
from simconnect_mobiflight.mobiflight_variable_requests import MobiFlightVariableRequests
from simconnect_mobiflight.simconnect_mobiflight import SimConnectMobiFlight

# Constants for LVARs
EFB_VISIBLE_CAPT = "(L:S_EFB_VISIBLE_CAPT)"
EFB_CHARGING_CAPT = "(L:S_EFB_CHARGING_CABLE_CAPT)"
EFB_VISIBLE_FO = "(L:S_EFB_VISIBLE_FO)"
EFB_CHARGING_FO = "(L:S_EFB_CHARGING_CABLE_FO)"

def set_and_get_lvar(mf_requests, lvar, value):
    """Sets an LVAR to a specified value and retrieves the updated value."""
    mf_requests.set(f"{value} (> {lvar})")
    result = mf_requests.get(f"{lvar}")
    print(f"{lvar} set to {value}. Current value: {result}")
    return result

def main():
    try:
        # Initialize the SimConnect connection
        sm = SimConnectMobiFlight()
        mf_requests = MobiFlightVariableRequests(sm)

        # Prime the library - possibly necessary to ensure the connection works properly?
        # TODO determine what causes this
        altitude = mf_requests.get("(A:PLANE ALTITUDE,Feet)")
        print(f"Primed with altitude: {altitude}")

        # Set values for Captain's EFB visibility and charging cable
        # Setting to 0 hides these in this case
        set_and_get_lvar(mf_requests, EFB_VISIBLE_CAPT, 0)
        set_and_get_lvar(mf_requests, EFB_CHARGING_CAPT, 0)

        # Set values for First Officer's EFB visibility and charging cable
        # Setting to 0 hides
        set_and_get_lvar(mf_requests, EFB_VISIBLE_FO, 0)
        set_and_get_lvar(mf_requests, EFB_CHARGING_FO, 0)

    except ConnectionError as e:
        print(f"Could not connect to Flight Simulator: {e}")
        print("Make sure MSFS is running and try again.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
