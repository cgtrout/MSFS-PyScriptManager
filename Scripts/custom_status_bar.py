# custom_status_bar.py: shows a draggable, customizable status bar using SimConnect to display real-time flight simulator metrics like time, altitude, and temperature in a compact GUI.
#   - use instructions below to customize
#   - Uses https://github.com/odwdinc/Python-SimConnect library to obtain values from SimConnect

import tkinter as tk
from tkinter import simpledialog, messagebox
from SimConnect import SimConnect, AircraftRequests
from datetime import datetime, timezone, timedelta
import os
import json

# Print initial message
print("custom_status_bar: Close this window to close status bar")

# DISPLAY_TEMPLATE
# The DISPLAY_TEMPLATE defines the content and format of the data displayed in the application's window.
# It serves as a blueprint for what information should be shown (e.g., simulator time, altitude) and how it should be styled.
# This template can include dynamic data elements, specified using 'VAR()' blocks, as well as static text.
# Each 'VAR()' block is defined as VAR(label, function_name, color), where:
# 'label' specifies the static text prefix,
# 'function_name' references a Python function used to fetch dynamic values,
# 'color' determines the text rendering color for both the label and value.

DISPLAY_TEMPLATE = "VAR(Sim:, get_sim_time, yellow) | VAR(Zulu:, get_real_world_time, white) | VAR(Sim Rate:, get_sim_rate, white) | VAR(Remaining:, get_time_to_future, red) | VAR(, get_temp, cyan)"

# Other examples that can be placed in template
# VAR(Altitude:, get_altitude, tomato)

# Configurable Variables
alpha_transparency_level = 0.95  # Set transparency (0.0 = fully transparent, 1.0 = fully opaque)
WINDOW_TITLE = "Simulator Time"
DARK_BG = "#000000"
FONT = ("Helvetica", 16)
UPDATE_INTERVAL = 500  # in milliseconds (1 second)
RECONNECT_INTERVAL = 1000  # in milliseconds (5 seconds)
PADDING_X = 20  # Horizontal padding for each label
PADDING_Y = 10  # Vertical padding for the window

sm = None
aq = None
sim_connected = False
future_time = None  # Time for countdown in seconds
last_entered_time = None  # Last entered future time in HHMM format

# --- SimConnect Lookup  ---
def get_sim_time():
    """Fetch the simulator time from SimConnect, formatted as HH:MM:SS."""
    try:
        sim_time_seconds = get_simconnect_value("ZULU_TIME")
        # Create a datetime object starting from midnight and add the sim time seconds
        sim_time = (datetime.min + timedelta(seconds=int(sim_time_seconds))).time()
        return sim_time.strftime("%H:%M:%S")
    except Exception as e:
        return str(e)

