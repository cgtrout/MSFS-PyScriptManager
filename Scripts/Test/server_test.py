import queue
import threading
import http.server
import socketserver
import time

# Create a FIFO queue to store messages
message_queue = queue.Queue()

# Custom HTTP request handler
class HttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/latest":
            try:
                # Get the next message from the queue (non-blocking)
                message = message_queue.get_nowait()
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write(message.encode("utf-8"))
            except queue.Empty:
                # If no messages are available, return an empty response
                self.send_response(204)  # No content
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

# Function to simulate new print jobs being received
def simulate_print_jobs():
    count = 1
    while True:
        time.sleep(5)  # Simulate a new print job every 5 seconds
        new_message = f"Print job #{count}: ACARS message or other data."
        print(f"New message added: {new_message}")
        # Put the new message in the queue
        message_queue.put(new_message)
        count += 1

# Start the HTTP server
def start_server():
    with socketserver.TCPServer(("localhost", 40001), HttpRequestHandler) as httpd:
        print("Server running on port 40001...")
        httpd.serve_forever()

# Start the server in one thread and simulate print jobs in another thread
if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()

    simulate_print_jobs()