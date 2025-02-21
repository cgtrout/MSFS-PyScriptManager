import logging
import time

from Lib.MSFSPythonSimConnectMobiFlightExtension import SimConnectMobiFlight
from Lib.MSFSPythonSimConnectMobiFlightExtension import MobiFlightVariableRequests
from Lib.color_print import print_info, print_error

# Disable warnings - still shows errors
logging.getLogger("SimConnect.SimConnect").setLevel(logging.ERROR)

class MobiflightConnection:
    """Handles the connection and reconnection to Mobiflight and MSFS."""

    def __init__(self, client_name="mobiflight_manager", retry_delay=20):
        self.client_name = client_name
        self.retry_delay = retry_delay
        self.sm = None
        self.mf_requests = None

    def connect(self):
        """Attempt to establish a connection, retrying on failure."""
        while True:
            try:
                print_info("Attempting to connect to Flight Simulator...")
                self.sm = SimConnectMobiFlight()
                self.mf_requests = MobiFlightVariableRequests(self.sm, self.client_name)
                self.mf_requests.clear_sim_variables()
                print_info("Successfully connected to Flight Simulator.")
                return
            except ConnectionError as e:
                print_error(f"Could not connect to Flight Simulator: {e}. Retrying in {self.retry_delay} seconds...")
                time.sleep(self.retry_delay)

    def get_request_handler(self):
        """Returns the request handler if the connection is active, otherwise reconnects."""
        if self.mf_requests is None:
            self.connect()
        return self.mf_requests

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

    def set_and_verify_lvar(self, lvar, value, tolerance=0.01, max_retries=5, retry_delay=0.1):
        """
        Sets an LVAR to a specified value and verifies it within a tolerance. Retries if necessary.
        If tolerance is None, disables the verification step entirely.
        """
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
            if abs(current_value - value) <= tolerance:
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
