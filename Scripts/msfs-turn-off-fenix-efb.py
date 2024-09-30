from time import sleep
import sys
import os

from simconnect_mobiflight.mobiflight_variable_requests import MobiFlightVariableRequests
from simconnect_mobiflight.simconnect_mobiflight import SimConnectMobiFlight

import logging

logging.basicConfig(level=logging.DEBUG)

try:
    # Initialize the SimConnect connection
    sm = SimConnectMobiFlight()
    mf_requests = MobiFlightVariableRequests(sm)
    
    # For some reason it seems we need to 'prime' the lib or it doesn't work otherwise?
    altitude = mf_requests.get("(A:PLANE ALTITUDE,Feet)")
    #autopilot_active = mf_requests.get("(L:A32NX_AUTOPILOT_1_ACTIVE)")
    #print(f"Altitude: {altitude}, Autopilot Active: {autopilot_active}")

    # Set the LVAR
    mf_requests.set("0 (>L:S_EFB_VISIBLE_CAPT)")
    sleep(0.1)  # Add a small delay to ensure the command processes

    # Fetch the LVAR value
    efb_visible = mf_requests.get("(L:S_EFB_VISIBLE_CAPT)")
    print(f"EFB Visibility is now set to: {efb_visible}")

    mf_requests.set("0 (>L:S_EFB_CHARGING_CABLE_CAPT)")
    charging_cable = mf_requests.get("(L:S_EFB_CHARGING_CABLE_CAPT)")
    print(f"EFB Charging Cable is now set to: {charging_cable}")

    # Set the LVARs for the First Officer's EFB visibility and charging cable
    mf_requests.set("0 (>L:S_EFB_VISIBLE_FO)")
    mf_requests.set("0 (>L:S_EFB_CHARGING_CABLE_FO)")
    sleep(0.1)  # Add a small delay to ensure the command processes

    # Fetch the LVAR values to confirm
    efb_visible_fo = mf_requests.get("(L:S_EFB_VISIBLE_FO)")
    charging_cable_fo = mf_requests.get("(L:S_EFB_CHARGING_CABLE_FO)")
    print(f"FO EFB Visibility: {efb_visible_fo}, FO Charging Cable: {charging_cable_fo}")
    
except ConnectionError as e:
    logging.error("Could not connect to Flight Simulator: %s", e)
    logging.info("Make sure MSFS is running and try again.")
except Exception as e:
    logging.error("An unexpected error occurred: %s", e)


