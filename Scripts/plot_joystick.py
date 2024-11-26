# plot_joystick: Show small plot window showing joystick axis position.
#  When ran will show a list of joysticks it detects.  Change "desired_joystick_name" below to the value you want to use.

# Desired joystick name
desired_joystick_name = "T.A320 Pilot"

# Set the desired graph size in pixels
graph_size_pixels = 100  # Change this to adjust the overall window size
alpha_transparency_level = 0.8 # Window transparency

import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from SimConnect import SimConnect, AircraftRequests
import threading
import tkinter as tk
import pygame

# Initialize pygame for joystick input
pygame.init()
pygame.joystick.init()

# Retrieve all connected joysticks
joysticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
joystick_names = [joystick.get_name() for joystick in joysticks]
joystick_count = pygame.joystick.get_count()

print("Showing list of detected joysticks:")

# Iterate over all detected joysticks and print their names
for i in range(joystick_count):
    joystick = pygame.joystick.Joystick(i)
    joystick.init()
    print(f"Joystick {i + 1}: {joystick.get_name()}")

# Check for desired joystick and select it if available
selected_joystick = None
if desired_joystick_name in joystick_names:
    selected_joystick = joysticks[joystick_names.index(desired_joystick_name)]
    selected_joystick.init()
    print(f"Joystick '{desired_joystick_name}' selected for visualization.")
else:
    print(f"No joystick found with the name '{desired_joystick_name}'. Exiting.")
    pygame.quit()
    exit()

# Function to initialize SimConnect and AircraftRequests
def initialize_simconnect():
    try:
        sm = SimConnect()
        aq = AircraftRequests(sm)
        print("Connected to SimConnect.")
        return sm, aq
    except Exception as e:
        print(f"SimConnect initialization failed: {e}")
        return None, None

sm, aq = initialize_simconnect()

# Calculate the size in inches for matplotlib (assuming 100 DPI)
graph_size_inches = graph_size_pixels / 100

# Create the main tkinter window with the specified size
root = tk.Tk()
root.geometry(f"{graph_size_pixels}x{graph_size_pixels}+{0}+{40}")  # Use the size variable for both dimensions
root.overrideredirect(1)  # Frameless window
root.attributes("-topmost", True)  # Keep it on top
root.attributes("-alpha", alpha_transparency_level)  # Set window transparency

# Add functionality to make the window draggable
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

# Bind mouse events for dragging
root.bind("<Button-1>", start_move)
root.bind("<ButtonRelease-1>", stop_move)
root.bind("<B1-Motion>", on_motion)

# Create a matplotlib figure and axis using the calculated size
fig, ax = plt.subplots(figsize=(graph_size_inches, graph_size_inches))
fig.patch.set_facecolor('#111111')  # Dark background for the figure
ax.set_facecolor('#000000')  # Dark background for the plot
scat = ax.scatter([], [], s=20, color="yellow")  # Marker for the joystick dot

# Tighten layout and remove any excess border space
fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
ax.set_xlim(-1.01, 1.01)
ax.set_ylim(-1.01, 1.01)
ax.axis('off')  # Remove all ticks, labels, and spines

# Draw crosshairs at the center of the plot
ax.axhline(0, color='darkgray', lw=0.7)
ax.axvline(0, color='darkgray', lw=0.7)

# Add trim markers with custom colors and transparency
elevator_trim_marker = ax.axhline(0, color=(0.1, 0.5, 0.9, 0.6) , lw=0.8, linestyle='--', label="Pitch Trim (Elevator)")
aileron_trim_marker = ax.axvline(0, color=(0.5, 0.1, 0.3, 0.8), lw=0.8, linestyle='--', label="Roll Trim (Aileron)")

# Global variable for reconnection cooldown
reconnect_cooldown = 0  # Number of frames to wait before retrying

threshold = 0.01
query_interval = 20  # Query SimConnect every n frames
frame_counter = 0  # Frame counter to track updates

cached_trim_values = {
    "elevator_trim": 0,
    "aileron_trim": 0,
    "rotor_lateral_trim": 0,
    "rotor_longitudinal_trim": 0,
}

# Lock for thread safety
cache_lock = threading.Lock()

