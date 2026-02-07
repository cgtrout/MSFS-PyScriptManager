"""
Live diagnostic: continuously reads CAMERA STATE and prints sim state verdict.

Run this while in the MSFS menu, then load into a flight, and watch the
camera state change.  Uses raw SimConnect (no MobiFlight required).
"""

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from Lib.color_print import print_info, print_color
from Lib.mobiflight_connection import MobiflightConnection
from Lib.sim_state import SimStateDetector


def main():
    print_color("[bold]Sim State Detector — Live Diagnostics[/bold]", bold=True)
    print()

    mobiflight = MobiflightConnection(client_name="sim_state_diag")
    mobiflight.connect()

    detector = SimStateDetector(mobiflight)
    cycle = 0

    print_info("Connected. Polling every 1s. Press Ctrl+C to stop.\n")

    try:
        while True:
            cycle += 1
            cam = detector.get_camera_state()
            in_flight = detector.is_in_flight()

            cam_str = f"{int(cam)}" if cam is not None else "None"
            color = "green" if in_flight else "red"
            label = "IN FLIGHT" if in_flight else "IN MENU / LOADING"

            print(
                f"  Cycle {cycle:>4}  |  "
                f"camera_state: {cam_str:<4}  |  ",
                end="",
            )
            print_color(f"[{color}(]{label}[)]")

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
