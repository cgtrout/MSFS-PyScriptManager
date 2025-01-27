# plot_altitude: Creates a draggable graph window of altitude.  Designed to be easily modifiable.

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib import animation
import tkinter as tk
from SimConnect import SimConnect, AircraftRequests
import math
import matplotlib.ticker as mticker
from tkinter import filedialog
import csv

# User-Defined Parameters
alpha_transparency_level = 0.8  # Set transparency (0.0 = fully transparent, 1.0 = fully opaque)
lookup_key = "PLANE_ALTITUDE" # SimConnect variable https://docs.flightsimulator.com/html/Programming_Tools/SimVars/Simulation_Variables.htm
y_axis_label = "Altitude (ft)"
y_min = 0
y_max = 40000  # Update y-axis max to 40,000 feet
update_interval = 1000
recording_duration = 2 * 3600  # Desired recording duration in seconds (e.g., 2 hours)

# Automatically calculate max_data_points based on recording duration
max_data_points = (recording_duration * 1000) // update_interval

# Log approximate memory usage
memory_usage_mb = (max_data_points * 8) / (1024**2)  # 64-bit floats (8 bytes each)
print(f"Recording for {recording_duration} seconds at {update_interval}ms interval "
      f"requires {max_data_points} data points (~{memory_usage_mb:.2f} MB RAM)")

visible_data_points = 100  # Number of data points visible in the plot

# Configuration: Enable or disable sine wave data
enable_sine_wave_data = False

# Initialize data storage using NumPy
if enable_sine_wave_data:
    # Insert some sine wave data for testing (amplitude: 5000, frequency: 0.05)
    sine_wave_points = 200  # Number of points of sine wave to generate
    values = np.array([5000 * math.sin(0.05 * x) + 5000 for x in range(sine_wave_points)])
else:
    values = np.array([])

# Set x_offset to view the start initially
x_offset = 0
auto_scroll = True  # New: Automatically scroll to the right if set to True

# Initialize SimConnect
sm = None
aq = None
sim_connected = False
RECONNECT_INTERVAL = 5000
latest_value = 0  # Store the latest fetched value

def initialize_simconnect():
    global sm, aq, sim_connected
    try:
        sm = SimConnect()
        aq = AircraftRequests(sm)
        sim_connected = True
    except Exception:
        sim_connected = False
        root.after(RECONNECT_INTERVAL, initialize_simconnect)

# Fetch data from SimConnect
def get_data():
    global sim_connected
    if not sim_connected:
        return 0
    try:
        value = aq.get(lookup_key)
        return value if value is not None else 0
    except Exception:
        # Handle disconnection or other issues, try to reconnect
        sim_connected = False
        initialize_simconnect()
        return 0

def export_to_csv():
    # Ask user for file location to save CSV
    file_path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                                             title="Save as")
    if file_path:
        # Write the values to a CSV file
        with open(file_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["Index", "Altitude (ft)"])
            for index, value in enumerate(values):
                writer.writerow([index, value])
        print("Data exported successfully to:", file_path)

# Update function for the plot (fetch new data)
def update_plot(frame):
    global values, latest_value, x_offset, auto_scroll
    new_value = get_data()
    latest_value = new_value  # Store the latest value for display

    # Append new value to the NumPy array
    values = np.append(values, new_value)

    # Maintain maximum length to prevent the array from growing indefinitely
    if len(values) > max_data_points:
        values = values[-max_data_points:]

    # If auto-scrolling is enabled and we are currently at the right edge, adjust x_offset
    if auto_scroll:
        x_offset = max(0, len(values) - visible_data_points)

    # Refresh the plot with the updated data
    refresh_plot()

    # Update real-time text display with the latest data point (independent of scrolling)
    real_time_text.set_text(f"{latest_value:.2f} {y_axis_label}")

# Function to convert seconds to MM:SS format for x-axis labels
def format_seconds_to_minutes(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{int(minutes):02d}:{int(seconds):02d}"

# Function to refresh the plot with the current offset (scrolling through history)
def refresh_plot():
    global values, x_offset

    # Ensure x_offset is within the valid range
    x_offset = max(0, min(x_offset, len(values) - visible_data_points))

    # Extract the visible portion of data
    end_offset = min(x_offset + visible_data_points, len(values))
    visible_values = values[x_offset:end_offset]

    # Update both X and Y data explicitly
    time_step = update_interval / 1000  # Convert interval to seconds
    x_data = np.arange(x_offset, x_offset + len(visible_values)) * time_step  # Time values in seconds
    line.set_data(x_data, visible_values)  # Set both x and y data at once

    # Calculate start and end time for the visible range
    start_time = x_offset * time_step
    end_time = (x_offset + visible_data_points) * time_step

    ax.set_xlim(start_time, end_time)  # Set x-axis to reflect the current visible time range
    ax.set_ylim(y_min, y_max)

    # Set x-axis tick labels to MM:SS format
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: format_seconds_to_minutes(x)))

    # Redraw the canvas to show updated data
    canvas.draw()
    canvas.flush_events()

