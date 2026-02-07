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
DEFAULT_PRINTER_SERVER_PORT = 9102
HTTP_SERVER_PORT = 40001
DEFAULT_PRINTER_NAME = "VirtualTextPrinter"
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

    def __init__(self, printer_queue, http_queue, host, port):
        self.printer_queue = printer_queue
        self.http_queue = http_queue
        self.host = host
        self.port = port
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
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)
        print(f"Printer server listening on {self.host}:{self.port}")
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
        """Initialize HTTP server (loopback-only)"""
        def handler(*args, **kwargs):
            return HttpRequestHandler(self.message_queue, self.sound_player, *args, **kwargs)

        # Bind to loopback ONLY to avoid LAN exposure + firewall prompt
        httpd = socketserver.TCPServer((PRINTER_SERVER_ADDRESS, HTTP_SERVER_PORT), handler)

        print(f"HTTP server running on http://{PRINTER_SERVER_ADDRESS}:{HTTP_SERVER_PORT}")
        return httpd

    def start(self):
        """Start HTTP server in a thread"""
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

class VirtualPosPrinter:
    """Manages UI, sound, and popups"""

    def __init__(self):
        # Initialize Settings
        self.settings = self.load_settings()
        self.printer_name = self.settings.get("printer_name", DEFAULT_PRINTER_NAME)
        self.printer_port = self.parse_printer_port(self.settings.get("printer_port", DEFAULT_PRINTER_SERVER_PORT))
        self.spawn_position = self.parse_spawn_position(self.settings.get("spawn_position", (100, 100)))
        self.settings["spawn_position"] = list(self.spawn_position)
        print_info(
            f"startup settings loaded: spawn_position_raw={self.settings.get('spawn_position')} "
            f"parsed={self.spawn_position}"
        )
        self.popup_max_height_ratio = self.parse_popup_max_height_ratio(
            self.settings.get("popup_max_height_ratio", 0.8)
        )
        self.popup_max_height_px = self.parse_popup_max_height_px(
            self.settings.get("popup_max_height_px", 0)
        )
        self.popup_scroll_lines_per_tick = self.parse_popup_scroll_lines_per_tick(
            self.settings.get("popup_scroll_lines_per_tick", 6)
        )
        self.play_sound_path = os.path.abspath(os.path.join(SETTINGS_DIR, self.settings.get("play_sound", "")))
        self.play_volume = self.settings.get("play_volume", 0.25)

        # Ensure port is available
        self.ensure_port_available(self.printer_port)

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
        self.server = PrinterServer(self.printer_queue, self.http_queue, PRINTER_SERVER_ADDRESS, self.printer_port)
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

        default_settings = {
            "printer_name": DEFAULT_PRINTER_NAME,
            "printer_port": DEFAULT_PRINTER_SERVER_PORT,
            "spawn_position": (100, 100),
            "popup_max_height_ratio": 0.8,
            "popup_max_height_px": 0,
            "popup_scroll_lines_per_tick": 6,
            "enable_popups": True,
            "play_sound": "../Data/receipt-printer-01-43872.mp3",
            "play_volume": 0.13
        }

        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding="utf-8") as f:
                existing_settings = json.load(f)

            # Backfill missing keys without overwriting user values.
            merged_settings = {**default_settings, **existing_settings}
            if merged_settings != existing_settings:
                with open(SETTINGS_FILE, 'w', encoding="utf-8") as f:
                    json.dump(merged_settings, f, indent=4)
            return merged_settings

        # Write default settings to file
        with open(SETTINGS_FILE, 'w', encoding="utf-8") as f:
            json.dump(default_settings, f, indent=4)

        return default_settings

    @staticmethod
    def parse_spawn_position(value):
        """Parse spawn position from settings and return a valid (x, y) tuple."""
        default_position = (100, 100)

        if isinstance(value, dict):
            x = value.get("x")
            y = value.get("y")
        elif isinstance(value, (list, tuple)) and len(value) == 2:
            x, y = value
        else:
            print_error(
                f"Invalid 'spawn_position' value '{value}' in settings. "
                "Using default (100, 100)."
            )
            return default_position

        try:
            return int(x), int(y)
        except (TypeError, ValueError):
            print_error(
                f"Invalid 'spawn_position' coordinates '{value}' in settings. "
                "Using default (100, 100)."
            )
            return default_position

    @staticmethod
    def parse_printer_port(value):
        """Parse and validate printer port from settings."""
        try:
            port = int(value)
        except (TypeError, ValueError):
            print_error(
                f"Invalid 'printer_port' value '{value}' in settings. "
                f"Using default {DEFAULT_PRINTER_SERVER_PORT}."
            )
            return DEFAULT_PRINTER_SERVER_PORT

        if 1 <= port <= 65535:
            return port

        print_error(
            f"Out-of-range 'printer_port' value '{value}' in settings. "
            f"Using default {DEFAULT_PRINTER_SERVER_PORT}."
        )
        return DEFAULT_PRINTER_SERVER_PORT

    @staticmethod
    def parse_popup_max_height_ratio(value):
        """Parse popup max-height ratio from settings."""
        try:
            ratio = float(value)
        except (TypeError, ValueError):
            print_error(
                f"Invalid 'popup_max_height_ratio' value '{value}' in settings. "
                "Using default 0.8."
            )
            return 0.8

        if 0.2 <= ratio <= 1.0:
            return ratio

        print_error(
            f"Out-of-range 'popup_max_height_ratio' value '{value}' in settings. "
            "Using default 0.8."
        )
        return 0.8

    @staticmethod
    def parse_popup_max_height_px(value):
        """Parse popup max-height override in pixels from settings."""
        try:
            pixels = int(value)
        except (TypeError, ValueError):
            print_error(
                f"Invalid 'popup_max_height_px' value '{value}' in settings. "
                "Using default 0 (disabled)."
            )
            return 0

        if pixels >= 0:
            return pixels

        print_error(
            f"Out-of-range 'popup_max_height_px' value '{value}' in settings. "
            "Using default 0 (disabled)."
        )
        return 0

    @staticmethod
    def parse_popup_scroll_lines_per_tick(value):
        """Parse mousewheel scroll speed for scrollable popups."""
        try:
            lines = int(value)
        except (TypeError, ValueError):
            print_error(
                f"Invalid 'popup_scroll_lines_per_tick' value '{value}' in settings. "
                "Using default 6."
            )
            return 6

        if 1 <= lines <= 50:
            return lines

        print_error(
            f"Out-of-range 'popup_scroll_lines_per_tick' value '{value}' in settings. "
            "Using default 6."
        )
        return 6

    def get_popup_max_height(self):
        """Get popup max height in pixels, clamped to the visible screen area."""
        screen_height = max(200, int(self.root.winfo_screenheight()))
        safe_screen_cap = max(120, screen_height - 80)
        configured_height = (
            self.popup_max_height_px
            if self.popup_max_height_px > 0
            else int(screen_height * self.popup_max_height_ratio)
        )
        return max(120, min(configured_height, safe_screen_cap))

    def capture_mouse_position(self):
        """Set spawn position based on current mouse position"""
        x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
        self.settings["spawn_position"] = [x, y]
        self.spawn_position = (x, y)
        print_info(f"capture_mouse_position: pointer=({x}, {y})")

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
            self.refresh_runtime_settings()
            print_info(
                f"process_print_queue: message_len={len(message)} "
                f"enable_popups={self.settings.get('enable_popups', True)} "
                f"spawn_position={self.spawn_position}"
            )
            if self.settings.get("enable_popups", True):
                self.create_window(message)
                self.sound_player.play()
        except queue.Empty:
            pass
        self.root.after(100, self.process_print_queue)

    def refresh_runtime_settings(self):
        """Refresh runtime settings that affect popup behavior."""
        try:
            with open(SETTINGS_FILE, 'r', encoding="utf-8") as f:
                latest_settings = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        self.settings.update(latest_settings)
        self.spawn_position = self.parse_spawn_position(
            latest_settings.get("spawn_position", self.spawn_position)
        )
        print_info(
            f"refresh_runtime_settings: settings.spawn_position="
            f"{latest_settings.get('spawn_position')} parsed={self.spawn_position}"
        )

    @staticmethod
    def resolve_popup_position(spawn_position, active_windows):
        """Resolve next popup position based on spawn point and current cascade state."""
        if active_windows:
            last_x, last_y = active_windows[-1]
            x_offset = min((last_x + 10 - spawn_position[0]), 100)
            y_offset = min((last_y + 10 - spawn_position[1]), 100)
            return spawn_position[0] + x_offset, spawn_position[1] + y_offset
        return spawn_position

    @staticmethod
    def build_geometry_position(x, y):
        """Build signed Tk geometry position segment, e.g. +100-50."""
        return f"{int(x):+d}{int(y):+d}"

    def create_window(self, data):
        """Create a dynamically positioned pop-up window for print messages."""
        window = tk.Toplevel()
        window.overrideredirect(1)
        window.configure(bg='white', highlightbackground='gray', highlightthickness=2, bd=2)

        # Use a font consistent with the default settings
        window_font = font.Font(family=self.default_font.cget("family"),
                                size=self.default_font.cget("size"))

        line_count = max(1, data.count("\n") + 1)
        line_height = max(1, int(window_font.metrics("linespace")))
        estimated_content_height = line_count * line_height + 20
        max_height = self.get_popup_max_height()
        needs_scroll = estimated_content_height > max_height

        scroll_text_widget = None
        close_widgets = [window]
        drag_widgets = [window]
        wheel_widgets = [window]

        if needs_scroll:
            content_frame = tk.Frame(window, bg="white")
            content_frame.pack(fill="both", expand=True)

            scrollbar = tk.Scrollbar(content_frame, orient="vertical")
            scrollbar.pack(side="right", fill="y")

            visible_lines = max(4, int((max_height - 20) / line_height))
            scroll_text_widget = tk.Text(
                content_frame,
                font=window_font,
                bg="white",
                padx=10,
                pady=10,
                wrap="word",
                yscrollcommand=scrollbar.set,
                height=visible_lines,
                relief="flat",
                highlightthickness=0,
                bd=0
            )
            scroll_text_widget.insert("1.0", data)
            scroll_text_widget.configure(state="disabled")
            scroll_text_widget.pack(side="left", fill="both", expand=True)
            scrollbar.configure(command=scroll_text_widget.yview)
            close_widgets.extend([content_frame, scrollbar, scroll_text_widget])
            drag_widgets.extend([content_frame, scroll_text_widget])
            wheel_widgets.extend([content_frame, scroll_text_widget])
        else:
            label = tk.Label(window, text=data, font=window_font,
                             bg='white', padx=10, pady=10, anchor='w', justify='left')
            label.pack()
            close_widgets.append(label)
            drag_widgets.append(label)
            wheel_widgets.append(label)

        # Cascade windows if needed
        if self.active_windows:
            last_x, last_y = self.active_windows[-1]
            new_x, new_y = self.resolve_popup_position(self.spawn_position, self.active_windows)
            x_offset = new_x - self.spawn_position[0]
            y_offset = new_y - self.spawn_position[1]
            print_info(
                f"create_window: cascade base={self.spawn_position} "
                f"last=({last_x}, {last_y}) offset=({x_offset}, {y_offset}) "
                f"new=({new_x}, {new_y})"
            )
        else:
            new_x, new_y = self.resolve_popup_position(self.spawn_position, self.active_windows)
            print_info(f"create_window: first window using spawn_position={self.spawn_position}")

        geometry_position = self.build_geometry_position(new_x, new_y)
        print_info(f"create_window: geometry_position={geometry_position} needs_scroll={needs_scroll}")

        window.update_idletasks()
        if needs_scroll:
            req_width = window.winfo_reqwidth()
            req_height = min(window.winfo_reqheight(), max_height)
            window.geometry(f"{req_width}x{req_height}{geometry_position}")
        else:
            window.geometry(geometry_position)

        window.update_idletasks()
        print_info(
            f"create_window: requested=({new_x}, {new_y}) actual=({window.winfo_x()}, {window.winfo_y()}) "
            f"size=({window.winfo_width()}x{window.winfo_height()})"
        )
        self.active_windows.append((new_x, new_y))

        def on_close():
            """Close the popup window on right-click."""
            window.focus_force()
            if (new_x, new_y) in self.active_windows:
                self.active_windows.remove((new_x, new_y))
            window.destroy()

        for widget in close_widgets:
            widget.bind("<ButtonRelease-3>", lambda event: on_close())

        # Enable window dragging
        start_mouse_x, start_mouse_y = 0, 0
        start_window_x, start_window_y = 0, 0
        drag_active = False

        def on_mouse_press(event):
            nonlocal start_mouse_x, start_mouse_y, start_window_x, start_window_y, drag_active
            if isinstance(event.widget, tk.Scrollbar):
                drag_active = False
                return
            drag_active = True
            start_mouse_x, start_mouse_y = event.x_root, event.y_root
            start_window_x, start_window_y = window.winfo_x(), window.winfo_y()

        def on_mouse_drag(event):
            if not drag_active or isinstance(event.widget, tk.Scrollbar):
                return
            new_x = start_window_x + (event.x_root - start_mouse_x)
            new_y = start_window_y + (event.y_root - start_mouse_y)
            window.geometry(f"+{new_x}+{new_y}")

        for widget in drag_widgets:
            widget.bind("<Button-1>", on_mouse_press)
            widget.bind("<B1-Motion>", on_mouse_drag)

        # Prevent text-selection drag behavior from fighting popup dragging.
        if scroll_text_widget is not None:
            scroll_text_widget.bind("<Button-1>", lambda event: (on_mouse_press(event), "break")[1])
            scroll_text_widget.bind("<B1-Motion>", lambda event: (on_mouse_drag(event), "break")[1])

        # Keep the popup always on top
        window.attributes('-topmost', True)
        window.lift()
        window.focus_force()

        # Allow font resizing via Ctrl + Mouse Wheel
        def handle_mouse_wheel(event):
            if event.state & 0x0004:  # Detect if Control key is pressed
                window.focus_force()
                current_size = int(window_font.cget("size"))
                new_size = current_size + 2 if event.delta > 0 else max(6, current_size - 2)
                window_font.config(size=new_size)

                if scroll_text_widget is not None:
                    new_line_height = max(1, int(window_font.metrics("linespace")))
                    visible_lines = max(4, int((max_height - 20) / new_line_height))
                    scroll_text_widget.configure(height=visible_lines)
                    window.update_idletasks()
                    req_width = window.winfo_reqwidth()
                    req_height = min(window.winfo_reqheight(), max_height)
                    window.geometry(f"{req_width}x{req_height}+{window.winfo_x()}+{window.winfo_y()}")
                return "break"

            if scroll_text_widget is not None:
                if not event.delta:
                    return "break"

                # event.delta can be smaller than 120 on some high-resolution wheels;
                # always scroll at least one step in the intended direction.
                direction = -1 if event.delta > 0 else 1
                wheel_steps = max(1, abs(int(event.delta)) // 120)
                scroll_units = direction * wheel_steps * self.popup_scroll_lines_per_tick
                scroll_text_widget.yview_scroll(scroll_units, "units")
                return "break"
            return None

        for widget in wheel_widgets:
            widget.bind("<MouseWheel>", handle_mouse_wheel)

    def setup_printer(self):
        """Setup printer in Windows"""
        printer_name = self.printer_name
        printer_port = self.printer_port
        driver_name = "Generic / Text Only"

        print_color("---CHECKING PRINTER STATUS--------------------------------------", color="yellow", bold=False)

        powershell_script = f"""
        try {{
            $portName = "{PRINTER_SERVER_ADDRESS}_{printer_port}"
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
                Add-PrinterPort -Name $portName -PrinterHostAddress "{PRINTER_SERVER_ADDRESS}" -PortNumber {printer_port}
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

                # Ensure existing printer is bound to the configured port.
                $currentPort = (Get-Printer -Name $printerName).PortName
                if ($currentPort -ne $portName) {{
                    Write-Host "Printer is on '$currentPort'. Reassigning to '$portName'..."
                    Set-Printer -Name $printerName -PortName $portName
                    Write-Host "Printer reassigned successfully."
                }} else {{
                    Write-Host "Printer is already assigned to the expected port."
                }}
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
        print_color("- Press [yellow(]Ctrl+Alt+Shift+P[)] to set the popup print location.")
        print_color(f"- In the Fenix A32x EFB, set the printer to [yellow(]'{self.printer_name}'[)] to enable printing.")
        print_color(f"- Current printer port: [yellow(]{self.printer_port}[)]")
        print("- Right-click a popup print to close it.")
        print("- Click 'Open Settings' to change script settings.")
        print("- Keep this script running for printer popups to work.")
        print("- Add this script to 'Scripts/_autoplay.script_group' to start it automatically.")
        print("- Click 'OpenHelp' for detailed usage instructions.")

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
