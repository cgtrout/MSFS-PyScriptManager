# fbw_a380_checklist - allows control of FBW A380 ECAM checklist using shift+arrow keys

import logging
import keyboard  # For global key detection
import pygetwindow as gw  # For window detection
from Lib.mobiflight_connection import MobiflightConnection
from Lib.sim_state import SimStateDetector
from time import monotonic, sleep

# Disable warnings - still shows errors
logging.getLogger("SimConnect.SimConnect").setLevel(logging.ERROR)

# Constants for LVARs (Logical Variables)
LVAR_CHECKLIST_CONFIRM = "L:A32NX_BTN_CHECK_LH"  # Confirms checklist item
LVAR_CHECKLIST_DOWN = "L:A32NX_BTN_DOWN"        # Moves down the checklist
LVAR_CHECKLIST_UP = "L:A32NX_BTN_UP"            # Moves up the checklist
LVAR_CHECKLIST_TOGGLE = "L:A32NX_BTN_CL"        # Toggles the checklist

# Constants for keyboard key mappings with Shift combinations
KEY_CHECKLIST_CONFIRM = "shift+enter"
KEY_CHECKLIST_DOWN = "shift+down"
KEY_CHECKLIST_UP = "shift+up"
KEY_CHECKLIST_TOGGLE = "shift+delete"

MSFS_WINDOW_TITLE = "Microsoft Flight Simulator"  # Title of the MSFS window for focus checking
DEBOUNCE_SECONDS = 0.02  # Filter brief key-state flicker that can cause duplicate presses

def set_lvar(mf_requests, lvar, value):
    """Sets an LVAR to a specified value."""
    mf_requests.set(f"{value} (> {lvar})")
    print(f"{lvar} set to {value}")

def is_msfs_active():
    """Checks if the Microsoft Flight Simulator window is active."""
    try:
        window = gw.getWindowsWithTitle(MSFS_WINDOW_TITLE)
        return window and window[0].isActive
    except Exception as e:
        print(f"Error checking MSFS window: {e}")
        return False

def main():
    try:
        mobiflight = MobiflightConnection(client_name="fbw_a380_checklist")
        mobiflight.connect()
        mf_requests = mobiflight.get_request_handler()

        # Wait until the user is actually in a flight (not menus/loading)
        detector = SimStateDetector(mobiflight)
        detector.wait_for_flight()

        # Prime the library - possibly necessary to ensure the connection works properly
        altitude = mf_requests.get("(A:PLANE ALTITUDE,Feet)")
        print(f"Primed with altitude: {altitude}")

        print("Press Shift + Enter, Shift + Up, Shift + Down, or Shift + Delete when MSFS is the active window to trigger respective buttons.")

        key_bindings = [
            (KEY_CHECKLIST_CONFIRM, LVAR_CHECKLIST_CONFIRM),
            (KEY_CHECKLIST_UP, LVAR_CHECKLIST_UP),
            (KEY_CHECKLIST_DOWN, LVAR_CHECKLIST_DOWN),
            (KEY_CHECKLIST_TOGGLE, LVAR_CHECKLIST_TOGGLE),
        ]
        stable_states = {lvar: 0 for _, lvar in key_bindings}
        candidate_states = stable_states.copy()
        candidate_since = {lvar: monotonic() for _, lvar in key_bindings}

        # Continuously listen for key events in a loop
        while True:
            # Only proceed if MSFS is the active window
            if is_msfs_active():
                now = monotonic()
                for hotkey, lvar in key_bindings:
                    raw_state = 1 if keyboard.is_pressed(hotkey) else 0

                    if raw_state != candidate_states[lvar]:
                        candidate_states[lvar] = raw_state
                        candidate_since[lvar] = now
                        continue

                    if (
                        candidate_states[lvar] != stable_states[lvar]
                        and (now - candidate_since[lvar]) >= DEBOUNCE_SECONDS
                    ):
                        stable_states[lvar] = candidate_states[lvar]
                        set_lvar(mf_requests, lvar, stable_states[lvar])

            # Short sleep to avoid excessive CPU usage
            sleep(0.05)

    except ConnectionError as e:
        print(f"Could not connect to Flight Simulator: {e}")
        print("Make sure MSFS is running and try again.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
