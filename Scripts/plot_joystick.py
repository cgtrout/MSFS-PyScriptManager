# plot_joystick - shows a plot of joystick state - right click to bring up menu

import os
import json
import sys
import logging
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import tkinter as tk

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
import pygame
import time
import math

TEST_MODE = False # Runs with test data rather than live joy data

try:
    # Import all color print functions
    from Lib.color_print import *
    from Lib.dark_mode import DarkmodeUtils
    from Lib.gc_tweak import optimize_gc
    from Lib.connection_helpers import SimConnectConnectionHelper
    from Lib.sim_state import SimStateDetector
    from Lib.sim_process import is_sim_running
    from SimConnect import SimConnect, AircraftRequests
except ImportError:
    print("Failed to import 'Lib' directory. Please ensure Lib/* is present")
    sys.exit(1)

# Reduce noise from Python-SimConnect internals (request definition spam).
logging.getLogger("SimConnect").setLevel(logging.CRITICAL)
logging.getLogger("SimConnect.SimConnect").setLevel(logging.CRITICAL)
logging.getLogger("SimConnect.RequestList").setLevel(logging.CRITICAL)
logging.getLogger("SimConnect.Constants").setLevel(logging.CRITICAL)

class JoystickApp:
    # ========================================================================
    # LIFECYCLE
    # ========================================================================

    def __init__(self, graph_size_pixels, alpha_transparency_level, settings_file, test_mode=False):
        # Initialize constants and state
        self.test_mode = test_mode
        self.graph_size_pixels = graph_size_pixels
        self.graph_size_inches = graph_size_pixels / 100
        self.alpha_transparency_level = alpha_transparency_level
        self.settings_file = settings_file

        self.TRIM_COLOR = '#444444'

        self.sm = None
        self.aq = None
        self.sim_state_detector = None
        self.conn = SimConnectConnectionHelper(retry_delay=30)
        self.sim_process_min_runtime = 10
        self.last_simconnect_attempt = 0.0
        self.selected_joystick = None
        self.joystick_names = []
        self.joysticks = []
        self.rudder_joystick = None
        self.rudder_joystick_name = None
        self.rudder_axis_id = None
        self.show_values = False
        self.trim_update_interval = 0.05
        self.sim_running_check_interval = 2.0
        self.last_sim_running_check = 0.0
        self.cached_sim_running = False
        # Used to cache values from
        self.cached_trim_values = {
            "elevator_trim": 0,
            "aileron_trim": 0,
            "rotor_lateral_trim": 0,
            "rotor_longitudinal_trim": 0,
        }

        # Used for comparison to prevent redraws
        self.last_trim_values = {
            "elevator_trim": 0.0,
            "aileron_trim": 0.0,
            "rotor_lateral_trim": 0.0,
            "rotor_longitudinal_trim": 0.0,
        }

        self.cache_lock = threading.Lock()
        self.dot = None
        self.elevator_trim_marker = None
        self.aileron_trim_marker = None
        self.rudder_marker = None
        self.coord_label = None
        self.sim_status_label = None
        self._sim_status_shown = False

        self.root = None
        self.menu = None
        self.fig, self.ax = None, None

        self.last_joystick_pos = None
        self.last_rudder_value = "unset"

        # Load settings
        (
            self.desired_joystick_name,
            self.window_position,
            self.rudder_joystick_name,
            self.rudder_axis_id,
            self.show_values,
        ) = self._load_settings()

        # Initialize pygame for joystick handling
        if not self.test_mode:
            pygame.init()
            pygame.joystick.init()
            self._load_joysticks()

        optimize_gc(allocs=5000, gen1_factor=5, gen2_factor=5, freeze=False, show_data=False)

    def run(self):
        self._create_gui()
        if not self.test_mode:
            # Trim thread handles SimConnect connection + retries in the background
            trim_thread = threading.Thread(target=self._fetch_trim_data, daemon=True)
            trim_thread.start()
        self.root.after(50, self._update_plot)
        self.root.mainloop()
        if not self.test_mode:
            pygame.quit()

    # ========================================================================
    # SETTINGS MANAGEMENT
    # ========================================================================

    def _load_settings(self):
        """Load settings like joystick name and window position."""
        try:
            with open(self.settings_file, "r") as f:
                data = json.load(f)
                rudder_joystick_name = data.get("rudder_joystick_name", None)
                if not isinstance(rudder_joystick_name, str) or not rudder_joystick_name.strip():
                    rudder_joystick_name = None
                rudder_axis_id = data.get("rudder_axis_id", None)
                if not isinstance(rudder_axis_id, int):
                    rudder_axis_id = None
                show_values = data.get("show_values", False)
                if not isinstance(show_values, bool):
                    show_values = False
                return (
                    data.get("desired_joystick_name", ""),
                    data.get("window_position", "+0+40"),
                    rudder_joystick_name,
                    rudder_axis_id,
                    show_values,
                )
        except (FileNotFoundError, json.JSONDecodeError):
            return "", "+0+40", None, None, False

    def _save_settings(
        self,
        joystick_name=None,
        position=None,
        rudder_joystick_name="__KEEP__",
        rudder_axis_id="__KEEP__",
        show_values="__KEEP__",
    ):
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
        if rudder_joystick_name != "__KEEP__":
            settings["rudder_joystick_name"] = rudder_joystick_name
        if rudder_axis_id != "__KEEP__":
            settings["rudder_axis_id"] = rudder_axis_id
        if show_values != "__KEEP__":
            settings["show_values"] = bool(show_values)

        with open(self.settings_file, "w") as f:
            json.dump(settings, f)

    # ========================================================================
    # JOYSTICK MANAGEMENT
    # ========================================================================

    def _load_joysticks(self):
        """Load joystick information and initialize the desired joystick."""
        # Get joystick info
        self.joysticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
        self.joystick_names = [joystick.get_name() for joystick in self.joysticks]

        # Use the desired joystick name already loaded
        if self.desired_joystick_name in self.joystick_names:
            self.selected_joystick = self.joysticks[self.joystick_names.index(self.desired_joystick_name)]
            print_info(f"Joystick '{self.desired_joystick_name}' loaded from settings and initialized.")
        else:
            print_warning(f"Saved joystick '{self.desired_joystick_name}' not found. No joystick selected.")

        self.rudder_joystick = self._get_joystick_by_name(self.rudder_joystick_name)
        self._validate_rudder_binding()

    def _get_joystick_by_name(self, joystick_name):
        if not joystick_name:
            return None
        if joystick_name not in self.joystick_names:
            return None
        return self.joysticks[self.joystick_names.index(joystick_name)]

    def _axis_in_range(self, joystick, axis_id):
        if joystick is None or axis_id is None:
            return False
        return 0 <= axis_id < joystick.get_numaxes()

    def _validate_rudder_binding(self):
        if self.rudder_joystick_name and self.rudder_joystick is None:
            print_warning(f"Rudder device '{self.rudder_joystick_name}' not found. Clearing rudder binding.")
            self.rudder_joystick_name = None
            self.rudder_axis_id = None
            self._save_settings(rudder_joystick_name=None, rudder_axis_id=None)
            return

        if self.rudder_axis_id is None:
            return

        if not self._axis_in_range(self.rudder_joystick, self.rudder_axis_id):
            device_name = self.rudder_joystick_name or "<none>"
            print_warning(f"Rudder axis {self.rudder_axis_id} is not valid for device '{device_name}'. Clearing axis.")
            self.rudder_axis_id = None
            self._save_settings(rudder_axis_id=None)

    # ========================================================================
    # SIMCONNECT MANAGEMENT
    # ========================================================================

    def _initialize_simconnect(self):
        """Try to connect to SimConnect directly (no subprocess process-check)."""
        self.last_simconnect_attempt = time.monotonic()
        try:
            self.conn.sm = SimConnect()
            self.conn.aq = AircraftRequests(
                self.conn.sm,
                _time=self.conn.request_time,
                _attemps=self.conn.request_attempts,
            )
            self.sm = self.conn.sm
            self.aq = self.conn.aq
            self.patch_rotor_trim(self.aq)
            self.sim_state_detector = SimStateDetector(self.sm)
            print_info("Connected to SimConnect.")
            return True
        except Exception:
            self.conn.sm = None
            self.conn.aq = None
            self.sim_state_detector = None
            return False

    def _disconnect_sim(self):
        """Disconnect from SimConnect and reset state."""
        self.conn.disconnect()
        self.sm = None
        self.aq = None
        self.sim_state_detector = None

    def patch_rotor_trim(self, aq):
        """
        Adds missing ROTOR_LATERAL_TRIM_PCT to the existing AircraftRequests instance.
        """
        # Find the helicopter helper inside aq.list
        heli = next((h for h in aq.list if h.__class__.__name__.endswith("_HelicopterSpecificData")), None)
        if heli is None:
            raise RuntimeError("Could not find _HelicopterSpecificData inside aq.list")

        if not isinstance(heli.list, dict):
            raise RuntimeError(f"Expected heli.list to be dict, got {type(heli.list)}")

        heli.list["ROTOR_LATERAL_TRIM_PCT"] = [
            "Trim percent",
            b"ROTOR LATERAL TRIM PCT",
            b"Percent Over 100",
            "N",
        ]
        heli.list["ROTOR_LONGITUDINAL_TRIM_PCT"] = [
            "Trim percent",
            b"ROTOR LONGITUDINAL TRIM PCT",
            b"Percent Over 100",
            "N",
        ]

        # Clear helper cache if present
        #if hasattr(heli, "dic") and hasattr(heli.dic, "clear"):
        #    heli.dic.clear()

        print_debug(f"[patch] heli helper type={type(heli)}")
        print_debug(f"[patch] added key='ROTOR_LATERAL_TRIM_PCT'")
        print_debug(f"[patch] now_has_lateral={'ROTOR_LATERAL_TRIM_PCT' in heli.list}")
        print_debug(f"[patch] lateral_def={heli.list['ROTOR_LATERAL_TRIM_PCT']}")

    def _ensure_connected(self):
        """Check sim process and attempt SimConnect connection. Returns True if connected."""
        if self.sm and self.aq:
            return True

        now = time.monotonic()
        if (now - self.last_sim_running_check) >= self.sim_running_check_interval:
            self.cached_sim_running = is_sim_running(min_runtime=self.sim_process_min_runtime)
            self.last_sim_running_check = now

        if not self.cached_sim_running:
            return False

        if (now - self.last_simconnect_attempt) >= self.conn.retry_delay:
            self._initialize_simconnect()

        return bool(self.sm and self.aq)

    # ========================================================================
    # TRIM DATA (BACKGROUND THREAD)
    # ========================================================================

    def _fetch_trim_data(self):
        """Fetch trim data in a background thread."""
        while True:
            time.sleep(self.trim_update_interval)

            if not self._ensure_connected():
                continue

            try:
                camera_state = self.sim_state_detector.get_camera_state()
                in_flight = camera_state is not None and camera_state in self.sim_state_detector.FLIGHT_CAMERA_STATES

                if not in_flight:
                    print_debug(f"Not in flight (camera state: {camera_state})")
                    self._reset_trim_cache()
                    continue

                print_debug(f"Fetching trim data (camera state: {camera_state})")
                self._poll_trim_values()

            except Exception as e:
                print_error(f"SimConnect query failed: {e}")
                self._disconnect_sim()

    def _poll_trim_values(self):
        """Fetch current trim values from SimConnect and update the cache."""
        elevator_trim = self.conn.get("ELEVATOR_TRIM_PCT") or 0
        aileron_trim = self.conn.get("AILERON_TRIM_PCT") or 0
        rotor_lateral_trim = self.conn.get("ROTOR_LATERAL_TRIM_PCT") or 0
        rotor_longitudinal_trim = self.conn.get("ROTOR_LONGITUDINAL_TRIM_PCT") or 0

        with self.cache_lock:
            self.cached_trim_values["elevator_trim"] = elevator_trim
            self.cached_trim_values["aileron_trim"] = aileron_trim
            self.cached_trim_values["rotor_lateral_trim"] = rotor_lateral_trim
            self.cached_trim_values["rotor_longitudinal_trim"] = rotor_longitudinal_trim

    def _reset_trim_cache(self):
        """Reset all trim values to zero."""
        with self.cache_lock:
            for key in self.cached_trim_values:
                self.cached_trim_values[key] = 0

    # ========================================================================
    # PLOT UPDATE LOOP
    # ========================================================================

    def _update_plot(self):
        self._update_sim_status_indicator()
        self._ensure_static_background()

        input_data = self._read_input()
        if input_data is None:
            self._show_no_joystick_warning()
            return

        new_x, new_y, new_rudder = input_data
        new_trim_values = self._read_trim_values()

        # Skip artist updates if nothing changed, but re-blit in case Tk cleared the canvas
        if (new_x, new_y) == self.last_joystick_pos and new_trim_values == self.last_trim_values and new_rudder == self.last_rudder_value:
            self.fig.canvas.blit(self.fig.bbox)
            self.root.after(50, self._update_plot)
            return

        self.last_joystick_pos = (new_x, new_y)
        self.last_trim_values = new_trim_values.copy()
        self.last_rudder_value = new_rudder

        self._update_artists(new_x, new_y, new_trim_values, new_rudder)
        self._blit()
        self.root.after(50, self._update_plot)

    def _update_sim_status_indicator(self):
        """Show or hide the 'No SIM' label based on connection state."""
        sim_connected = bool(self.sm and self.aq)
        if sim_connected and self._sim_status_shown:
            self.sim_status_label.place_forget()
            self._sim_status_shown = False
        elif not sim_connected and not self._sim_status_shown:
            self.sim_status_label.config(text="No SIM")
            self.sim_status_label.place(relx=0.0, rely=1.0, x=2, y=-2, anchor='sw')
            self._sim_status_shown = True

    def _ensure_static_background(self):
        """Capture the static background once for manual blitting."""
        if not hasattr(self, 'static_background'):
            self.fig.canvas.draw()
            self.static_background = self.fig.canvas.copy_from_bbox(self.fig.bbox)

    def _read_input(self):
        """Read joystick position and rudder. Returns (x, y, rudder) or None if no joystick."""
        if self.test_mode:
            t = time.time()
            return math.sin(t * 0.5), math.sin(t * 0.7), math.sin(t * 0.9)
        if self.selected_joystick:
            pygame.event.pump()
            x = self.selected_joystick.get_axis(0)
            y = self.selected_joystick.get_axis(1)
            if self._axis_in_range(self.rudder_joystick, self.rudder_axis_id):
                rudder = self.rudder_joystick.get_axis(self.rudder_axis_id)
            else:
                rudder = None
            return x, y, rudder
        return None

    def _show_no_joystick_warning(self):
        """Display 'No Joy' warning and schedule next update."""
        self.coord_label.config(text="No Joy!\nRight-click\nto select")
        self.coord_label.place(relx=1.0, rely=1.0, x=-2, y=-2, anchor='se')
        self.fig.canvas.blit(self.fig.bbox)
        self.root.after(100, self._update_plot)

    def _read_trim_values(self):
        """Read trim values from test data or SimConnect cache."""
        if self.test_mode:
            t = time.time()
            return {
                "elevator_trim": 0.3 + 0.2 * math.sin(t * 0.3),
                "aileron_trim": -0.2 + 0.15 * math.sin(t * 0.4),
                "rotor_lateral_trim": 0,
                "rotor_longitudinal_trim": 0,
            }
        with self.cache_lock:
            return self.cached_trim_values.copy()

    def _update_artists(self, x, y, trim_values, rudder):
        """Update all dynamic plot artists and the values label."""
        self.dot.set_xdata([x])
        self.dot.set_ydata([y])

        # Pick helicopter or fixed-wing trim based on rotor activity
        threshold = 0.01
        is_helicopter = (abs(trim_values["rotor_lateral_trim"]) > threshold or
                         abs(trim_values["rotor_longitudinal_trim"]) > threshold)
        if is_helicopter:
            elev_trim = trim_values["rotor_longitudinal_trim"]
            ail_trim = trim_values["rotor_lateral_trim"]
        else:
            elev_trim = trim_values["elevator_trim"]
            ail_trim = trim_values["aileron_trim"]

        self.elevator_trim_marker.set_ydata([elev_trim] * 2)
        self.elevator_trim_marker.set_visible(abs(elev_trim) > threshold)
        self.aileron_trim_marker.set_xdata([ail_trim] * 2)
        self.aileron_trim_marker.set_visible(abs(ail_trim) > threshold)

        if rudder is not None:
            self.rudder_marker.set_xdata([rudder, rudder])
            self.rudder_marker.set_visible(True)
            rudder_text = f"{rudder:>5.2f}"
        else:
            self.rudder_marker.set_visible(False)
            rudder_text = "  N/A"

        if self.show_values:
            self.coord_label.config(text=f"X: {x:>5.2f} Y: {y:>5.2f}\nR: {rudder_text}")
            self.coord_label.place(relx=1.0, rely=1.0, x=-2, y=-2, anchor='se')
        else:
            self.coord_label.place_forget()

    def _blit(self):
        """Restore static background, redraw dynamic artists, and blit to display."""
        self.fig.canvas.restore_region(self.static_background)
        for artist in [self.dot, self.elevator_trim_marker, self.aileron_trim_marker, self.rudder_marker]:
            self.fig.draw_artist(artist)
        self.fig.canvas.blit(self.fig.bbox)

    # ========================================================================
    # GUI CREATION
    # ========================================================================

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

        self.dot, = self.ax.plot([], [], 'o', color='yellow', markersize=4, markeredgewidth=0, linestyle='None')
        self.ax.set_xlim(-1.01, 1.01)
        self.ax.set_ylim(-1.01, 1.01)

        self.ax.axhline(0, color='darkgray', lw=0.7)
        self.ax.axvline(0, color='darkgray', lw=0.7)

        self.elevator_trim_marker = self.ax.axhline(0, color=self.TRIM_COLOR, lw=0.8, linestyle='--', visible=False)
        self.aileron_trim_marker = self.ax.axvline(0, color=self.TRIM_COLOR, lw=0.8, linestyle='--', visible=False)
        self.ax.plot([-1.0, 1.0], [0.88, 0.88], color="#303030", lw=1.0)
        self.rudder_marker, = self.ax.plot([0, 0], [0.82, 0.94], color='cyan', lw=1.2, visible=False)

        canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Tk Label for coordinates — kept out of matplotlib's draw loop entirely
        self.coord_label = tk.Label(self.root, text='', font=('Consolas', 7),
                                    fg='darkgray', bg='black', bd=0, highlightthickness=0, anchor='se')
        self.coord_label.place(relx=1.0, rely=1.0, x=-2, y=-2, anchor='se')

        # Sim connection status indicator
        self.sim_status_label = tk.Label(
            self.root, text='No SIM', font=('Consolas', 6),
            fg='#555555', bg='black', bd=0, highlightthickness=0, anchor='sw')
        self.sim_status_label.place(relx=0.0, rely=1.0, x=2, y=-2, anchor='sw')
        self._sim_status_shown = True

        self.fig.canvas.draw()

    def _apply_plot_layout_adjustments(self):
        """Ensure consistent layout settings for the plot."""
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)  # Remove extra padding
        self.fig.patch.set_facecolor('#111111')  # Background for the figure
        self.ax.set_facecolor('#000000')  # Background for the plot
        self.ax.axis('off')  # Hide axes

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

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
        joystick_menu = tk.Menu(self.menu, tearoff=0, bg="#333333", fg="white", activebackground="#555555", activeforeground="white")
        for name in self.joystick_names:
            marker = " *" if name == self.desired_joystick_name else ""
            joystick_menu.add_command(label=f"{name}{marker}", command=lambda n=name: self._handle_joystick_selection(n))
        if not self.joystick_names:
            joystick_menu.add_command(label="No devices", state=tk.DISABLED)
        self.menu.add_cascade(label="Set Joystick Device", menu=joystick_menu)
        self.menu.add_separator()
        device_menu = tk.Menu(self.menu, tearoff=0, bg="#333333", fg="white", activebackground="#555555", activeforeground="white")
        for device_name in self.joystick_names:
            marker = " *" if device_name == self.rudder_joystick_name else ""
            device_menu.add_command(
                label=f"{device_name}{marker}",
                command=lambda n=device_name: self._set_rudder_device(n)
            )
        if not self.joystick_names:
            device_menu.add_command(label="No devices", state=tk.DISABLED)
        self.menu.add_cascade(label="Set Rudder Device", menu=device_menu)

        if self.rudder_joystick:
            rudder_axis_menu = tk.Menu(self.menu, tearoff=0, bg="#333333", fg="white", activebackground="#555555", activeforeground="white")
            axis_count = self.rudder_joystick.get_numaxes()
            for axis_id in range(axis_count):
                marker = " *" if axis_id == self.rudder_axis_id else ""
                rudder_axis_menu.add_command(
                    label=f"Axis {axis_id}{marker}",
                    command=lambda i=axis_id: self._set_rudder_axis(i)
                )
            self.menu.add_cascade(label="Set Rudder Axis", menu=rudder_axis_menu)
        else:
            self.menu.add_command(label="Set Rudder Axis (select rudder device first)", state=tk.DISABLED)
        self.menu.add_separator()
        self.menu.add_command(
            label=f"{'Hide' if self.show_values else 'Show'} Values",
            command=self._toggle_show_values
        )
        self.menu.tk_popup(event.x_root, event.y_root)

    def _handle_joystick_selection(self, name):
        """Handle joystick selection from the context menu."""
        self.desired_joystick_name = name
        self._save_settings(name)
        self._load_joysticks()  # Refresh joysticks and reinitialize selected joystick
        self._apply_plot_layout_adjustments()  # Ensure consistent plot layout

        # Reset last known values to force an update
        self.last_joystick_pos = (None, None)
        self.last_rudder_value = "unset"
        self.last_trim_values = {}

        print_info(f"Joystick '{name}' saved and reloaded.")

    def _set_rudder_device(self, device_name):
        self.rudder_joystick_name = device_name
        self.rudder_joystick = self._get_joystick_by_name(device_name)
        self.rudder_axis_id = None
        self._save_settings(rudder_joystick_name=device_name, rudder_axis_id=None)
        self.last_rudder_value = "unset"
        print_info(f"Rudder device set to '{device_name}'.")

    def _set_rudder_axis(self, axis_id):
        if not self.rudder_joystick:
            print_warning("Cannot set rudder axis without a selected rudder device.")
            return
        self.rudder_axis_id = axis_id
        self._save_settings(rudder_axis_id=axis_id)
        self.last_rudder_value = "unset"
        print_info(f"Rudder axis set to {axis_id} on '{self.rudder_joystick_name}'.")

    def _toggle_show_values(self):
        self.show_values = not self.show_values
        self._save_settings(show_values=self.show_values)
        if self.selected_joystick is None and not self.test_mode:
            self.coord_label.config(text="No Joy!\nRight-click\nto select")
            self.coord_label.place(relx=1.0, rely=1.0, x=-2, y=-2, anchor='se')
        elif self.show_values:
            self.coord_label.place(relx=1.0, rely=1.0, x=-2, y=-2, anchor='se')
        else:
            self.coord_label.place_forget()
        # Force next update tick to redraw even if input values are unchanged.
        self.last_joystick_pos = (None, None)
        self.last_trim_values = {}
        self.last_rudder_value = "unset"
        print_info(f"Show values: {self.show_values}")

if __name__ == "__main__":
    # Get the directory one level up from the current script's directory
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Define the Settings directory and settings file path
    SETTINGS_DIR = os.path.join(BASE_DIR, "Settings")
    SETTINGS_FILE = os.path.join(SETTINGS_DIR, "plot_joystick.json")

    app = JoystickApp(graph_size_pixels=100, alpha_transparency_level=0.8, settings_file=SETTINGS_FILE, test_mode=TEST_MODE)
    app.run()
