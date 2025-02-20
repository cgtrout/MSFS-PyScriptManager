"""
virtual_pos_printer: Runs as a virtual printer and shows print-out as popup.  Will also
configure network windows printer if needed
"""
import atexit
import socket
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import font, messagebox
import queue
import json
import http.server
import socketserver
import os
import re
import keyboard

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
import pygame

try:
    # Import all color print functions
    from Lib.color_print import *

except ImportError:
    print("Failed to import 'Lib.color_print'. Please ensure /Lib/color_print.py is present")
    sys.exit(1)

# Constants
DEFAULT_FONT = ("Consolas", 12)
PRINTER_SERVER_ADDRESS = '127.0.0.1'
PRINTER_SERVER_PORT = 9102
HTTP_SERVER_PORT = 40001
SETTINGS_DIR = os.path.join(os.path.dirname(__file__), '../Settings')
SETTINGS_FILE = os.path.join(SETTINGS_DIR, 'settings.json')

class PlaySound:
    """Handles sound playback for the virtual printer"""

    def __init__(self, sound_path, volume=0.5):
        self.sound_path = os.path.abspath(os.path.join(SETTINGS_DIR, sound_path))
        self.volume = max(0.0, min(1.0, volume))  # Ensure volume is between 0.0 and 1.0

        pygame.mixer.init()
        atexit.register(pygame.mixer.quit)

        if not os.path.isfile(self.sound_path):
            print(f"WARNING: Sound file '{self.sound_path}' not found. Sound will be disabled.")
            self.sound_path = None  # Disable sound if file is missing

    def play(self):
        """Plays the print sound"""
        if self.sound_path:
            try:
                pygame.mixer.music.load(self.sound_path)
                pygame.mixer.music.set_volume(self.volume)
                pygame.mixer.music.play(start=1.3, fade_ms=400)
            except pygame.error as e:
                print(f"ERROR: Unable to play sound - {e}")

class PrinterServer:
    """Handles the virtual printer TCP server"""

    def __init__(self, printer_queue, http_queue):
        self.printer_queue = printer_queue
        self.http_queue = http_queue
        self.socket = self.initialize_server()
        self.http_request_pattern = re.compile(
            r'^\s*(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH|CONNECT|TRACE)\s+'
            r'.*\s+HTTP/\d',
            re.IGNORECASE
        )

    def initialize_server(self):
        """Initialize the TCP printer server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((PRINTER_SERVER_ADDRESS, PRINTER_SERVER_PORT))
        server_socket.listen(5)
        print(f"Printer server listening on {PRINTER_SERVER_ADDRESS}:{PRINTER_SERVER_PORT}")
        return server_socket

    def run(self):
        """Server loop to receive and queue print jobs"""
        while True:
            connection, client_address = self.socket.accept()
            print_info(f'Printer connection from {client_address}')

            try:
                data = b""
                while True:
                    part = connection.recv(1024)
                    if not part:
                        break
                    data += part

                decoded_data = data.decode('utf-8')

                # Ignore any request that starts with an HTTP method. This is to deal with random
                # software such as Logitech GHub that for some reason probe this port
                first_line = decoded_data.partition("\n")[0].strip()
                if self.http_request_pattern.match(first_line):
                    print_info("Not a print request: skipping...")
                    continue

                print_debug("decoded_data------------")
                print(decoded_data)
                print_debug("decoded_data------------  END \n\n")

                cleaned_data = re.sub(r'[\r\n]+', '\n', decoded_data)
                cleaned_data = cleaned_data.strip()
                if not cleaned_data:
                    print_debug("Cleaned print job is empty after removing Form Feed and whitespace, ignoring.")
                    continue

                acars_message = self.extract_acars_message(cleaned_data)

                # Add to both queues
                self.printer_queue.put(acars_message)
                self.http_queue.put(acars_message)

            except Exception as e:
                print_error(f"PrinterServer error: {e}")
            finally:
                connection.close()

    @staticmethod
    def extract_acars_message(data):
        """Extract ACARS message from text"""
        match = re.search(r'ACARS BEGIN\s*(.*?)\s*ACARS END', data, re.DOTALL)
        return match.group(1).strip() if match else data

    def start(self):
        """Start Printer server thread"""
        threading.Thread(target=self.run, daemon=True).start()

class HttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP Server to serve the next message from the queue"""

    def __init__(self, message_queue, sound_player, *args, **kwargs):
        self.message_queue = message_queue
        self.sound_player = sound_player  # Store PlaySound instance
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/latest":
            try:
                response = self.message_queue.get_nowait()  # Get the next message in the queue
                if self.sound_player:
                    self.sound_player.play()

                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
                self.wfile.write(response.encode("utf-8"))

            except queue.Empty:
                # No content available
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()
        else:
            # Resource not found
            self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

