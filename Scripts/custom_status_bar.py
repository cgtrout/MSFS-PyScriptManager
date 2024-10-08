# custom_status_bar.py: shows a draggable, customizable status bar using SimConnect to display real-time flight simulator metrics like time, altitude, and temperature in a compact GUI.
#   - use instructions below to customize

import tkinter as tk
from tkinter import simpledialog, messagebox
from SimConnect import SimConnect, AircraftRequests
from datetime import datetime, timezone, timedelta

# Print initial message
print("custom_status_bar: Close this window to close time display")

# DISPLAY_TEMPLATE
# The DISPLAY_TEMPLATE defines the content and format of the data displayed in the application's window.
# It serves as a blueprint for what information should be shown (e.g., simulator time, altitude) and how it should be styled.
# This template can include dynamic data elements, specified using 'VAR()' blocks, as well as static text.

# Each 'VAR()' block is defined as VAR(label, function_name, color), where:
# 'label' specifies the static text prefix,
# 'function_name' references a Python function used to fetch dynamic values,
# 'color' determines the text rendering color for both the label and value.

DISPLAY_TEMPLATE = "VAR(Sim:, get_sim_time, yellow)|VAR(Zulu:, get_real_world_time, white) | VAR(Altitude:, get_altitude, tomato) | VAR(Remaining:, get_time_to_future, red) | VAR(, get_temp, cyan) "

# Configurable Variables
WINDOW_TITLE = "Simulator Time"
DARK_BG = "#000000"
FONT = ("Helvetica", 16)
UPDATE_INTERVAL = 1000  # in milliseconds (1 second)
RECONNECT_INTERVAL = 5000  # in milliseconds (5 seconds)
PADDING_X = 20  # Horizontal padding for each label
PADDING_Y = 10  # Vertical padding for the window

sm = None
aq = None
sim_connected = False
future_time = None  # Time for countdown in seconds
last_entered_time = None  # Last entered future time in HHMM format

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

def get_sim_time():
    """Fetch the simulator time from SimConnect."""
    if not sim_connected:
        return "Sim Not Running"
    
    try:
        sim_time_seconds = aq.get("ZULU_TIME")
        if sim_time_seconds is None:
            return "No Data"
        return str(timedelta(seconds=int(sim_time_seconds)))
    except Exception:
        return "Disconnected"

def get_real_world_time():
    """Fetch the real-world Zulu time."""
    return datetime.now(timezone.utc).strftime("%H:%M:%S")

def get_altitude():
    """Fetch the altitude from SimConnect."""
    if not sim_connected:
        return "Sim Not Running"
    
    try:
        altitude = aq.get("PLANE_ALTITUDE")
        if altitude is None:
            return "No Data"
        return f"{altitude:.0f} ft"
    except Exception:
        return "Disconnected"

def get_temp():
    """Fetch the Temperature from SimConnect."""
    if not sim_connected:
        return "Sim Not Running"
    
    try:
        sat = aq.get("AMBIENT_TEMPERATURE")
        tat = aq.get("TOTAL_AIR_TEMPERATURE")
        if sat is None or tat is None :
            return "No Data"
        return f"SAT:{sat:.1f}°C TAT:{tat:.1f}°C"
    except Exception:
        return "Disconnected"

def get_time_to_future():
    """Calculate remaining time to a future event or goal."""
    if future_time is None:
        return "--:--:--"
    current_sim_time_seconds = aq.get("ZULU_TIME")
    if current_sim_time_seconds is None:
        return "--:--:--"
    remaining_time_seconds = future_time - current_sim_time_seconds
    if remaining_time_seconds <= 0:
        return "00:00:00"
    return str(timedelta(seconds=int(remaining_time_seconds)))

