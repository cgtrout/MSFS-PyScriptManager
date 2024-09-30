# get_sim_time.py: shows floating time bar for MSFS

import tkinter as tk
from tkinter import ttk, Menu, simpledialog, messagebox
from SimConnect import SimConnect, AircraftRequests
from datetime import datetime, timezone, timedelta

# Print initial message
print("Simulator Time Display: Close this window to close time display")

# Configurable Variables
WINDOW_TITLE = "Simulator Time"
DARK_BG = "#000000"
SIM_TEXT_COLOR = "#FFFF00"  # Light Yellow
ZULU_TEXT_COLOR = "#FFFFFF"  # White
TIMER_TEXT_COLOR = "#FF6347"  # Tomato
TEMP_TEXT_COLOR = "#00FFFF"  # Cyan
FONT = ("Helvetica", 16)
UPDATE_INTERVAL = 1000  # in milliseconds (1 second)
RECONNECT_INTERVAL = 5000  # in milliseconds (5 seconds)
PADDING_X = 10  # Horizontal padding for each label
PADDING_Y = 10  # Vertical padding for the window

# Initialize SimConnect variables
sm = None
aq = None
sim_connected = False
future_time = None  # Time for countdown in seconds
last_entered_time = None  # Last entered future time in HHMM format

# Function to initialize SimConnect
def initialize_simconnect():
    global sm, aq, sim_connected
    try:
        sm = SimConnect()
        aq = AircraftRequests(sm)
        sim_connected = True
    except Exception as e:
        sim_connected = False
        root.after(RECONNECT_INTERVAL, initialize_simconnect)

# Function to get current simulator time in seconds and convert to HH:MM:SS format
def get_sim_time():
    global sim_connected
    if not sim_connected:
        return "Sim Not Running"
    try:
        sim_time_seconds = aq.get("ZULU_TIME")
        if sim_time_seconds is None:
            return "No Data"
        return sim_time_seconds
    except Exception:
        sim_connected = False
        root.after(RECONNECT_INTERVAL, initialize_simconnect)
        return "Disconnected"

# Function to get TAT and SAT temperatures
def get_temperatures():
    global sim_connected
    if not sim_connected:
        return ("N/A", "N/A")
    try:
        tat = aq.get("AMBIENT_TEMPERATURE")  # Adjust this key if necessary
        # sat = aq.get("AMBIENT_STATIC_TEMPERATURE")  # Adjust this key if necessary
        if tat is None: 
            return ("No Data", "No Data")
        return (tat, "N/A")  # Ensure it's a tuple with two elements
    except Exception:
        sim_connected = False
        root.after(RECONNECT_INTERVAL, initialize_simconnect)
        return ("Disconnected", "Disconnected")