class HttpServer:
    """Handles HTTP API to serve latest print messages"""
    def __init__(self, message_queue, sound_player):
        self.message_queue = message_queue
        self.sound_player = sound_player
        self.httpd = self.initialize_server()

    def initialize_server(self):
        """Initialize HTTP server"""
        def handler(*args, **kwargs):
            return HttpRequestHandler(self.message_queue, self.sound_player, *args, **kwargs)

        httpd = socketserver.TCPServer(("", HTTP_SERVER_PORT), handler)
        print(f"HTTP server running on port {HTTP_SERVER_PORT}")
        return httpd

    def start(self):
        """Start HTTP server in a thread"""
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

class VirtualPosPrinter:
    """Manages UI, sound, and popups"""

    def __init__(self):
        # Initialize Settings
        self.settings = self.load_settings()
        self.spawn_position = tuple(self.settings.get("spawn_position", (100, 100)))
        self.play_sound_path = os.path.abspath(os.path.join(SETTINGS_DIR, self.settings.get("play_sound", "")))
        self.play_volume = self.settings.get("play_volume", 0.25)

        # Ensure port is available
        self.ensure_port_available(PRINTER_SERVER_PORT)

        # Setup printer
        self.setup_printer()

        # Initialize queues used for main printer queue and printer server queue
        self.printer_queue = queue.Queue()
        self.http_queue = queue.Queue()

        # Manage active window positions - used for cascading
        self.active_windows = []

        # Initialize Tkinter
        self.root = tk.Tk()
        self.root.withdraw()
        self.default_font = font.Font(family=DEFAULT_FONT[0], size=DEFAULT_FONT[1])

        # Initialize sound player
        self.sound_player = PlaySound(self.settings["play_sound"], self.settings["play_volume"])

        # Start Servers
        self.server = PrinterServer(self.printer_queue, self.http_queue)
        self.server.start()
        self.http_server = HttpServer(self.http_queue, self.sound_player)
        self.http_server.start()

        # Add global keyboard shortcut
        keyboard.add_hotkey('ctrl+shift+alt+p', self.capture_mouse_position)

        self.process_print_queue()
        self.print_instructions()

    def load_settings(self):
        """Load settings from file or create a new one if missing"""
        os.makedirs(SETTINGS_DIR, exist_ok=True)

        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding="utf-8") as f:
                return json.load(f)

        # Default settings
        default_settings = {
            "spawn_position": (100, 100),
            "enable_popups": True,
            "play_sound": "../Data/receipt-printer-01-43872.mp3",
            "play_volume": 0.25
        }

        # Write default settings to file
        with open(SETTINGS_FILE, 'w', encoding="utf-8") as f:
            json.dump(default_settings, f, indent=4)

        return default_settings

    def capture_mouse_position(self):
        """Set spawn position based on current mouse position"""
        x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
        self.settings["spawn_position"] = (x, y)
        self.spawn_position = (x, y)

        # Reset active windows to ensure cascading starts from new position
        self.active_windows.clear()

        with open(SETTINGS_FILE, 'w', encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4)
        messagebox.showinfo("Position Set", f"Spawn position set to: {x}, {y}")
        print_info(f"New spawn position set to {x}, {y} ")

    def process_print_queue(self):
        """Process messages from print queue"""
        try:
            message = self.printer_queue.get_nowait()
            if self.settings.get("enable_popups", True):
                self.create_window(message)
                self.sound_player.play()
        except queue.Empty:
            pass
        self.root.after(100, self.process_print_queue)

    def create_window(self, data):
        """Create a dynamically positioned pop-up window for print messages."""
        window = tk.Toplevel()
        window.overrideredirect(1)
        window.configure(bg='white', highlightbackground='gray', highlightthickness=2, bd=2)

        # Use a font consistent with the default settings
        window_font = font.Font(family=self.default_font.cget("family"),
                                size=self.default_font.cget("size"))

        label = tk.Label(window, text=data, font=window_font,
                         bg='white', padx=10, pady=10, anchor='w', justify='left')
        label.pack()

        # Cascade windows if needed
        if self.active_windows:
            last_x, last_y = self.active_windows[-1]
            x_offset = min((last_x + 10 - self.spawn_position[0]), 100)
            y_offset = min((last_y + 10 - self.spawn_position[1]), 100)
            new_x, new_y = self.spawn_position[0] + x_offset, self.spawn_position[1] + y_offset
        else:
            new_x, new_y = self.spawn_position

        window.geometry(f"+{new_x}+{new_y}")
        self.active_windows.append((new_x, new_y))

        def on_close():
            """Close the popup window on right-click."""
            window.focus_force()
            if (new_x, new_y) in self.active_windows:
                self.active_windows.remove((new_x, new_y))
            window.destroy()

        window.bind("<ButtonRelease-3>", lambda event: on_close())

        # Enable window dragging
        mouse_x, mouse_y = 0, 0

        def on_mouse_press(event):
            nonlocal mouse_x, mouse_y
            mouse_x, mouse_y = event.x, event.y

        def on_mouse_drag(event):
            x = window.winfo_x() - mouse_x + event.x
            y = window.winfo_y() - mouse_y + event.y
            window.geometry(f"+{x}+{y}")

        window.bind("<Button-1>", on_mouse_press)
        window.bind("<B1-Motion>", on_mouse_drag)

        # Keep the popup always on top
        window.attributes('-topmost', True)
        window.lift()
        window.focus_force()

        # Allow font resizing via Ctrl + Mouse Wheel
        def scale_font(event):
            if event.state & 0x0004:  # Detect if Control key is pressed
                current_size = window_font.cget("size")
                new_size = current_size + 2 if event.delta > 0 else max(6, current_size - 2)
                window_font.config(size=new_size)

        window.bind("<Enter>", lambda event: window.bind("<MouseWheel>", scale_font))
        window.bind("<Leave>", lambda event: window.unbind("<MouseWheel>"))

    def setup_printer(self):
        """Setup printer in Windows"""
        printer_name = "VirtualTextPrinter"
        driver_name = "Generic / Text Only"

        print_color("---CHECKING PRINTER STATUS--------------------------------------", color="yellow", bold=False)

        powershell_script = f"""
        try {{
            $portName = "{PRINTER_SERVER_ADDRESS}_{PRINTER_SERVER_PORT}"
            $printerName = "{printer_name}"
            $driverName = "{driver_name}"

            # Check if the 'Generic / Text Only' printer driver is installed
            Write-Host "Checking printer driver..."
            if (!(Get-PrinterDriver -Name $driverName -ErrorAction SilentlyContinue)) {{
                Write-Host "Printer driver is missing. Installing driver..."
                Add-PrinterDriver -Name $driverName
                Write-Host "Printer driver installed successfully."
            }} else {{
                Write-Host "Printer driver is already installed."
            }}

            # Check if the port exists; if not, create it
            Write-Host "Checking printer port..."
            if (!(Get-PrinterPort -Name $portName -ErrorAction SilentlyContinue)) {{
                Write-Host "Printer port is missing. Creating port..."
                Add-PrinterPort -Name $portName -PrinterHostAddress "{PRINTER_SERVER_ADDRESS}" -PortNumber {PRINTER_SERVER_PORT}
                Write-Host "Printer port created successfully."
            }} else {{
                Write-Host "Printer port is already configured."
            }}

            # Check if the printer exists; if not, create it
            Write-Host "Checking printer..."
            if (!(Get-Printer -Name $printerName -ErrorAction SilentlyContinue)) {{
                Write-Host "Printer is missing. Installing printer..."
                Add-Printer -Name $printerName -DriverName $driverName -PortName $portName
                Write-Host "Printer installed successfully."
            }} else {{
                Write-Host "Printer is already installed."
            }}

            Write-Host " "

            # Final sanity check: verify that the printer is assigned to the correct port
            Write-Host "Performing final check to ensure correct port assignment..."
            $assignedPort = (Get-Printer -Name $printerName).PortName
            if ($assignedPort -eq $portName) {{
                Write-Host "Check passed: Printer is assigned to the correct port."
            }} else {{
                Write-Host "!!  Check FAILED: Printer is assigned to '$assignedPort' instead of '$portName'."
                exit 1  # Exit with a non-zero code if the port assignment is incorrect
            }}
        }} catch {{
            Write-Host "An error occurred during setup: $_"
            exit 1  # Exit with a non-zero code if an error occurs
        }}
        """

        try:
            # Start the PowerShell process and capture output line by line
            process = subprocess.Popen(
                ["powershell", "-ExecutionPolicy", "Bypass", "-Command", powershell_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            # Read output line by line as the script executes
            for line in process.stdout:
                print(line.strip())  # Print each line immediately

            process.wait()  # Wait for the process to complete
            if process.returncode != 0:
                print("An error occurred during setup. Please check the details above.")
        except Exception as e:
            print_error(f"setup_printer: An unexpected error occurred: {e}")

        print_color("----------------------------------------------------------------", color="yellow", bold=False)

    def print_instructions(self):
        """Print user instructions to screen"""
        print()
        print_color("=== Instructions ===", color="green")
        print_color("- Use [yellow(]Ctrl+Alt+Shift+P[)] to change the print location of pop-ups.")
        print_color("- In the Fenix A32x EFB, set the printer to [yellow(]'VirtualTextPrinter'[)] to enable printing.")
        print("- Right-click on a note to close it.")
        print("- To modify the settings for this script, click the 'Open Settings' button")
        print("- For more information, visit the project Github page for MSFS-PyScriptManager.")

    def run(self):
        """Start the Tkinter main loop"""
        self.root.mainloop()

    def ensure_port_available(self, port, host='127.0.0.1'):
        """Validate that port is open"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
            except OSError:
                print_error(f"\nERROR: Port {port} is already in use!")
                print("\nPossible causes:")
                print("- Another instance of this script is already running.")
                print("- Improper shutdown of a previous instance has left the port occupied.")
                print("\nTo resolve:")
                print("1. Close MSFS-PyScriptManager.")
                print("2. Check for running Python processes and terminate them:")
                print("   - Open Task Manager and close any running 'python.exe' instances.")
                sys.exit(1)

if __name__ == "__main__":
    app = VirtualPosPrinter()
    app.run()
