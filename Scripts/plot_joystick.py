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

# Update function for the scatter plot to follow joystick movements
def update(frame):
    pygame.event.pump()
    x = selected_joystick.get_axis(0)
    y = selected_joystick.get_axis(1)
    scat.set_offsets([[x, y]])
    
    # Update the text with the new coordinates
    coord_text.set_text(f"X: {x:>5.2f} Y: {y:>5.2f}")
    
    return scat, coord_text

# Embed the plot in the tkinter window and ensure it draws correctly
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# Add text for coordinates in the bottom right corner
coord_text = ax.text(0.9, -0.9, '', ha='right', va='bottom',
                     fontsize=8, color='darkgray', transform=ax.transData)

# Run the animation with the update function
ani = animation.FuncAnimation(fig, update, interval=50, blit=False)

# Run the tkinter main loop to show the window
root.mainloop()

# Quit pygame once the tkinter loop ends
pygame.quit()
