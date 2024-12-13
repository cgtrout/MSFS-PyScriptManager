# fenix_radio.py: shows draggable radio panel on screen showing currently set radio channels on RMP1.  

import tkinter as tk
import json
import os
from time import sleep
from PIL import Image, ImageDraw, ImageFont, ImageTk
from simconnect_mobiflight.simconnect_mobiflight import SimConnectMobiFlight
from lib.extended_mobiflight_variable_requests import ExtendedMobiFlightVariableRequests  
import logging
from threading import Thread

# Set the SimConnect logging level to ERROR to suppress warnings
logging.getLogger("SimConnect.SimConnect").setLevel(logging.ERROR)

# Constants for RMP1 LVARs
RMP1_ACTIVE = "(L:N_PED_RMP1_ACTIVE)"
RMP1_STDBY = "(L:N_PED_RMP1_STDBY)"

# Settings for font and paths
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Settings", "fenix_radio.json")
FONT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Data", "Fonts", "digital-7.ttf")
initial_font_size = 40
font_increment = 1
min_font_size = 10
max_font_size = 100
font_size = initial_font_size

# Function to load settings from JSON file
def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        return {"font_size": initial_font_size, "position": {"x": 0, "y": 0}}
    with open(SETTINGS_FILE, "r") as file:
        return json.load(file)

# Function to save settings to JSON file
def save_settings(font_size, position):
    settings = {
        "font_size": font_size,
        "position": position
    }
    with open(SETTINGS_FILE, "w") as file:
        json.dump(settings, file)

# Function to create an image of LCD-style text with custom font and styling adjustments
def create_lcd_text_image(text, font_size, fg_color="#FFDDAA", bg_color="#0D0705", padding=15):
    if os.path.exists(FONT_PATH):
        try:
            font = ImageFont.truetype(FONT_PATH, font_size - 2)
        except IOError:
            print(f"Warning: Could not load custom font at {FONT_PATH}. Using default font.")
            font = ImageFont.load_default()
    else:
        print(f"Warning: Font file not found at {FONT_PATH}. Using default font.")
        font = ImageFont.load_default()

    text_bbox = font.getbbox(text)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1] + padding
    image = Image.new("RGB", (text_width + padding * 2, text_height + padding), color=bg_color)
    draw = ImageDraw.Draw(image)
    radius = 10
    draw.rounded_rectangle([(0, 0), (text_width + padding * 2, text_height + padding)], radius=radius, fill=bg_color)
    y_offset = padding // 2
    draw.text((padding, y_offset), text, font=font, fill=fg_color)
    
    return ImageTk.PhotoImage(image)

# Function to fetch and update frequency values for RMP1
def fetch_values(mf_requests, label_active_value, label_stby_value):
    while True:
        # Fetch the active and standby values for RMP1
        active_value_raw = mf_requests.get(RMP1_ACTIVE)
        standby_value_raw = mf_requests.get(RMP1_STDBY)

        # Format the values as frequencies
        active_value = f"{active_value_raw / 1000:.3f}"
        standby_value = f"{standby_value_raw / 1000:.3f}"

        # Update the labels with the new images
        active_image = create_lcd_text_image(active_value, font_size)
        standby_image = create_lcd_text_image(standby_value, font_size)
        label_active_value.config(image=active_image)
        label_active_value.image = active_image
        label_stby_value.config(image=standby_image)
        label_stby_value.image = standby_image

        # Delay before the next update
        sleep(1/60)

# Function to make the window draggable and save position on move
def make_draggable(widget):
    widget._drag_data = {'x': 0, 'y': 0}

    def start_move(event):
        widget._drag_data['x'] = event.x
        widget._drag_data['y'] = event.y

    def move_window(event):
        x = widget.winfo_x() + (event.x - widget._drag_data['x'])
        y = widget.winfo_y() + (event.y - widget._drag_data['y'])
        widget.geometry(f"+{x}+{y}")
        save_settings(font_size, {"x": x, "y": y})

    widget.bind("<Button-1>", start_move)
    widget.bind("<B1-Motion>", move_window)

# Function to handle resizing with the mouse wheel and apply to all components
def resize(event, window, labels):
    global font_size
    if event.delta > 0 and font_size < max_font_size:
        font_size += font_increment
    elif event.delta < 0 and font_size > min_font_size:
        font_size -= font_increment

    labels['label_active'].config(font=("Arial", int(font_size / 3), "bold"))
    labels['label_arrow'].config(font=("Arial", int(font_size / 3), "bold"))
    labels['label_stby'].config(font=("Arial", int(font_size / 3), "bold"))

    active_value = labels['label_active_value'].cget("text")
    standby_value = labels['label_stby_value'].cget("text")
    labels['label_active_value'].config(image=create_lcd_text_image(active_value, font_size))
    labels['label_stby_value'].config(image=create_lcd_text_image(standby_value, font_size))

    save_settings(font_size, {"x": window.winfo_x(), "y": window.winfo_y()})

# Main function to set up SimConnect and the GUI window
def main():
    global font_size

    settings = load_settings()
    font_size = settings.get("font_size", initial_font_size)
    position = settings.get("position", {"x": 0, "y": 0})

    # Initialize SimConnect and MobiFlightVariableRequests
    sm = SimConnectMobiFlight()
    mf_requests = ExtendedMobiFlightVariableRequests(sm, "fenix_radio")

    altitude = mf_requests.get("(A:PLANE ALTITUDE,Feet)")
    mf_requests.clear_sim_variables()

    # Set up the tkinter window
    window = tk.Tk()
    window.overrideredirect(True)
    window.configure(bg="black")
    window.attributes("-topmost", True)

    # Active and Standby labels to resemble panel style
    label_active = tk.Label(window, text="ACTIVE", fg="#FFD700", bg="black", font=("Arial", int(font_size / 3), "bold"))
    label_arrow = tk.Label(window, text="↔", fg="green", bg="black", font=("Arial", int(font_size / 3), "bold"))
    label_stby = tk.Label(window, text="STBY/CRS", fg="#FFD700", bg="black", font=("Arial", int(font_size / 3), "bold"))

    label_active_value = tk.Label(window, bg="black")
    label_stby_value = tk.Label(window, bg="black")

    # Arrange labels in grid to mimic the panel layout
    label_active.grid(row=0, column=0, padx=1, pady=1)
    label_active_value.grid(row=1, column=0, padx=1, pady=1)
    label_arrow.grid(row=1, column=1, padx=1, pady=1)
    label_stby.grid(row=0, column=2, padx=1, pady=1)
    label_stby_value.grid(row=1, column=2, padx=1, pady=1)

    labels = {
        'label_active': label_active,
        'label_active_value': label_active_value,
        'label_arrow': label_arrow,
        'label_stby': label_stby,
        'label_stby_value': label_stby_value
    }

    # Position the window based on saved position
    window.geometry(f"+{position['x']}+{position['y']}")
    make_draggable(window)

    # Bind mouse wheel for resizing and right-click for closing
    window.bind("<MouseWheel>", lambda event: resize(event, window, labels))
    window.bind("<Button-3>", lambda event: window.destroy())  # Right-click to close

    # Start a thread to continuously update values without blocking the GUI
    fetch_thread = Thread(target=fetch_values, args=(mf_requests, label_active_value, label_stby_value), daemon=True)
    fetch_thread.start()

    window.mainloop()

if __name__ == "__main__":
    main()
