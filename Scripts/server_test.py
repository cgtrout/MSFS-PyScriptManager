import socket
import threading
import tkinter as tk
from tkinter import font, messagebox
import queue  # Queue to handle sequential messages
import json
import keyboard
import http.server
import socketserver
import time
import os

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

settings = load_settings()
spawn_position = tuple(settings.get("spawn_position", (100, 100)))

# Variables for cascading windows
active_windows = []
MAX_OFFSET = 100
OFFSET_STEP = 10

# Queue to store messages sequentially
message_queue = queue.Queue()

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
        if event.state & 0x0004:
            current_size = window_font.cget("size")
            new_size = current_size + 2 if event.delta > 0 else current_size - 2
            window_font.config(size=new_size)

    window.bind("<Enter>", lambda event: window.bind("<MouseWheel>", scale_font))
    window.bind("<Leave>", lambda event: window.unbind("<MouseWheel>"))

# Function to process messages from the queue
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

# HTTP Server to serve the next message from the queue
class HttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/latest":
            try:
                response = message_queue.get_nowait()  # Get the next message in the queue
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
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
    with socketserver.TCPServer(("", 40001), HttpRequestHandler) as httpd:
        print("HTTP Server serving on port 40001")
        httpd.serve_forever()

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

# Initialize Tkinter
root = tk.Tk()
root.withdraw()

# Create a queue for communication
q = queue.Queue()

# Start HTTP server thread
http_server_thread = threading.Thread(target=start_http_server)
http_server_thread.daemon = True
http_server_thread.start()

# Start simulating print jobs thread
print_jobs_thread = threading.Thread(target=simulate_print_jobs)
print_jobs_thread.daemon = True
print_jobs_thread.start()

# Default font for pop-up windows
default_font = font.Font(family="Consolas", size=12)

# Start processing queue
root.after(100, process_queue, default_font)

# Global keyboard shortcut for setting spawn position
keyboard.add_hotkey('ctrl+shift+p', capture_mouse_position)

# Start Tkinter main loop
root.mainloop()