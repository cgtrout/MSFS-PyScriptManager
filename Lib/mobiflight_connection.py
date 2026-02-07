import logging
import time
from typing import Optional

from Lib.MSFSPythonSimConnectMobiFlightExtension import SimConnectMobiFlight
from Lib.MSFSPythonSimConnectMobiFlightExtension import MobiFlightVariableRequests
from Lib.color_print import print_info, print_error
from Lib.connection_helpers import BaseConnectionHelper
from Lib.sim_process import wait_for_sim_running

# Disable warnings - still shows errors
logging.getLogger("SimConnect.SimConnect").setLevel(logging.ERROR)

class MobiflightConnectionHelper(BaseConnectionHelper):
    """Handles the connection and reconnection to Mobiflight and MSFS."""

    def __init__(self, client_name="mobiflight_manager", retry_delay=20):
        self.client_name = client_name
        self.retry_delay = retry_delay
        self.sm: Optional[SimConnectMobiFlight] = None
        self.mf_requests: Optional[MobiFlightVariableRequests] = None

    def connect(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """Attempt to establish a connection. If blocking, retry until connected or timeout."""
        if not blocking:
            return self._try_connect_once()

        start = time.monotonic()
        while True:
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return False

            if not wait_for_sim_running(timeout=self.retry_delay, interval=self.retry_delay):
                print_info(
                    f"Flight Simulator not detected yet. Retrying in {self.retry_delay} seconds..."
                )
                continue

            if self._try_connect_once():
                return True

            print_error(
                f"Could not connect to Flight Simulator. Retrying in {self.retry_delay} seconds..."
            )
            time.sleep(self.retry_delay)

    def _try_connect_once(self) -> bool:
        try:
            print_info("Attempting to connect to Flight Simulator...")
            self.sm = SimConnectMobiFlight()
            self.mf_requests = MobiFlightVariableRequests(self.sm, self.client_name)
            self.mf_requests.clear_sim_variables()

            # Prime the library - possibly necessary to ensure the connection works properly
            altitude = self.mf_requests.get("(A:PLANE ALTITUDE,Feet)")
            print(f"Primed with altitude: {altitude}")
            print_info("Successfully connected to Flight Simulator.")
            return True
        except ConnectionError as e:
            print_error(f"Could not connect to Flight Simulator: {e}")
            self.sm = None
            self.mf_requests = None
            return False

    def disconnect(self) -> None:
        if self.sm is not None:
            try:
                if hasattr(self.sm, "close"):
                    self.sm.close()
            except Exception as e:  # pylint: disable=broad-except
                print_error(f"Mobiflight close failed: {e}")
        self.sm = None
        self.mf_requests = None

    def is_connected(self) -> bool:
        return self.sm is not None and self.mf_requests is not None

    def get_request_handler(self):
        """Returns the request handler if the connection is active, otherwise reconnects."""
        if self.mf_requests is None:
            self.connect()
        return self.mf_requests

    def get_requests(self):
        if self.mf_requests is None:
            raise RuntimeError("Mobiflight not connected")
        return self.mf_requests

    def get(self, key):
        return self.get_requests().get(key)

    def wait_for_lvar(self, lvar, check_interval=0.5):
        """Waits for a specified LVAR to reach a non zero state"""
        print_info(f"Waiting for LVAR '{lvar}'")
        while True:
            try:
                value = self.mf_requests.get(f"({lvar})")
                if int(value) > 0:
                    print_info(f"LVAR '{lvar}' set")
                    return
            except Exception as e:
                print_error(f"Error reading LVAR '{lvar}': {e}")
            time.sleep(check_interval)

    def wait_for_lvar_change_to_value(
        self,
        lvar,
        target_value=1,
        check_interval=0.5,
        tolerance=0.01,
    ):
        """
        Wait until an LVAR changes from its initial value, then reaches target_value.
        Useful for avoiding stale/default startup values.
        """
        print_info(f"Waiting for LVAR '{lvar}' to change, then reach {target_value}")
        initial_value = None
        saw_change = False

        while True:
            try:
                value = float(self.mf_requests.get(f"({lvar})"))
                if initial_value is None:
                    initial_value = value
                    print_info(f"Initial '{lvar}' value: {initial_value}")

                if abs(value - initial_value) > tolerance:
                    saw_change = True

                if saw_change and abs(value - target_value) <= tolerance:
                    print_info(f"LVAR '{lvar}' changed and reached target {target_value}")
                    return
            except Exception as e:
                print_error(f"Error reading LVAR '{lvar}': {e}")
            time.sleep(check_interval)

    def set_and_verify_lvar(self, lvar, value, tolerance=0.01, max_retries=5, retry_delay=0.1):
        """
        Sets an LVAR to a specified value and verifies it within a tolerance. Retries if necessary.
        If tolerance is None, disables the verification step entirely.
        """
        current_value = None
        for attempt in range(1, max_retries + 1):
            # Attempt to set the LVAR
            req_str = f"{value} (> {lvar})"
            self.mf_requests.set(req_str)

            # Skip verification if tolerance is None
            if tolerance is None:
                return True

            time.sleep(retry_delay)  # Allow time for the simulator to apply the value

            # Check if the value was successfully applied within the tolerance
            current_value = self.mf_requests.get(f"({lvar})")
            if current_value is None:
                continue

            try:
                current_value = float(current_value)
                target_value = float(value)
            except (TypeError, ValueError):
                continue

            if abs(current_value - target_value) <= tolerance:
                return True

        # Enhanced error message with actual vs expected values
        print_error(
            f"[FAILURE] Could not set {lvar} to {value} (current value: {current_value}) "
            f"within tolerance {tolerance} after {max_retries} attempts."
        )
        return False

    def get(self, variable_string):
        """Calls mf_requests.get()"""
        return self.mf_requests.get(variable_string)

# Backwards compatibility alias
MobiflightConnection = MobiflightConnectionHelper
