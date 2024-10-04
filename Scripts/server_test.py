import http.server
import socketserver
from threading import Thread
import time

PORT = 40001

# Global variable to hold the latest message
acars_data = "This is the latest ACARS message."

# Function to update the message periodically (simulating new incoming data)
def update_message():
    global acars_data
    count = 1
    while True:
        # Update message every 10 seconds (for testing purposes)
        acars_data = f"ACARS message update #{count}"
        count += 1
        time.sleep(10)

# Custom request handler
class MyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/latest":
            # Respond with the latest message
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(acars_data.encode("utf-8"))
        else:
            # Handle other paths with a 404 error
            self.send_response(404)
            self.end_headers()

# Start the message update function in a separate thread
message_thread = Thread(target=update_message, daemon=True)
message_thread.start()

# Starting the server

with socketserver.TCPServer(("", PORT), MyHandler) as httpd:
    print(f"Serving on port {PORT}")
    httpd.serve_forever()
