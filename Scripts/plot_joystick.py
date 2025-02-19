# plot_joystick - shows a plot of joystick state - right click to bring up menu

import os
import json
import sys
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from SimConnect import SimConnect, AircraftRequests
import threading
import tkinter as tk

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
import pygame
import time

try:
    # Import all color print functions
    from Lib.color_print import *
    from Lib.dark_mode import DarkmodeUtils
    from Lib.gc_tweak import optimize_gc
except ImportError:
    print("Failed to import 'Lib' directory. Please ensure Lib/* is present")
    sys.exit(1)

class JoystickApp:
    def __init__(self, graph_size_pixels, alpha_transparency_level, settings_file):
        # Initialize constants and state
        self.graph_size_pixels = graph_size_pixels
        self.graph_size_inches = graph_size_pixels / 100
        self.alpha_transparency_level = alpha_transparency_level
        self.settings_file = settings_file

        self.TRIM_COLOR = '#444444'

        self.sm = None
        self.aq = None
        self.selected_joystick = None
        self.joystick_names = []
        self.joysticks = []
        self.trim_update_interval = 0.5
        self.cached_trim_values = {
            "elevator_trim": 0,
            "aileron_trim": 0,
            "rotor_lateral_trim": 0,
            "rotor_longitudinal_trim": 0,
        }
        self.cache_lock = threading.Lock()
        self.scat = None
        self.elevator_trim_marker = None
        self.aileron_trim_marker = None
        self.coord_text = None

        self.root = None
        self.menu = None
        self.fig, self.ax = None, None

        self.last_joystick_pos = (0,0)

        # Load settings
        self.desired_joystick_name, self.window_position = self._load_settings()

        # Initialize pygame for joystick handling
        pygame.init()
        pygame.joystick.init()

        # Load and configure joysticks
        self._load_joysticks()

        optimize_gc()

    def _load_joysticks(self):
        """Load joystick information and initialize the desired joystick."""
        # Get joystick info
        self.joysticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
        self.joystick_names = [joystick.get_name() for joystick in self.joysticks]

        # Use the desired joystick name already loaded
        if self.desired_joystick_name in self.joystick_names:
            self.selected_joystick = self.joysticks[self.joystick_names.index(self.desired_joystick_name)]
            self.selected_joystick.init()
            print_info(f"Joystick '{self.desired_joystick_name}' loaded from settings and initialized.")
        else:
            print_warning(f"Saved joystick '{self.desired_joystick_name}' not found. No joystick selected.")

    def _save_settings(self, joystick_name=None, position=None):
        """Save settings like joystick name and window position."""
        settings = {}
        try:
            with open(self.settings_file, "r") as f:
                settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # If settings file doesn't exist or is invalid, start fresh

        if joystick_name:
            settings["desired_joystick_name"] = joystick_name
        if position:
            settings["window_position"] = position

        with open(self.settings_file, "w") as f:
            json.dump(settings, f)

    def _load_settings(self):
        """Load settings like joystick name and window position."""
        try:
            with open(self.settings_file, "r") as f:
                data = json.load(f)
                return data.get("desired_joystick_name", ""), data.get("window_position", "+0+40")
        except (FileNotFoundError, json.JSONDecodeError):
            return "", "+0+40"

    def _retry_simconnect(self, retry_interval=1000 * 60):
        """Schedule a retry of SimConnect initialization."""
        print_info(f"Scheduling SimConnect reconnection in {retry_interval // 1000} seconds.")
        self.root.after(retry_interval, self._initialize_simconnect)

    def _initialize_simconnect(self):
        """Attempt to initialize SimConnect."""
        try:
            self.sm = SimConnect()
            self.aq = AircraftRequests(self.sm)
            print_info("Connected to SimConnect.")
        except Exception as e:
            print_error(f"SimConnect initialization failed: {e}")
            self.sm = None
            self.aq = None
            self._retry_simconnect()

    def _fetch_trim_data(self):
        """Fetch trim data in a background thread."""
        while True:
            if self.sm and self.aq:
                try:
                    # Fetch data
                    elevator_trim = self.aq.find("ELEVATOR_TRIM_PCT").value or 0
                    aileron_trim = self.aq.find("AILERON_TRIM_PCT").value or 0
                    rotor_lateral_trim = self.aq.find("ROTOR_LATERAL_TRIM_PCT").value or 0
                    rotor_longitudinal_trim = self.aq.find("ROTOR_LONGITUDINAL_TRIM_PCT").value or 0

                    # Safely update the cache
                    with self.cache_lock:
                        self.cached_trim_values["elevator_trim"] = elevator_trim
                        self.cached_trim_values["aileron_trim"] = aileron_trim
                        self.cached_trim_values["rotor_lateral_trim"] = rotor_lateral_trim
                        self.cached_trim_values["rotor_longitudinal_trim"] = rotor_longitudinal_trim

                except Exception as e:
                    print_error(f"SimConnect query failed: {e}")
                    self.sm = None
                    self.aq = None
                    # Trigger reconnection
                    wait_interval = 60
                    self.root.after(0, lambda: self._retry_simconnect(retry_interval=wait_interval * 1000))
                    time.sleep(wait_interval+0.1)  # Sleep for the retry interval
            time.sleep(self.trim_update_interval)

    def _update_plot(self, frame):
        try:
            if self.selected_joystick:
                pygame.event.pump()
                x = self.selected_joystick.get_axis(0)
                y = self.selected_joystick.get_axis(1)
            else:
                x, y = 0, 0
                self.coord_text.set_text("No Joy!\nRight-click to \nselect")
                return self.scat, self.coord_text

            self.scat.set_offsets([[x, y]])

            # Cache previous joystick position to avoid redundant updates
            if (x, y) != getattr(self, "last_joystick_pos", (None, None)):
                self.scat.set_offsets([[x, y]])
                self.last_joystick_pos = (x, y)

            # Get current trim values
            with self.cache_lock:
                elevator_trim = self.cached_trim_values.get("elevator_trim", 0)
                aileron_trim = self.cached_trim_values.get("aileron_trim", 0)
                rotor_lateral_trim = self.cached_trim_values.get("rotor_lateral_trim", 0)
                rotor_longitudinal_trim = self.cached_trim_values.get("rotor_longitudinal_trim", 0)

            # Determine mode (helicopter or airplane) based on trim values
            threshold = 0.01
            is_helicopter = (
                abs(rotor_lateral_trim) > threshold or abs(rotor_longitudinal_trim) > threshold
            )

            updated_elements = [self.scat]

            # Update visualization based on mode
            if is_helicopter:
                # Helicopter Mode - Update only if values change
                if getattr(self, "last_rotor_longitudinal_trim", None) != rotor_longitudinal_trim:
                    self.elevator_trim_marker.set_ydata([rotor_longitudinal_trim] * 2)
                    self.last_rotor_longitudinal_trim = rotor_longitudinal_trim
                    updated_elements.append(self.elevator_trim_marker)

                if getattr(self, "last_rotor_lateral_trim", None) != rotor_lateral_trim:
                    self.aileron_trim_marker.set_xdata([rotor_lateral_trim] * 2)
                    self.last_rotor_lateral_trim = rotor_lateral_trim
                    updated_elements.append(self.aileron_trim_marker)
            else:
                # Airplane Mode - Update only if values change
                if getattr(self, "last_elevator_trim", None) != elevator_trim:
                    self.elevator_trim_marker.set_ydata([elevator_trim] * 2)
                    self.last_elevator_trim = elevator_trim
                    updated_elements.append(self.elevator_trim_marker)

                if getattr(self, "last_aileron_trim", None) != aileron_trim:
                    self.aileron_trim_marker.set_xdata([aileron_trim] * 2)
                    self.last_aileron_trim = aileron_trim
                    updated_elements.append(self.aileron_trim_marker)

            # Ensure visibility updates only when necessary
            def update_visibility(marker, condition):
                if marker.get_visible() != condition:
                    marker.set_visible(condition)
                    updated_elements.append(marker)

            update_visibility(self.elevator_trim_marker, is_helicopter and abs(rotor_longitudinal_trim) > threshold)
            update_visibility(self.aileron_trim_marker, is_helicopter and abs(rotor_lateral_trim) > threshold)

            # Update coordinates display only when joystick position changes
            new_coord_text = f"X: {x:>5.2f} Y: {y:>5.2f}"
            if self.coord_text.get_text() != new_coord_text:
             self.coord_text.set_text(new_coord_text)

            return updated_elements  # Return only updated elements

        except Exception as e:
            print_error(f"Joystick read failed: {e}")
            return self.scat, self.coord_text

    def _create_gui(self):
        self.root = tk.Tk()
        self.root.geometry(f"{self.graph_size_pixels}x{self.graph_size_pixels}{self.window_position}")
        self.root.overrideredirect(1)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.alpha_transparency_level)

        self.root.bind("<Button-1>", self._start_drag)
        self.root.bind("<ButtonRelease-1>", self._stop_drag)
        self.root.bind("<B1-Motion>", self._on_drag)

        self.menu = tk.Menu(self.root, tearoff=0, bg="#333333", fg="white", activebackground="#555555", activeforeground="white")
        self.root.bind("<Button-3>", self._show_context_menu)

        self.fig, self.ax = plt.subplots(figsize=(self.graph_size_inches, self.graph_size_inches))
        self._apply_plot_layout_adjustments()

        self.scat = self.ax.scatter([], [], s=20, color="yellow")
        self.ax.set_xlim(-1.01, 1.01)
        self.ax.set_ylim(-1.01, 1.01)

        self.ax.axhline(0, color='darkgray', lw=0.7)
        self.ax.axvline(0, color='darkgray', lw=0.7)

        self.elevator_trim_marker = self.ax.axhline(0, color=self.TRIM_COLOR, lw=0.8, linestyle='--', visible=False)
        self.aileron_trim_marker = self.ax.axvline(0, color=self.TRIM_COLOR, lw=0.8, linestyle='--', visible=False)
        self.coord_text = self.ax.text(0.9, -0.9, '', ha='right', va='bottom', fontsize=8, color='darkgray', transform=self.ax.transData)

        canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _apply_plot_layout_adjustments(self):
        """Ensure consistent layout settings for the plot."""
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)  # Remove extra padding
        self.fig.patch.set_facecolor('#111111')  # Background for the figure
        self.ax.set_facecolor('#000000')  # Background for the plot
        self.ax.axis('off')  # Hide axes

    def run(self):
        self._create_gui()
        self._initialize_simconnect()
        trim_thread = threading.Thread(target=self._fetch_trim_data, daemon=True)
        trim_thread.start()
        ani = animation.FuncAnimation(self.fig, self._update_plot,
                                      interval=50, blit=True, cache_frame_data=False)
        self.root.mainloop()
        pygame.quit()

    def _start_drag(self, event):
        self.root.x = event.x
        self.root.y = event.y

    def _stop_drag(self, event):
        """Stop dragging the window and save its position."""
        self.root.x = None
        self.root.y = None

        # Save the current window position
        position = f"+{self.root.winfo_x()}+{self.root.winfo_y()}"
        self._save_settings(position=position)
        print_info(f"Window position saved: {position}")

    def _on_drag(self, event):
        deltax = event.x - self.root.x
        deltay = event.y - self.root.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def _show_context_menu(self, event):
        """Show a context menu for joystick selection."""
        self.menu.delete(0, tk.END)  # Clear previous menu items
        for idx, name in enumerate(self.joystick_names):
            self.menu.add_command(label=name, command=lambda n=name: self._handle_joystick_selection(n))
        self.menu.tk_popup(event.x_root, event.y_root)

    def _handle_joystick_selection(self, name):
        """Handle joystick selection from the context menu."""
        self.desired_joystick_name = name
        self._save_settings(name)
        self._load_joysticks()  # Refresh joysticks and reinitialize selected joystick
        self._apply_plot_layout_adjustments()  # Ensure consistent plot layout

        print_info(f"Joystick '{name}' saved and reloaded.")

if __name__ == "__main__":
    # Get the directory one level up from the current script's directory
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Define the Settings directory and settings file path
    SETTINGS_DIR = os.path.join(BASE_DIR, "Settings")
    SETTINGS_FILE = os.path.join(SETTINGS_DIR, "plot_joystick.json")

    app = JoystickApp(graph_size_pixels=100, alpha_transparency_level=0.8, settings_file=SETTINGS_FILE)
    app.run()
