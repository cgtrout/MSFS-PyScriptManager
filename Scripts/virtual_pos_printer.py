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

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
import pygame
import atexit

# Define constants for server address and port
PRINTER_SERVER_ADDRESS = '127.0.0.1'
PRINTER_SERVER_PORT = 9102
HTTP_SERVER_PORT = 40001

# Define the settings file location
SETTINGS_DIR = os.path.join(os.path.dirname(__file__), '../Settings')
SETTINGS_FILE = os.path.join(SETTINGS_DIR, 'settings.json')

# Create the directory if it doesn't exist
os.makedirs(SETTINGS_DIR, exist_ok=True)

# Play printer sound
def play_print_sound():
    try:
        pygame.mixer.music.load(play_sound_path)
        pygame.mixer.music.set_volume(play_volume)
        pygame.mixer.music.play()
        # print(f"Playing sound from: {play_sound_path} at volume: {play_volume}")
    except pygame.error as e:
        print(f"Error loading or playing sound: {e}")

# Load sounds from file
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
    if "play_sound" not in settings:
        settings["play_sound"] = "../Data/receipt-printer-01-43872.mp3"
        updated = True
    if "play_volume" not in settings:  
        settings["play_volume"] = 0.5  
        updated = True
    else:
        # Ensure play_volume is within the valid range (0.0 to 1.0)
        settings["play_volume"] = max(0.0, min(1.0, settings["play_volume"]))

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

# Load settings from file
settings = load_settings()
spawn_position = tuple(settings.get("spawn_position", (100, 100)))
play_sound_path = os.path.abspath(os.path.join(SETTINGS_DIR, settings.get("play_sound", "")))
play_volume = settings.get("play_volume", 0.5)  # Use the play_volume setting

# pygame sound init for sound playback
#
# Initialize pygame mixer

pygame.mixer.init()
atexit.register(pygame.mixer.quit)

# Check if the MP3 file exists
if not os.path.isfile(play_sound_path):
    print(f"Error: The sound file '{play_sound_path}' does not exist.  Sound playback will not work. Please check the path in settings.json.")
else:
    print("MP3 sound file found.")

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
        message = printer_message_queue.get_nowait()

        # Only show popup if enabled in settings
        if settings.get("enable_popups", True):
            create_window(message, default_font)
            print(f"Processing message from printer queue: {message}")
            if play_sound_path:
                play_print_sound()
        
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

    print(f"Printer server is listening on {PRINTER_SERVER_ADDRESS}:{PRINTER_SERVER_PORT}\n")
    
    while True:
        connection, client_address = server_socket.accept()
        print(f'Printer connection from {client_address}')

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
                if play_sound_path:
                    play_print_sound()
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

def setup_printer():
    printer_name = "VirtualTextPrinter"
    driver_name = "Generic / Text Only"

    print("---CHECKING PRINTER STATUS--------------------------------------")

    powershell_script = f"""
    try {{
        $portName = "{PRINTER_SERVER_ADDRESS}_{PRINTER_SERVER_PORT}"
        $printerName = "{printer_name}"
        $driverName = "{driver_name}"

        # Check if the 'Generic / Text Only' printer driver is installed
        Write-Host "Checking printer driver..."
        if (!(Get-PrinterDriver -Name $driverName)) {{
            Write-Host "Printer driver is missing. Installing driver..."
            Add-PrinterDriver -Name $driverName
            Write-Host "Printer driver installed successfully."
        }} else {{
            Write-Host "Printer driver is already installed."
        }}

        # Check if the port exists; if not, create it
        Write-Host "Checking printer port..."
        if (!(Get-PrinterPort -Name $portName)) {{
            Write-Host "Printer port is missing. Creating port..."
            Add-PrinterPort -Name $portName -PrinterHostAddress "{PRINTER_SERVER_ADDRESS}" -PortNumber {PRINTER_SERVER_PORT}
            Write-Host "Printer port created successfully."
        }} else {{
            Write-Host "Printer port is already configured."
        }}

        # Check if the printer exists; if not, create it
        Write-Host "Checking printer..."
        if (!(Get-Printer -Name $printerName)) {{
            Write-Host "Printer is missing. Installing printer..."
            Add-Printer -Name $printerName -DriverName $driverName -PortName $portName
            Write-Host "Printer installed successfully."
        }} else {{
            Write-Host "Printer is already installed."
        }}

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
        # Run the PowerShell script inline (no temp file)
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", powershell_script],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )

        # Output the result of the PowerShell script to the user (filtered)
        if result.returncode == 0:
            print(result.stdout.strip())
        else:
            print("An error occurred during setup. Please try again.")
            print(f"Error details: {result.stderr}")

    except subprocess.CalledProcessError:
        print("An error occurred during the process. Please try again.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    print("----------------------------------------------------------------")

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