def fetch_trim_data():
    """Fetch trim data asynchronously from SimConnect."""
    global sm, aq, cached_trim_values
    if sm and aq:
        try:
            # Fetch data
            elevator_trim = aq.find("ELEVATOR_TRIM_PCT").value or 0
            aileron_trim = aq.find("AILERON_TRIM_PCT").value or 0
            rotor_lateral_trim = aq.find("ROTOR_LATERAL_TRIM_PCT").value or 0
            rotor_longitudinal_trim = aq.find("ROTOR_LONGITUDINAL_TRIM_PCT").value or 0

            # Safely update the cache
            with cache_lock:
                cached_trim_values["elevator_trim"] = elevator_trim
                cached_trim_values["aileron_trim"] = aileron_trim
                cached_trim_values["rotor_lateral_trim"] = rotor_lateral_trim
                cached_trim_values["rotor_longitudinal_trim"] = rotor_longitudinal_trim
        except Exception as e:
            print(f"[ERROR] SimConnect query failed: {e}")
            sm, aq = None, None  # Reset connection on failure

def update(frame):
    global sm, aq, reconnect_cooldown, cached_trim_values

    # Ensure joystick input is processed
    pygame.event.pump()

    # Initialize joystick variables
    try:
        x = selected_joystick.get_axis(0)
        y = selected_joystick.get_axis(1)
    except Exception as e:
        print(f"[ERROR] Failed to read joystick axes: {e}")
        x, y = 0, 0  # Default to zero if joystick input fails

    scat.set_offsets([[x, y]])  # Update the scatter plot position

    # Start a new thread every 10 frames to fetch data
    if frame % 10 == 0:
        threading.Thread(target=fetch_trim_data).start()

    # Use cached values for graph and text display
    with cache_lock:
        elevator_trim = cached_trim_values.get("elevator_trim", 0)
        aileron_trim = cached_trim_values.get("aileron_trim", 0)
        rotor_lateral_trim = cached_trim_values.get("rotor_lateral_trim", 0)
        rotor_longitudinal_trim = cached_trim_values.get("rotor_longitudinal_trim", 0)

    # Determine mode (helicopter or airplane) based on trim values
    is_helicopter = (
        abs(rotor_lateral_trim) > threshold or abs(rotor_longitudinal_trim) > threshold
    )

    # Update visualization based on detected mode
    if is_helicopter:
        # Helicopter mode: Show rotor trim
        elevator_trim_marker.set_ydata([rotor_longitudinal_trim] * 2)
        elevator_trim_marker.set_xdata([-1.01, 1.01])  # Full graph width
        elevator_trim_marker.set_visible(abs(rotor_longitudinal_trim) > threshold)

        aileron_trim_marker.set_xdata([rotor_lateral_trim] * 2)
        aileron_trim_marker.set_ydata([-1.01, 1.01])  # Full graph height
        aileron_trim_marker.set_visible(abs(rotor_lateral_trim) > threshold)

    else:
        # Airplane mode: Show elevator and aileron trim
        elevator_trim_marker.set_ydata([elevator_trim] * 2)
        elevator_trim_marker.set_xdata([-1.01, 1.01])  # Full graph width
        elevator_trim_marker.set_visible(abs(elevator_trim) > threshold)

        aileron_trim_marker.set_xdata([aileron_trim] * 2)
        aileron_trim_marker.set_ydata([-1.01, 1.01])  # Full graph height
        aileron_trim_marker.set_visible(abs(aileron_trim) > threshold)

    # Update text display
    coord_text.set_text(
        f"X: {x:>5.2f} Y: {y:>5.2f}"
    )

    return scat, coord_text, elevator_trim_marker, aileron_trim_marker

# Embed the plot in the tkinter window and ensure it draws correctly
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# Add text for coordinates in the bottom right corner
coord_text = ax.text(0.9, -0.9, '', ha='right', va='bottom',
                     fontsize=8, color='darkgray', transform=ax.transData)

# Run the animation with the update function
ani = animation.FuncAnimation(fig, update, interval=50, blit=True, cache_frame_data=False)

# Run the tkinter main loop to show the window
root.mainloop()

# Quit pygame once the tkinter loop ends
pygame.quit()