# Function to convert seconds to HH:MM:SS format
def convert_seconds_to_hms(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"

# Function to get current real-world Zulu time
def get_real_world_time():
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

# Function to calculate the time until the future time
def get_time_to_future():
    if future_time is None:
        return "--:--:--"
    current_sim_time_seconds = get_sim_time()
    if isinstance(current_sim_time_seconds, str):  # Check if it's a string
        return "--:--:--"
    
    sim_hours = int(current_sim_time_seconds // 3600)
    future_hours = int(future_time // 3600)

    remaining_time_seconds = future_time - current_sim_time_seconds
    
    if remaining_time_seconds <= 0:
        return "00:00:00"
    return convert_seconds_to_hms(remaining_time_seconds)

# Function to update the time in the GUI
def update_time():
    current_sim_time_seconds = get_sim_time()
    if isinstance(current_sim_time_seconds, str):
        current_sim_time = current_sim_time_seconds
    else:
        current_sim_time = convert_seconds_to_hms(current_sim_time_seconds)
    
    current_real_world_time = get_real_world_time()
    time_to_future = get_time_to_future()
    tat, sat = get_temperatures()
    
    sim_time_label.config(text=f"Sim: {current_sim_time}")
    zulu_time_label.config(text=f"Zulu: {current_real_world_time}")
    timer_label.config(text=f"Rem: {time_to_future}")
    tat_rounded = tat
    if(isinstance(tat, (int,float))):
        tat_rounded = round(tat, 1)
    tat_label.config(text=f"TAT: {tat_rounded}°C")
    #sat_label.config(text=f"SAT: {sat}°C")

    # Ensure the window size adjusts to the labels
    root.update_idletasks()
    width = sim_time_label.winfo_reqwidth() + zulu_time_label.winfo_reqwidth() + timer_label.winfo_reqwidth() + tat_label.winfo_reqwidth() +5 * PADDING_X + 20
    height = max(sim_time_label.winfo_reqheight(), zulu_time_label.winfo_reqheight(), timer_label.winfo_reqheight(), tat_label.winfo_reqheight()) + PADDING_Y
    root.geometry(f"{width}x{height}")

    root.after(UPDATE_INTERVAL, update_time)  # Update every second

# Function to close the application
def close_app():
    root.quit()

# Function to set future time based on sim time
def set_future_time():
    global future_time, last_entered_time
    current_sim_time_seconds = get_sim_time()
    if isinstance(current_sim_time_seconds, str) or current_sim_time_seconds is None:
        messagebox.showerror("Sim Not Running", "Cannot set time because the simulator is not running.")
        return

    sim_time_str = convert_seconds_to_hms(current_sim_time_seconds)
    prompt_message = f"Enter future time based on Sim Time (HHMM)\nCurrent Sim Time: {sim_time_str}"
    future_time_input = simpledialog.askstring("Input", prompt_message, initialvalue=last_entered_time, parent=root)
    if future_time_input:
        try:
            if len(future_time_input) != 4 or not future_time_input.isdigit():
                raise ValueError("Invalid format")
            future_hours = int(future_time_input[:2])
            future_minutes = int(future_time_input[2:])
            future_time_seconds = future_hours * 3600 + future_minutes * 60
            if future_time_seconds <= current_sim_time_seconds:
                # Handle transition across midnight
                future_time_seconds += 24 * 3600
            future_time = future_time_seconds
            last_entered_time = future_time_input  # Store the last entered time
        except ValueError:
            messagebox.showerror("Invalid input", "Please enter the time in HHMM format (e.g., 1642 for 16:42)")

# Create the GUI window
root = tk.Tk()
root.title(WINDOW_TITLE)

# Remove the title bar
root.overrideredirect(True)

# Set the initial window size
root.geometry("800x50")

# Keep the window always on top
root.attributes("-topmost", True)

# Configure dark mode colors
root.configure(bg=DARK_BG)

# Create a frame to handle moving
main_frame = ttk.Frame(root, style="TFrame", padding=5)
main_frame.pack(expand=True, fill="both")

# Create labels to display the times with dark mode styling
sim_time_label = ttk.Label(main_frame, text="Sim: --:--:--", font=FONT, foreground=SIM_TEXT_COLOR, background=DARK_BG)
sim_time_label.pack(side="left", padx=(10, 5), pady=0)

zulu_time_label = ttk.Label(main_frame, text="Zulu: --:--:--", font=FONT, foreground=ZULU_TEXT_COLOR, background=DARK_BG)
zulu_time_label.pack(side="left", padx=(5, 5), pady=0)

timer_label = ttk.Label(main_frame, text="Rem: --:--:--", font=FONT, foreground=TIMER_TEXT_COLOR, background=DARK_BG)
timer_label.pack(side="left", padx=(5, 5), pady=0)

tat_label = ttk.Label(main_frame, text="TAT: --°C", font=FONT, foreground=TEMP_TEXT_COLOR, background=DARK_BG)
tat_label.pack(side="left", padx=(5, 5), pady=0)

#sat_label = ttk.Label(main_frame, text="SAT: --°C", font=FONT, foreground=TEMP_TEXT_COLOR, background=DARK_BG)
#sat_label.pack(side="left", padx=(5, 10), pady=0)

# Apply dark mode to the frame styles
style = ttk.Style()
style.configure("TFrame", background=DARK_BG)

# Create a right-click menu
menu = Menu(root, tearoff=0)
menu.add_command(label="Close", command=close_app)

# Function to show the right-click menu
def show_menu(event):
    menu.post(event.x_root, event.y_root)

# Bind right-click to show the menu
root.bind("<Button-3>", show_menu)

# Bind double-click to open future time entry form
root.bind("<Double-1>", lambda event: set_future_time())

# Variables to track mouse movement for dragging
is_moving = False

# Functions to handle dragging
def start_move(event):
    root.x = event.x
    root.y = event.y

def do_move(event):
    deltax = event.x - root.x
    deltay = event.y - root.y
    root.geometry(f"+{root.winfo_x() + deltax}+{root.winfo_y() + deltay}")

# Bind the left mouse button to dragging functions
main_frame.bind("<Button-1>", start_move)
main_frame.bind("<B1-Motion>", do_move)
sim_time_label.bind("<Button-1>", start_move)
sim_time_label.bind("<B1-Motion>", do_move)
zulu_time_label.bind("<Button-1>", start_move)
zulu_time_label.bind("<B1-Motion>", do_move)
timer_label.bind("<Button-1>", start_move)
timer_label.bind("<B1-Motion>", do_move)
tat_label.bind("<Button-1>", start_move)
tat_label.bind("<B1-Motion>", do_move)
#sat_label.bind("<Button-1>", start_move)
#sat_label.bind("<B1-Motion>", do_move)

# Start the time update loop
update_time()

# Try to initialize SimConnect on start
initialize_simconnect()

# Run the GUI event loop
root.mainloop()
