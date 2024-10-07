# virtual_pos_printer: Runs as a virtual printer and shows print-out as popup.  Will also configure network windows printer if needed.

import socket
import threading
import tkinter as tk
from tkinter import font, messagebox
import signal
import sys
import queue
import json
import keyboard
import http.server
import socketserver
import os
import re
import subprocess

# Define constants for server address and port
PRINTER_SERVER_ADDRESS = '127.0.0.1'
PRINTER_SERVER_PORT = 9102
HTTP_SERVER_PORT = 40001

# Define the settings file location
SETTINGS_DIR = os.path.join(os.path.dirname(__file__), '../Settings')
SETTINGS_FILE = os.path.join(SETTINGS_DIR, 'settings.json')

# Create the directory if it doesn't exist
os.makedirs(SETTINGS_DIR, exist_ok=True)

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
    else:
        settings = {}

    # Ensure all required settings keys are present
    updated = False
    if "spawn_position" not in settings:
        settings["spawn_position"] = (100, 100)
        updated = True
    if "enable_popups" not in settings:
        settings["enable_popups"] = True
        updated = True

    # Save the updated settings if new keys were added
    if updated:
        save_settings(settings)

    if not settings.get("enable_popups", True):
        print("\n" + "="*50)
        print("WARNING: Pop-up windows are currently disabled!")
        print("Printout notifications will NOT be shown (Windows).")
        print("\nTo enable Windows printer popups, update the setting:")
        print("   File: /Settings/settings.json")
        print("   Setting: \"enable_popups\": true")
        print("\nNOTE: You can disregard this warning if you are using the community add-on.")
        print("="*50 + "\n")

    return settings

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=4)  # Adds indentation for pretty formatting

settings = load_settings()
spawn_position = tuple(settings.get("spawn_position", (100, 100)))

# Variables for cascading windows
active_windows = []
MAX_OFFSET = 100
OFFSET_STEP = 10

# Queue to store messages sequentially for server out (community module)
http_message_queue = queue.Queue()

# Function to capture mouse position for setting spawn position
def capture_mouse_position():
    global spawn_position
    x = root.winfo_pointerx()
    y = root.winfo_pointery()
    spawn_position = (x, y)
    
    settings["spawn_position"] = spawn_position
    save_settings(settings)
    
    messagebox.showinfo("Position Set", f"Spawn position set to: {spawn_position}")
    print(f"Spawn position set to: {spawn_position}")

# Function to create a new window with the given data
def create_window(data, default_font):
    global active_windows

    window = tk.Toplevel()
    window.overrideredirect(1)
    window.configure(bg='white', highlightbackground='gray', highlightthickness=2, bd=2)
    window_font = font.Font(family=default_font.cget("family"), size=default_font.cget("size"))
    label = tk.Label(window, text=data, font=window_font, bg='white', padx=10, pady=10, anchor='w', justify='left')
    label.pack()

    # try to cascade the output
    if active_windows:
        last_x, last_y = active_windows[-1]
        x_offset = min((last_x + OFFSET_STEP - spawn_position[0]), MAX_OFFSET)
        y_offset = min((last_y + OFFSET_STEP - spawn_position[1]), MAX_OFFSET)
        new_x, new_y = spawn_position[0] + x_offset, spawn_position[1] + y_offset
    else:
        new_x, new_y = spawn_position

    window.geometry(f"+{new_x}+{new_y}")
    active_windows.append((new_x, new_y))

    def on_close():
        active_windows.remove((new_x, new_y))
        window.destroy()

    window.bind("<ButtonRelease-3>", lambda event: on_close())

    mouse_x = 0
    mouse_y = 0

    def on_mouse_press(event):
        nonlocal mouse_x, mouse_y
        mouse_x = event.x
        mouse_y = event.y

    def on_mouse_drag(event):
        x = window.winfo_x() - mouse_x + event.x
        y = window.winfo_y() - mouse_y + event.y
        window.geometry(f"+{x}+{y}")

    window.bind("<Button-1>", on_mouse_press)
    window.bind("<B1-Motion>", on_mouse_drag)

    window.attributes('-topmost', True)
    window.lift()
    window.focus_force()

    def scale_font(event):
        # detect control
        if event.state & 0x0004:
            current_size = window_font.cget("size")
            new_size = current_size + 2 if event.delta > 0 else current_size - 2
            window_font.config(size=new_size)

    window.bind("<Enter>", lambda event: window.bind("<MouseWheel>", scale_font))
    window.bind("<Leave>", lambda event: window.unbind("<MouseWheel>"))

# Function to process messages from the queue
def process_print_queue(default_font):
    try:
        # Are popups enabled?
        if not settings.get("enable_popups", True):
            message = printer_message_queue.get_nowait()
            return

        # Pop-ups are enabled, process the message and create a window
        message = printer_message_queue.get_nowait()
        print(f"Processing message: {message}")
        create_window(message, default_font)
        
    except queue.Empty:
        pass
    except Exception as e:
        print(f"Error in process_queue: {e}")

    root.after(100, process_print_queue, default_font)

