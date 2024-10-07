import queue
import threading
import http.server
import socketserver
import time

SERVER_PORT = 40001

# Create a FIFO queue to store messages
http_message_queue = queue.Queue()

# Custom HTTP request handler
class HttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/latest":
            try:
                response = http_message_queue.get_nowait()  # Get the next message in the queue
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()
                self.wfile.write(response.encode("utf-8"))
            except queue.Empty:
                self.send_response(204)  # No content available
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
        http_message_queue.put(new_message)
        count += 1

# Start the HTTP server
def start_server():
    with socketserver.TCPServer(("localhost", SERVER_PORT), HttpRequestHandler) as httpd:
        print(f"Server running on port {SERVER_PORT}...")
        httpd.serve_forever()

# Start the server in one thread and simulate print jobs in another thread
if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server)
    server_thread.daemon = True
    server_thread.start()

    simulate_print_jobs()