def get_real_world_time():
    """Fetch the real-world Zulu time."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def get_altitude():
    """Fetch the altitude from SimConnect, formatted in feet."""
    return get_formatted_value("PLANE_ALTITUDE", "{:.0f} ft")

def get_sim_rate():
    """Fetch the sim rate from SimConnect, formatted in feet."""
    return get_formatted_value("SIMULATION_RATE", "{:.1f}")

def get_temp():
    """Fetch both TAT and SAT temperatures from SimConnect, formatted with labels."""
    return get_formatted_value(["AMBIENT_TEMPERATURE", "TOTAL_AIR_TEMPERATURE"], "TAT {1:.0f}°C  SAT {0:.0f}°C")

def get_time_to_future():
    """
    Calculate remaining time to the globally configured future event.
    Returns '00:00:00' if the future time has not been set.
    """
    global future_time
    try:
        # If future_time is not set, return "00:00:00"
        if future_time is None:
            return "00:00:00"

        # Get the current simulator datetime
        current_sim_time = get_simulator_datetime()

        # Calculate remaining time
        remaining_time = future_time - current_sim_time

        # If the remaining time is zero or negative, return "00:00:00"
        if remaining_time.total_seconds() <= 0:
            return "00:00:00"

        # Format the remaining time as HH:MM:SS
        hours, remainder = divmod(remaining_time.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_time = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

        return formatted_time

    except Exception as e:
        return str(e)

def initialize_simconnect():
    """Initialize the connection to SimConnect."""
    global sm, aq, sim_connected
    try:
        sm = SimConnect()  # Connect to SimConnect
        aq = AircraftRequests(sm)
        sim_connected = True
    except Exception:
        sim_connected = False
        root.after(RECONNECT_INTERVAL, initialize_simconnect)

def get_simconnect_value(variable_name):
    """Generalized function to fetch a SimConnect variable, raising an exception on error."""
    if not sim_connected:
        raise ConnectionError("Sim Not Running")
    
    value = aq.get(variable_name)
    if value is None:
        raise ValueError("No Data")
    return value

def get_formatted_value(variable_names, format_string=None):
    """
    Fetch one or more SimConnect variables, apply optional formatting if provided.
    
    Parameters:
    - variable_names: The SimConnect variable name(s) to retrieve (can be a single name or a list).
    - format_string: An optional string format to apply to the retrieved values.
    
    Returns:
    - The formatted string, or an error message if retrieval fails.
    """
    if isinstance(variable_names, str):
        variable_names = [variable_names]

    try:
        values = [get_simconnect_value(var) for var in variable_names]
        if format_string:
            return format_string.format(*values)
        return values[0] if len(values) == 1 else values  # Return raw value(s) if no format specified
    except Exception as e:
        return str(e)

def get_simulator_datetime():
    """
    Fetch the current simulator date and time as a datetime object.
    """
    try:
        # Fetch necessary SimConnect variables
        zulu_year = int(get_simconnect_value("ZULU_YEAR"))
        zulu_month = int(get_simconnect_value("ZULU_MONTH_OF_YEAR"))
        zulu_day = int(get_simconnect_value("ZULU_DAY_OF_MONTH"))
        zulu_time_seconds = float(get_simconnect_value("ZULU_TIME"))

        # Convert ZULU_TIME (seconds since midnight) into hours, minutes, seconds
        hours, remainder = divmod(int(zulu_time_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)

        # Construct and return the current datetime object
        simulator_datetime = datetime(zulu_year, zulu_month, zulu_day, hours, minutes, seconds)
        return simulator_datetime

    except Exception as e:
        raise ValueError(f"Failed to retrieve simulator datetime: {str(e)}")

def set_future_time():
    """Prompt the user to set a future countdown time based on Sim Time."""
    global future_time, last_entered_time
    try:
        # Get current simulator datetime
        current_sim_time = get_simulator_datetime()
        sim_time_str = current_sim_time.strftime("%H:%M:%S")

        # Prompt the user to enter the future time in HHMM format
        prompt_message = f"Enter future time based on Sim Time (HHMM)\nCurrent Sim Time: {sim_time_str}"
        future_time_input = simpledialog.askstring("Input", prompt_message, initialvalue=last_entered_time, parent=root)

        if future_time_input:
            try:
                if len(future_time_input) != 4 or not future_time_input.isdigit():
                    raise ValueError("Invalid format")
                future_hours = int(future_time_input[:2])
                future_minutes = int(future_time_input[2:])
                future_time_candidate = current_sim_time.replace(hour=future_hours, minute=future_minutes, second=0, microsecond=0)

                # If the entered future time is earlier than the current time, assume it is the next day
                if future_time_candidate <= current_sim_time:
                    future_time_candidate += timedelta(days=1)

                # Store the future time as a global datetime object
                future_time = future_time_candidate
                last_entered_time = future_time_input
                print(f"DEBUG: Future time set to: {future_time}")
            except ValueError:
                messagebox.showerror("Invalid input", "Please enter the time in HHMM format (e.g., 1642 for 16:42)")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to set future time: {str(e)}")

# --- Template Parsing  ---
def get_dynamic_value(function_name):
    """Dynamically execute the function by looking it up in the global scope."""
    try:
        if function_name in globals():
            func = globals()[function_name]
            if callable(func):
                return func()
        return None
    except Exception as e:
        print(f"Error executing function '{function_name}': {str(e)}")
        return None

def parse_template_part(part):
    """Extract the label, function, and color from a template part without regex."""
    if part.startswith("VAR(") and part.endswith(")"):
        inner_content = part[4:-1]
        parts = inner_content.split(",")
        if len(parts) == 3:
            label = parts[0].strip() + " "
            func_name = parts[1].strip()
            color = parts[2].strip()
            return label, func_name, color
    return None, None, None

# --- Display Update  ---
def update_display():
    """Update the display based on the user-defined template."""

    global is_moving  # Use the existing is_moving variable

    # Skip updates if the window is being dragged
    if is_moving:
        root.after(UPDATE_INTERVAL, update_display)
        return
    
    try:
        for widget in display_frame.winfo_children():
            widget.destroy()
        index = 0
        while index < len(DISPLAY_TEMPLATE):
            if DISPLAY_TEMPLATE[index:index + 4] == "VAR(":
                end_index = DISPLAY_TEMPLATE.find(')', index)
                if end_index == -1:
                    break
                var_content = DISPLAY_TEMPLATE[index + 4:end_index]
                index = end_index + 1
                parts = var_content.split(',')
                if len(parts) == 3:
                    label = parts[0].strip()
                    func_name = parts[1].strip()
                    color = parts[2].strip()
                    value = get_dynamic_value(func_name)
                    value_str = str(value) if value is not None else "None"
                    label_widget = tk.Label(display_frame, text=f"{label} {value_str}", fg=color, font=FONT, bg=DARK_BG)
                    label_widget.pack(side=tk.LEFT, padx=0, pady=0)
            else:
                next_var_index = DISPLAY_TEMPLATE.find("VAR(", index)
                if next_var_index == -1:
                    next_var_index = len(DISPLAY_TEMPLATE)
                plain_text = DISPLAY_TEMPLATE[index:next_var_index]
                index = next_var_index
                if plain_text.strip():
                    plain_text_widget = tk.Label(display_frame, text=plain_text.strip(), fg="white", font=FONT, bg=DARK_BG)
                    plain_text_widget.pack(side=tk.LEFT, padx=0, pady=0)
        root.update_idletasks()
        width = display_frame.winfo_reqwidth() + PADDING_X
        height = display_frame.winfo_reqheight() + PADDING_Y
        root.geometry(f"{width}x{height}")
    except Exception as e:
        print(f"Unexpected error in display update: {e}")
    root.after(UPDATE_INTERVAL, update_display)

# --- Drag functionality ---
is_moving = False

def start_move(event):
    """Start moving the window."""
    global is_moving, offset_x, offset_y
    is_moving = True
    offset_x = event.x
    offset_y = event.y

def do_move(event):
    """Handle window movement."""
    if is_moving:
        deltax = event.x - offset_x
        deltay = event.y - offset_y
        new_x = root.winfo_x() + deltax
        new_y = root.winfo_y() + deltay
        root.geometry(f"+{new_x}+{new_y}")

def stop_move(event):
    """Stop moving the window."""
    global is_moving
    is_moving = False
    save_settings({"x": root.winfo_x(), "y": root.winfo_y()})

# --- Settings  ---
SCRIPT_DIR = os.path.dirname(__file__)
SETTINGS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "Settings")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "custom_status_bar.json")

# Ensure the Settings directory exists
os.makedirs(SETTINGS_DIR, exist_ok=True)

def load_settings():
    """Load settings from the JSON file."""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Error: Settings file is corrupted. Using defaults.")
    return {"x": 0, "y": 0}  # Default position

def save_settings(settings):
    """Save settings to the JSON file."""
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Error saving settings: {e}")

# --- Load initial settings ---
settings = load_settings()
initial_x = settings.get("x", 0)
initial_y = settings.get("y", 0)

print(f"DEBUG: Loaded settings - x: {initial_x}, y: {initial_y}")

# --- GUI Setup ---
root = tk.Tk()
root.title(WINDOW_TITLE)
root.overrideredirect(True)
root.attributes("-topmost", True)
root.attributes("-alpha", alpha_transparency_level)
root.configure(bg=DARK_BG)

# Apply initial geometry after creating the root window
try:
    # Set initial position
    root.geometry(f"+{initial_x}+{initial_y}")
    print(f"DEBUG: Applied geometry - x: {initial_x}, y: {initial_y}")
except Exception as e:
    print(f"DEBUG: Failed to apply geometry - {e}")

# Bind mouse events to enable dragging of the window
root.bind("<Button-1>", start_move)
root.bind("<B1-Motion>", do_move)
root.bind("<ButtonRelease-1>", stop_move)

# Frame to hold the labels
display_frame = tk.Frame(root, bg=DARK_BG)
display_frame.pack(padx=10, pady=5)

# --- Double click functionality for setting timer ---
root.bind("<Double-1>", lambda event: set_future_time())

# Initialize SimConnect
initialize_simconnect()

# Start the time update loop
update_display()

# Run the GUI event loop
root.mainloop()