def set_future_time():
    """Prompt the user to set a future countdown time based on Sim Time."""
    global future_time, last_entered_time
    current_sim_time_seconds = aq.get("ZULU_TIME")
    
    if current_sim_time_seconds is None:
        messagebox.showerror("Sim Not Running", "Cannot set time because the simulator is not running.")
        return
    
    # Convert the current simulator time in seconds to a datetime object for today
    current_sim_time = timedelta(seconds=int(current_sim_time_seconds))
    current_sim_datetime = datetime.combine(datetime.utcnow().date(), datetime.min.time()) + current_sim_time
    sim_time_str = current_sim_datetime.strftime("%H:%M:%S")
    
    # Prompt user for future time
    prompt_message = f"Enter future time based on Sim Time (HHMM)\nCurrent Sim Time: {sim_time_str}"
    future_time_input = simpledialog.askstring("Input", prompt_message, initialvalue=last_entered_time, parent=root)
    
    if future_time_input:
        try:
            # Validate input is exactly 4 digits and numeric
            if len(future_time_input) != 4 or not future_time_input.isdigit():
                raise ValueError("Invalid format")

            # Parse the entered time into hours and minutes
            future_hours = int(future_time_input[:2])
            future_minutes = int(future_time_input[2:])
            
            # Create a future datetime object for today with entered hours and minutes
            future_datetime = current_sim_datetime.replace(hour=future_hours, minute=future_minutes, second=0, microsecond=0)

            # If future time is earlier than or equal to the current time, add 1 day to move to the next day
            if future_datetime <= current_sim_datetime:
                future_datetime += timedelta(days=1)

            # Calculate future time in seconds since midnight
            future_time_seconds = (future_datetime - current_sim_datetime.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
            
            # Set future_time and remember last entered time
            future_time = int(future_time_seconds)
            last_entered_time = future_time_input
        
        except ValueError:
            messagebox.showerror("Invalid input", "Please enter the time in HHMM format (e.g., 1642 for 16:42)")

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
        inner_content = part[4:-1]  # Remove 'VAR(' from the beginning and ')' from the end
        parts = inner_content.split(",")
        if len(parts) == 3:
            label = parts[0].strip() + " "
            func_name = parts[1].strip()
            color = parts[2].strip()
            return label, func_name, color
    return None, None, None

def update_display():
    """Update the display based on the user-defined template."""
    try:
        # Clear the frame content before inserting new widgets
        for widget in display_frame.winfo_children():
            widget.destroy()

        # Manually parse DISPLAY_TEMPLATE to handle both VAR() elements and plain text
        index = 0
        while index < len(DISPLAY_TEMPLATE):
            if DISPLAY_TEMPLATE[index:index + 4] == "VAR(":
                # Extract everything between 'VAR(' and ')'
                end_index = DISPLAY_TEMPLATE.find(')', index)
                if end_index == -1:
                    break  # Malformed VAR(), exit loop

                # Extract the content inside VAR()
                var_content = DISPLAY_TEMPLATE[index + 4:end_index]
                index = end_index + 1

                # Split the content of VAR into label, function name, and color
                parts = var_content.split(',')
                if len(parts) == 3:
                    label = parts[0].strip()
                    func_name = parts[1].strip()
                    color = parts[2].strip()

                    # Get the value by calling the corresponding function
                    value = get_dynamic_value(func_name)
                    value_str = str(value) if value is not None else "None"

                    # Add label with the extracted color and value, with no extra spaces
                    label_widget = tk.Label(display_frame, text=f"{label} {value_str}", fg=color, font=FONT, bg=DARK_BG)
                    label_widget.pack(side=tk.LEFT, padx=0, pady=0)
            else:
                # Find the next VAR or the end of the template
                next_var_index = DISPLAY_TEMPLATE.find("VAR(", index)
                if next_var_index == -1:
                    next_var_index = len(DISPLAY_TEMPLATE)

                # Extract plain text and add it with default color (white)
                plain_text = DISPLAY_TEMPLATE[index:next_var_index]
                index = next_var_index

                # Add the plain text label with no extra spaces
                if plain_text.strip():
                    plain_text_widget = tk.Label(display_frame, text=plain_text.strip(), fg="white", font=FONT, bg=DARK_BG)
                    plain_text_widget.pack(side=tk.LEFT, padx=0, pady=0)

        # Adjust the window size dynamically
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
        root.geometry(f"+{root.winfo_x() + deltax}+{root.winfo_y() + deltay}")

def stop_move(event):
    """Stop moving the window."""
    global is_moving
    is_moving = False

# --- GUI Setup ---
root = tk.Tk()
root.title(WINDOW_TITLE)
root.overrideredirect(True)
root.attributes("-topmost", True)
root.configure(bg=DARK_BG)

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
