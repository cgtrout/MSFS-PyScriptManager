"""
sim_state.py — detect whether MSFS is in an active flight or sitting in menus.

Uses CAMERA STATE read directly via SimConnect DLL (no MobiFlight required).
Works with connection helpers or raw SimConnect instances.

Usage:
    from Lib.sim_state import SimStateDetector

    # Works with connection helpers:
    conn = MobiflightConnection(client_name="my_script")
    conn.connect()
    detector = SimStateDetector(conn)

    # Or with raw SimConnect:
    sm = SimConnect()
    detector = SimStateDetector(sm)

    detector.wait_for_flight()   # blocks until in-flight
    detector.is_in_flight()      # instant check
"""

from __future__ import annotations

import time
from typing import Optional

from SimConnect.RequestList import Request

from Lib.color_print import print_info, print_error


class SimStateDetector:
    """Detects whether MSFS is in an active flight via CAMERA STATE.

    Reads CAMERA STATE directly through the SimConnect DLL, bypassing
    both MobiFlight and the AircraftRequests predefined variable list.
    Works with connection helpers or raw SimConnect instances.
    """

    # Camera states confirmed in-flight (MSFS 2024):
    #   2 = cockpit, 3 = external, 4 = drone
    FLIGHT_CAMERA_STATES = {2, 3, 4}

    def __init__(self, connection):
        """
        Args:
            connection: Either:
                        - A connection helper with a .sm (SimConnect) attribute
                          (MobiflightConnectionHelper, SimConnectConnectionHelper)
                        - A raw SimConnect instance directly
        """
        # Accept either a wrapper with .sm or a raw SimConnect instance
        if hasattr(connection, 'sm'):
            self._sm = connection.sm
        else:
            # Assume it's a raw SimConnect instance
            self._sm = connection
        self._camera_request = Request(
            (b'CAMERA STATE', b'Enum'), self._sm, _time=0
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_camera_state(self) -> Optional[float]:
        """Read the current CAMERA STATE value. Returns None on error."""
        try:
            value = self._camera_request.value
            if value is not None:
                return float(value)
            return None
        except Exception:
            return None

    def is_in_flight(self) -> bool:
        """Returns True if CAMERA STATE indicates an active flight."""
        cam = self.get_camera_state()
        return cam is not None and cam in self.FLIGHT_CAMERA_STATES

    def wait_for_flight(
        self,
        check_interval: float = 0.5,
        timeout: Optional[float] = None,
    ) -> bool:
        """
        Block until in-flight state is detected.

        Returns True when in-flight, False if timeout expired.
        """
        print_info("Waiting for active flight session...")
        start = time.monotonic()

        while True:
            if timeout is not None and (time.monotonic() - start) >= timeout:
                print_error("Timed out waiting for active flight session.")
                return False

            if self.is_in_flight():
                print_info("Active flight session detected.")
                return True

            time.sleep(check_interval)
