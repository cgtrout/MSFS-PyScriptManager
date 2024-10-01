# virtual_pos_printer: Runs as a virtual printer and shows print-out as popup.  Will also configure network windows printer if needed.

import socket
import threading
import tkinter as tk
from tkinter import font, messagebox
import queue
import re
import subprocess
import os
import json
import keyboard

# Define constants for server address and port
SERVER_ADDRESS = '127.0.0.1'
SERVER_PORT = 9102

# Define the settings file location
SETTINGS_DIR = os.path.join(os.path.dirname(__file__), '../Settings')
SETTINGS_FILE = os.path.join(SETTINGS_DIR, 'settings.json')

# Create the directory if it doesn't exist
os.makedirs(SETTINGS_DIR, exist_ok=True)

# Load and Save Settings
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {"spawn_position": (100, 100)}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

# Load settings from the file
settings = load_settings()
spawn_position = tuple(settings.get("spawn_position", (100, 100)))

# Variables for cascading windows
active_windows = []  # List of current window positions
MAX_OFFSET = 100     # Maximum allowable offset for cascading
OFFSET_STEP = 10     # Step size for offset

# Function to detect and install the printer
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
        $portName = "{SERVER_ADDRESS}_{SERVER_PORT}"
        $printerName = "{printer_name}"

        # Check if the 'Generic / Text Only' printer driver is installed
        $driverName = "{driver_name}"
        if (!(Get-PrinterDriver -Name $driverName -ErrorAction SilentlyContinue)) {{
            Write-Host "Installing printer driver: {driver_name}"
            Add-PrinterDriver -Name $driverName
        }}

        # Add a new TCP/IP Port that points to the loopback address
        if (!(Get-PrinterPort -Name $portName -ErrorAction SilentlyContinue)) {{
            Add-PrinterPort -Name $portName -PrinterHostAddress "{SERVER_ADDRESS}" -PortNumber {SERVER_PORT}
        }}

        # Install the printer using the Generic / Text Only driver
        if (!(Get-Printer -Name $printerName -ErrorAction SilentlyContinue)) {{
            Add-Printer -Name $printerName -DriverName $driverName -PortName $portName
            Write-Host "Printer successfully added."
        }} else {{
            Write-Host "Printer already exists."
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

# Server code (a virtual printer server to intercept print jobs)
def start_virtual_printer_server(q):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_address = (SERVER_ADDRESS, SERVER_PORT)
    server_socket.bind(server_address)
    server_socket.listen(5)

    print(f"Server is listening on {SERVER_ADDRESS}:{SERVER_PORT}")
    
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
            cleaned_data = re.sub(r'[\r\n]+', '\n', decoded_data)  # Remove excess newlines
            cleaned_data = cleaned_data.replace('\x0c', '')  # Remove form feed (\x0c)
            acars_message = extract_acars_message(cleaned_data)
            q.put(acars_message)

        except Exception as e:
            print(f"Error: {e}")
        finally:
            connection.close()

def extract_acars_message(data):
    match = re.search(r'ACARS BEGIN\s*(.*?)\s*ACARS END', data, re.DOTALL)
    if match:
        return match.group(1).strip()
    return data

def capture_mouse_position():
    global spawn_position
    x = root.winfo_pointerx()
    y = root.winfo_pointery()
    spawn_position = (x, y)
    
    settings["spawn_position"] = spawn_position
    save_settings(settings)

    messagebox.showinfo("Position Set", f"Spawn position set to: {spawn_position}")
    print(f"Spawn position set to: {spawn_position}")

def create_window(data, default_font):
    global active_windows

    # Create a new window
    window = tk.Toplevel()
    window.overrideredirect(1)
    
    # Add a light gray border
    window.configure(bg='white', highlightbackground='gray', highlightthickness=2, bd=2)

    # Create a new font instance for this specific window
    window_font = font.Font(family=default_font.cget("family"), size=default_font.cget("size"))

    label = tk.Label(window, text=data, font=window_font, bg='white', padx=10, pady=10, anchor='w', justify='left')
    label.pack()

    # Determine the next position based on active windows
    if active_windows:
        last_x, last_y = active_windows[-1]
        x_offset = min((last_x + OFFSET_STEP - spawn_position[0]), MAX_OFFSET)
        y_offset = min((last_y + OFFSET_STEP - spawn_position[1]), MAX_OFFSET)
        new_x, new_y = spawn_position[0] + x_offset, spawn_position[1] + y_offset
    else:
        new_x, new_y = spawn_position

    # Position the window with cascading effect
    window.geometry(f"+{new_x}+{new_y}")
    active_windows.append((new_x, new_y))

    def on_close():
        # Remove from active window list when closed
        active_windows.remove((new_x, new_y))
        window.destroy()

    # Bind right-click to close the window
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
        if event.state & 0x0004:
            current_size = window_font.cget("size")
            new_size = current_size + 2 if event.delta > 0 else current_size - 2
            window_font.config(size=new_size)

    window.bind("<Enter>", lambda event: window.bind("<MouseWheel>", scale_font))
    window.bind("<Leave>", lambda event: window.unbind("<MouseWheel>"))

def process_queue(default_font):
    try:
        message = q.get_nowait()
        print(f"Processing message: {message}")
        create_window(message, default_font)
    except queue.Empty:
        pass
    except Exception as e:
        print(f"Error in process_queue: {e}")
    root.after(100, process_queue, default_font)

# Initialize the Tkinter application
root = tk.Tk()
root.withdraw()

# Create a queue for inter-thread communication
q = queue.Queue()

# Start a thread for the fake printer server
printer_thread = threading.Thread(target=start_virtual_printer_server, args=(q,))
printer_thread.daemon = True
printer_thread.start()

# Default font for the pop-up windows
default_font = font.Font(family="Consolas", size=12)

# Check and install the printer if necessary
setup_printer()

# Start processing the queue
root.after(100, process_queue, default_font)

# Global keyboard shortcut to set spawn position
keyboard.add_hotkey('ctrl+shift+p', capture_mouse_position)

# Start the Tkinter main event loop
root.mainloop()