# Initialize Tkinter window without title bar
root = tk.Tk()
root.geometry("600x200")  # Initial window size
root.overrideredirect(1)  # Remove title bar
root.attributes("-topmost", True)
root.attributes("-alpha", alpha_transparency_level)  # Set window transparency

# Make the window draggable
def start_move(event):
    root.x = event.x
    root.y = event.y

def stop_move(event):
    root.x = None
    root.y = None

def on_motion(event):
    deltax = event.x - root.x
    deltay = event.y - root.y
    x = root.winfo_x() + deltax
    y = root.winfo_y() + deltay
    root.geometry(f"+{x}+{y}")

root.bind("<Button-1>", start_move)
root.bind("<ButtonRelease-1>", stop_move)
root.bind("<B1-Motion>", on_motion)

# Unified mouse wheel handler to handle both resizing and scrolling
def handle_mouse_wheel(event):
    global x_offset, auto_scroll
    if event.state & 0x4:  # Check if Ctrl key is pressed
        # Handle resizing
        scale_factor = 1.1 if event.delta > 0 else 0.9
        resize_plot(scale_factor)
    else:
        # Handle scrolling through data
        step = 10  # How much to scroll per wheel event
        if event.delta > 0:  # Scroll up (move left in data)
            x_offset = max(0, x_offset - step)
            auto_scroll = False  # Disable auto-scrolling when moving left
        else:  # Scroll down (move right in data)
            if x_offset + visible_data_points < len(values):
                x_offset = min(len(values) - visible_data_points, x_offset + step)
                if x_offset + visible_data_points >= len(values):
                    auto_scroll = True  # Enable auto-scrolling when at the rightmost end
            else:
                auto_scroll = True  # Enable auto-scroll if already at the end

        # Refresh the plot with the current offset (do not fetch new data)
        refresh_plot()

# Function to resize plot
def resize_plot(scale_factor=1.0):
    new_width = max(100, root.winfo_width() * scale_factor)
    new_height = max(100, root.winfo_height() * scale_factor)
    root.geometry(f"{int(new_width)}x{int(new_height)}")
    fig.set_size_inches(new_width / 100, new_height / 100)
    fig.tight_layout(pad=0.5)
    canvas.draw()

# Bind the mouse wheel to the handle_mouse_wheel function
root.bind("<MouseWheel>", handle_mouse_wheel)

# Set up matplotlib figure and axis using Figure (not plt.subplots)
fig = Figure(figsize=(6, 2), dpi=100)
ax = fig.add_subplot(111)
line, = ax.plot([], [], color='yellow', lw=1.5)  # Initialize with empty data

# Styling adjustments
ax.set_facecolor('#000000')
fig.patch.set_facecolor('#111111')
ax.set_xlim(0, visible_data_points - 1)
ax.set_ylim(y_min, y_max)
ax.spines['bottom'].set_color('gray')
ax.spines['top'].set_color('gray')
ax.spines['right'].set_color('gray')
ax.spines['left'].set_color('gray')
ax.tick_params(axis='x', colors='#FFFFFF')
ax.tick_params(axis='y', colors='#FFFFFF')
ax.margins(x=0.01, y=0.05)  # Reduces the margins around the plot area

# Real-time data value text (always displays the latest data point)
real_time_text = ax.text(0.95, 0.9, '', ha='right', va='center',
                         color='white', transform=ax.transAxes,
                         fontsize=10)

# Embed the plot in Tkinter window using FigureCanvasTkAgg
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# Create the context menu
context_menu = tk.Menu(root, tearoff=0)
context_menu.add_command(label="Export Data to CSV", command=export_to_csv)

# Right-click handler to display the context menu
def show_context_menu(event):
    context_menu.post(event.x_root, event.y_root)

# Bind right-click event to show the context menu
canvas.get_tk_widget().bind("<Button-3>", show_context_menu)

# Initial layout setup
fig.tight_layout(pad=0.5)
canvas.draw()

# Initialize SimConnect connection
initialize_simconnect()

# Set up animation to update the plot periodically
ani = animation.FuncAnimation(fig, update_plot, interval=update_interval, cache_frame_data=False)

# Run the Tkinter main loop
root.mainloop()

# Quit SimConnect when Tkinter loop ends
if sm:
    sm.quit()