# Server code (a virtual printer server to intercept print jobs)
def start_virtual_printer_server(printer_message_queue):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_address = (PRINTER_SERVER_ADDRESS, PRINTER_SERVER_PORT)
    server_socket.bind(server_address)
    server_socket.listen(5)

    print(f"Printer server is listening on {PRINTER_SERVER_ADDRESS}:{PRINTER_SERVER_PORT}")
    
    while True:
        connection, client_address = server_socket.accept()
        print(f'Connection from {client_address}')

        try:
            data = b""
            while True:
                part = connection.recv(1024)
                if not part:
                    break
                data += part

            decoded_data = data.decode('utf-8')
            cleaned_data = re.sub(r'[\r\n]+', '\n', decoded_data)
            cleaned_data = cleaned_data.replace('\x0c', '')
            acars_message = extract_acars_message(cleaned_data)
            printer_message_queue.put(acars_message)

            http_message_queue.put(acars_message)  # Store the message in the queue

        except Exception as e:
            print(f"Error: {e}")
        finally:
            connection.close()

def extract_acars_message(data):
    match = re.search(r'ACARS BEGIN\s*(.*?)\s*ACARS END', data, re.DOTALL)
    if match:
        return match.group(1).strip()
    return data

# HTTP Server to serve the next message from the queue
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

# Start the HTTP server
def start_http_server():
    with socketserver.TCPServer(("", HTTP_SERVER_PORT), HttpRequestHandler, bind_and_activate=False) as httpd:
        httpd.allow_reuse_address = True
        httpd.server_bind()
        httpd.server_activate()
        print(f"HTTP Server serving on port {HTTP_SERVER_PORT}\n")
        httpd.serve_forever()

# Setup printer using PowerShell
def setup_printer():
    printer_name = "VirtualTextPrinter"
    driver_name = "Generic / Text Only"

    # PowerShell command to check if the printer exists
    check_printer_cmd = f"Get-Printer -Name '{printer_name}'"
    
    try:
        # Check if the printer exists by running the PowerShell command with no window
        print(f"Checking if printer '{printer_name}' is installed...")
        result = subprocess.run(
            ["powershell", "-Command", check_printer_cmd],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        if printer_name in result.stdout:
            print(f"Printer '{printer_name}' is already installed.")
            return  # Printer exists, no need to install
        
        # If the printer doesn't exist, install it
        print(f"Printer '{printer_name}' not found. Installing printer...")

        powershell_script = f"""
        try {{
            $portName = "${PRINTER_SERVER_ADDRESS}_${PRINTER_SERVER_PORT}"
            $printerName = "{printer_name}"
          
            # Check if the 'Generic / Text Only' printer driver is installed
            $driverName = "{driver_name}"
            if (!(Get-PrinterDriver -Name $driverName -ErrorAction SilentlyContinue)) {{
                Write-Host "Installing printer driver: {driver_name}"
                Add-PrinterDriver -Name $driverName
            }}
            
            # Add a new TCP/IP Port that points to the loopback address
            if (!(Get-PrinterPort -Name $portName -ErrorAction SilentlyContinue)) {{
                Add-PrinterPort -Name $portName -PrinterHostAddress "${PRINTER_SERVER_ADDRESS}" -PortNumber ${PRINTER_SERVER_PORT}
            }}

            # Install the printer using the Generic / Text Only driver
            if (!(Get-Printer -Name $printerName -ErrorAction SilentlyContinue)) {{
                Add-Printer -Name $printerName -DriverName $driverName -PortName $portName
                Write-Host "Printer successfully added."
            }} else {{
                Write-Host "Printer already exists."
            }}
        }} catch {{
            Write-Error "An error occurred: $_"
            exit 1  # Exit with a non-zero code so Python knows there was an issue
        }}
        """

        # Save the PowerShell script to a temporary file
        script_path = os.path.join(os.getcwd(), "setup_printer.ps1")
        with open(script_path, "w") as script_file:
            script_file.write(powershell_script)

        # Run the PowerShell script to install the printer with no window
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        print(f"PowerShell stdout: {result.stdout}")
        print(f"PowerShell stderr: {result.stderr}")
        
        if "Printer successfully added." in result.stdout:
            print("Printer installation completed.")
        else:
            print("Printer installation may have failed. Check PowerShell output.")

        # Clean up the temporary PowerShell script file
        os.remove(script_path)

    except subprocess.CalledProcessError as e:
        print(f"Error checking or installing printer: {e}")

# Initialize Tkinter
root = tk.Tk()
root.withdraw()

# Default font for pop-up windows
default_font = font.Font(family="Consolas", size=12)

# Create a queue for communication
printer_message_queue = queue.Queue()

# Setup printer
setup_printer()

# Start printer server thread
printer_thread = threading.Thread(target=start_virtual_printer_server, args=(printer_message_queue,))
printer_thread.daemon = True
printer_thread.start()

# Start HTTP server thread
http_server_thread = threading.Thread(target=start_http_server)
http_server_thread.daemon = True
http_server_thread.start()

# Start processing queue
root.after(100, process_print_queue, default_font)

# Global keyboard shortcut for setting spawn position
keyboard.add_hotkey('ctrl+shift+p', capture_mouse_position)

# Handle termination signals (SIGINT and SIGTERM) for a graceful shutdown
def signal_handler(sig, frame):
    print("Shutting down...")
    root.quit()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)  # Capture SIGINT (Ctrl+C)
signal.signal(signal.SIGTERM, signal_handler)  # Capture SIGTERM

# Start Tkinter main loop
root.mainloop()