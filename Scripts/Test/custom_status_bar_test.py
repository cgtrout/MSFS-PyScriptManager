import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from unittest.mock import patch
import os
import sys
import requests
import json

# Add the parent directory to sys.path to import custom_status_bar
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(SCRIPT_DIR)

from custom_status_bar import main

# Global state to control server behavior
server_should_hang = False

# Fake SimBrief Server
class SimBriefHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        """Handle GET requests."""
        global server_should_hang

        if "/api/xml.fetcher.php" in self.path:
            if server_should_hang:
                # Simulate a hanging server
                print("DEBUG: Simulating a hanging server...")
                while True:
                    time.sleep(1)  # Infinite loop to hang the request
            else:
                # Normal response
                self.send_response(200)
                self.end_headers()
                response = {
                    "times": {"est_in": "1734589974"},
                    "params": {"time_generated": "1734589974"},
                }
                self.wfile.write(json.dumps(response).encode())
                print("DEBUG: SimBrief responded normally.")
        else:
            self.send_response(404)
            self.end_headers()

def start_fake_server():
    """Start the fake SimBrief server."""
    server = HTTPServer(("localhost", 5000), SimBriefHandler)

    def run_server():
        """Run the server and handle hanging transition."""
        global server_should_hang
        print("DEBUG: Fake SimBrief server started on http://127.0.0.1:5000")
        # Run the server
        server.serve_forever()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Set the server to hang after 10 seconds
    def delay_hang():
        global server_should_hang
        time.sleep(10)
        print("DEBUG: Switching server to hanging mode.")
        server_should_hang = True

    delay_thread = threading.Thread(target=delay_hang, daemon=True)
    delay_thread.start()

    return server

def test_full_script_with_fake_server():
    """Test the full script execution with the fake server."""
    print("\nRunning full script with fake SimBrief server")

    # Mock the SimBrief API URL to redirect to the fake server
    simbrief_url = "http://127.0.0.1:5000/api/xml.fetcher.php?username=test"

    def mock_get_latest_simbrief_ofp_json(username):
        """Mock function to fetch SimBrief data from the fake server."""
        response = requests.get(simbrief_url)  # No timeout specified to match original behavior
        response.raise_for_status()
        return response.json()

    with patch("custom_status_bar.get_latest_simbrief_ofp_json", mock_get_latest_simbrief_ofp_json):
        try:
            main()  # Run the full script
        except KeyboardInterrupt:
            print("DEBUG: Test interrupted manually.")
        except Exception as e:
            print(f"ERROR: Unexpected exception during script execution: {e}")

    print("DEBUG: Completed full script test with fake server")

# Main test script
if __name__ == "__main__":
    # Start the fake server
    fake_server = start_fake_server()
    time.sleep(2)  # Allow the server to start

    try:
        # Run the full script test
        test_full_script_with_fake_server()
    finally:
        # Stop the fake server
        fake_server.shutdown()
        print("DEBUG: Fake SimBrief server shut down")
