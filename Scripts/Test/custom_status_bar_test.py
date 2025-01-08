import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import time  # To simulate time passage

# Add the parent directory to the system path
parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

# Import the main script after updating the system path
import custom_status_bar

# Track the start time for dynamic updates
start_time_epoch = time.time()

# Define the current date's midnight UTC as the test's fixed start time
fixed_test_start_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

def generate_mock_simbrief_data():
    """
    Dynamically generate mock SimBrief data with a custom offset applied directly to the gate-out time.

    The custom_offset adjusts all times relative to fixed_test_start_time for testing purposes.
    """
    # Custom offset for testing (in seconds)
    custom_offset = -24*60*60

    # Use the simulated datetime (fixed_test_start_time) for consistency
    now_simulated = fixed_test_start_time

    # Calculate the gate-out time directly using the custom offset
    sched_out = now_simulated + timedelta(seconds=custom_offset)  # Gate-out time is offset from fixed_test_start_time

    # Define other times relative to gate-out
    flight_duration = timedelta(hours=2)  # Flight duration is always 2 hours
    time_before_generation = timedelta(minutes=5)  # Plan was generated 5 minutes before gate-out

    # Calculate remaining timestamps
    est_in = sched_out + flight_duration          # Estimated arrival time
    time_generated = sched_out - time_before_generation  # Plan generated time

    # Debugging: Print calculated times for validation
    print(f"[DEBUG] SimBrief Data Generation:")
    print(f"  Now Simulated: {now_simulated}")
    print(f"  Scheduled Gate Out: {sched_out} (Custom Offset: {custom_offset} seconds)")
    print(f"  Estimated Arrival (est_in): {est_in}")
    print(f"  Time Generated: {time_generated}")

    # Return the JSON structure with dynamic timestamps
    return {
        "times": {
            "sched_out": int(sched_out.timestamp()),  # Convert to epoch time
            "est_in": int(est_in.timestamp()),        # Convert to epoch time
        },
        "navlog": {
            "fix": [
                {"ident": "TOD", "time_total": int(flight_duration.total_seconds() / 2)},  # TOD is halfway through the flight
            ]
        },
        "params": {
            "time_generated": int(time_generated.timestamp())  # Convert to epoch time
        }
    }

# Mock SimBrief Fetch Function
def mock_get_latest_simbrief_ofp_json(username):
    """
    Mock SimBrief API response for fetching OFP JSON data.
    """
    print(f"Mock SimBrief called for username: {username}")
    return generate_mock_simbrief_data()

# Mock for `get_sim_time`
def mock_get_sim_time(offset_seconds=0):
    """
    Mock for get_sim_time to return a dynamically updating time string (HH:MM:SS).
    """
    elapsed_time = time.time() - start_time_epoch
    dynamic_sim_time = fixed_test_start_time + timedelta(seconds=offset_seconds + elapsed_time)
    return dynamic_sim_time.strftime("%H:%M:%S")

# Mock for `get_simulator_datetime`
def mock_get_simulator_datetime(offset_seconds=0):
    """
    Mock for get_simulator_datetime to return a dynamically updating datetime object.
    """
    elapsed_time = time.time() - start_time_epoch
    return fixed_test_start_time + timedelta(seconds=offset_seconds + elapsed_time)

# Helper function to mock datetime around the fixed start time
def mock_datetime_now(offset_seconds=0):
    """
    Mock datetime.now() to return dynamically updating UTC time with an applied offset.
    """
    elapsed_time = time.time() - start_time_epoch
    return fixed_test_start_time + timedelta(seconds=offset_seconds + elapsed_time)

# Create a mock `datetime` class
class MockDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        """
        Mock datetime.now() to return dynamically updating UTC time with an applied offset.
        """
        return mock_datetime_now(real_world_time_offset)

    @classmethod
    def utcnow(cls):
        """
        Mock datetime.utcnow() to return dynamically updating UTC time.
        """
        return mock_datetime_now(real_world_time_offset).replace(tzinfo=None)

# Main test function
def run_with_mocked_times():
    """
    Run the `custom_status_bar.py` script with mocked datetime, SimBrief, and SimConnect functions.
    """
    # Define offsets for simulator time and real-world time (in seconds)
    global real_world_time_offset, simulator_time_offset
    simulator_time_offset = -10  # Sim time offset is 10 seconds behind midnight UTC
    real_world_time_offset = -30  # Real world time offset is 30 seconds behind midnight UTC

    # Patch `datetime`, SimBrief, and SimConnect functions
    with patch("custom_status_bar.datetime", MockDateTime):
        with patch("custom_status_bar.get_sim_time", lambda: mock_get_sim_time(simulator_time_offset)):
            with patch("custom_status_bar.get_simulator_datetime", lambda: mock_get_simulator_datetime(simulator_time_offset)):
                with patch("custom_status_bar.SimBriefFunctions.get_latest_simbrief_ofp_json", mock_get_latest_simbrief_ofp_json):
                    # Run the main function from the main script
                    try:
                        custom_status_bar.main()  # Start the main loop of the status bar
                    except KeyboardInterrupt:
                        print("Test script interrupted. Exiting...")

if __name__ == "__main__":
    run_with_mocked_times()
