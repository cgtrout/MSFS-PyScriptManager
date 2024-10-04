import http.server
import socketserver

# Data to serve, test message
acars_data = "This is the latest ACARS message."

# request handler
class MyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/latest":
            # Respond with plain text
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(acars_data.encode("utf-8"))
        else:
            # Handle other paths with a 404 error
            self.send_response(404)
            self.end_headers()

# Starting the server
PORT = 8080
with socketserver.TCPServer(("", PORT), MyHandler) as httpd:
    print(f"Serving on port {PORT}")
    httpd.serve_forever()
