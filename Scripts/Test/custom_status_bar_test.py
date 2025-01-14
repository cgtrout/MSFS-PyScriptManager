import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import time

# Add the parent directory to the system path for importing the main script
parent_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(parent_dir))

# Import the main script
import custom_status_bar

# Track the start time for dynamic updates
start_time_epoch = time.time()

# Define the current date's midnight UTC as the test's fixed start time
fixed_test_start_time = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

# Shared state to track the simulated time
_sim_rate_state = {"last_update": time.time(), "current_rate": 1.0}

def generate_mock_simbrief_data():
    """
    Dynamically generate mock SimBrief data with a custom offset applied directly to the gate-out time.
    """
    custom_offset = -24 * 60 * 60  # Custom offset: 24 hours ago
    now_simulated = fixed_test_start_time

    # Calculate the times
    sched_out = now_simulated + timedelta(seconds=custom_offset)
    flight_duration = timedelta(hours=2)  # Fixed flight duration
    time_before_generation = timedelta(minutes=5)

    est_in = sched_out + flight_duration
    time_generated = sched_out - time_before_generation

    # Debugging: Print calculated times
    print(f"[DEBUG] SimBrief Data:")
    print(f"  Now Simulated: {now_simulated}")
    print(f"  Scheduled Gate Out: {sched_out}")
    print(f"  Estimated Arrival: {est_in}")
    print(f"  Time Generated: {time_generated}")

    return {
        "times": {
            "sched_out": int(sched_out.timestamp()),
            "est_in": int(est_in.timestamp()),
        },
        "navlog": {
            "fix": [
                {"ident": "TOD", "time_total": int(flight_duration.total_seconds() / 2)},
            ]
        },
        "params": {
            "time_generated": int(time_generated.timestamp())
        }
    }

def mock_get_latest_simbrief_ofp_json(username):
    """
    Mock the SimBrief API to return dynamic OFP data.
    """
    print(f"Mock SimBrief called for username: {username}")
    return generate_mock_simbrief_data()

def mock_get_sim_time(offset_seconds=0):
    """
    Mock the simulator time to return dynamic time (HH:MM:SS).
    """
    elapsed_time = time.time() - start_time_epoch
    dynamic_sim_time = fixed_test_start_time + timedelta(seconds=offset_seconds + elapsed_time)
    return dynamic_sim_time.strftime("%H:%M:%S")

def mock_get_simulator_datetime(offset_seconds=0):
    """
    Mock the simulator datetime to return dynamic datetime objects.
    """
    elapsed_time = time.time() - start_time_epoch
    return fixed_test_start_time + timedelta(seconds=offset_seconds + elapsed_time)

def mock_get_sim_rate():
    """
    Mock the get_sim_rate function to alternate between "1.0" and "2.0" every 5 seconds.
    """
    now = time.time()
    if now - _sim_rate_state["last_update"] >= 5:
        _sim_rate_state["current_rate"] = 2.0 if _sim_rate_state["current_rate"] == 1.0 else 1.0
        _sim_rate_state["last_update"] = now
    return f"{_sim_rate_state['current_rate']:.1f}"  # Return as a formatted string

def mock_is_sim_rate_accelerated():
    """
    Mock the accelerated sim rate check based on the current mock sim rate.
    """
    return mock_get_sim_rate() != "1.0"  # Compare with the string "1.0"

class MockDateTime(datetime):
    """
    Mock datetime class for overriding `now()` and `utcnow()`.
    """
    @classmethod
    def now(cls, tz=None):
        return mock_datetime_now(real_world_time_offset)

    @classmethod
    def utcnow(cls):
        return mock_datetime_now(real_world_time_offset).replace(tzinfo=None)

def mock_datetime_now(offset_seconds=0):
    """
    Mock `datetime.now()` to return dynamically updating UTC time.
    """
    elapsed_time = time.time() - start_time_epoch
    return fixed_test_start_time + timedelta(seconds=offset_seconds + elapsed_time)

def run_with_mocked_times():
    """
    Run the `custom_status_bar.py` script with all required mocks.
    """
    # Define offsets
    global real_world_time_offset, simulator_time_offset
    simulator_time_offset = -10
    real_world_time_offset = -30

    # Apply patches in a single `with` block for clarity
    with patch("custom_status_bar.datetime", MockDateTime), \
         patch("custom_status_bar.get_sim_time", lambda: mock_get_sim_time(simulator_time_offset)), \
         patch("custom_status_bar.get_simulator_datetime", lambda: mock_get_simulator_datetime(simulator_time_offset)), \
         patch("custom_status_bar.SimBriefFunctions.get_latest_simbrief_ofp_json", mock_get_latest_simbrief_ofp_json), \
         patch("custom_status_bar.get_sim_rate", mock_get_sim_rate), \
         patch("custom_status_bar.is_sim_rate_accelerated", mock_is_sim_rate_accelerated):

        try:
            custom_status_bar.main()  # Run the main script
        except KeyboardInterrupt:
            print("Test script interrupted. Exiting...")

if __name__ == "__main__":
    run_with_mocked_times()
