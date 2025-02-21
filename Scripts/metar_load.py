# metar_load.py: looks up a list of historical metars for a given airport code
import tkinter as tk
from tkinter import ttk, messagebox
import os
import json
import requests
import re
from datetime import datetime, timedelta, timezone
from SimConnect import SimConnect, AircraftRequests
import subprocess
import threading
import sys
import win32print

try:
    # Import all color print functions
    from Lib.color_print import *
    from Lib.dark_mode import DarkmodeUtils

except ImportError:
    print("Failed to import 'Lib.color_print'. Please ensure /Lib/color_print.py is present")
    sys.exit(1)

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "Settings", "metar_load.json")

printer_name = "VirtualTextPrinter"  # Replace with your specific printer name

class MetarSource:
    """Base class for a METAR source."""
    name = "BaseSource"

    def fetch(self, airport_code):
        raise NotImplementedError

    def parse(self, raw_data):
        raise NotImplementedError

class OgimetSource(MetarSource):
    name = "Ogimet"

    def fetch(self, airport_code):
        url = f"https://www.ogimet.com/display_metars2.php?lugar={airport_code}&tipo=SA&ord=REV&nil=SI&fmt=txt"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text

    def parse(self, raw_data):
        metar_pattern = re.compile(r"\d{12}\s+METAR\s+\w{4}\s+.*?=")
        raw_metar_lines = metar_pattern.findall(raw_data)
        return [re.sub(r"^\d{12}\s+", "", line) for line in raw_metar_lines]

class NoaaSource(MetarSource):
    name = "NOAA"

    def __init__(self):
        self.airport_code = None
        super().__init__()

    def fetch(self, airport_code):
        url = "https://aviationweather.gov/api/data/metar"
        params = {
            "ids": airport_code,
            "format": "json",
            "hours": 24,  # Fetch all 24 hours in one request
        }
        headers = {"Accept": "application/json"}
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        self.airport_code = airport_code
        return response.json()

    def parse(self, raw_data):
        metar_lines = []
        invalid_airports = set()
        for metar in raw_data:
            raw_observation = metar.get("rawOb")
            station_id = metar.get("stationId")
            if station_id != self.airport_code.upper():
                invalid_airports.add(station_id)
            if raw_observation:
                metar_lines.append(raw_observation)

        if invalid_airports:
            raise ValueError(
                f"NOAA returned METARs for unexpected airports: {', '.join(invalid_airports)}. "
                f"Expected only {self.airport_code.upper()}."
            )

        return metar_lines

class AviationWeatherSource(MetarSource):
    name = "AviationWeather"

    def fetch(self, airport_code):
        url = "https://aviationweather.gov/api/data/metar"
        params = {
            "ids": airport_code,
            "format":
            "json",
            "hours": 24  # Fetch METARs for the past 24 hours
        }
        headers = {
            "User-Agent": "METAR Fetcher/1.0 (contact@example.com)",
            "Accept": "application/json"
        }

        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def parse(self, raw_data):
        # Ensure raw_data is a list of dictionaries
        if not isinstance(raw_data, list):
            return []

        metar_lines = []
        for metar_entry in raw_data:
            # Extract 'rawOb' field, which contains the raw METAR text
            raw_observation = metar_entry.get("rawOb")
            if raw_observation:
                metar_lines.append(raw_observation)

        return metar_lines

class MetarFetcher:
    def __init__(self, debug=False):
        self.sources = [NoaaSource(), AviationWeatherSource(), OgimetSource()]
        self.debug = debug

    def parse_metar_datetime(self, metar_line):
        """Parse the date and time from a METAR line."""
        try:
            parts = metar_line.split()
            datetime_part = parts[1]  # e.g., "090900Z"

            day = int(datetime_part[:2])
            time_utc = datetime_part[2:6]

            # Get current year and month with timezone-aware datetime
            now = datetime.now(timezone.utc)
            year, month = now.year, now.month

            # Construct and return the datetime object
            return datetime(year, month, day, int(time_utc[:2]), int(time_utc[2:]), tzinfo=timezone.utc)
        except Exception as e:
            if self.debug:
                print(f"Failed to parse datetime from METAR line: {metar_line}, Error: {e}")
            return None

    def fetch_metar(self, airport_code):
        """Fetch and organize METAR data as a dictionary."""
        if self.debug:
            print(f"Fetching METAR data for {airport_code}...")

        for source in self.sources:
            if self.debug:
                print(f"Trying source: {source.name}")

            try:
                raw_data = source.fetch(airport_code)
                if self.debug:
                    print(f"Raw data from {source.name}: {raw_data}...")

                metar_lines = source.parse(raw_data)
                if self.debug:
                    print(f"Parsed METAR lines from {source.name}: {metar_lines}")

                if metar_lines:
                    if self.debug:
                        print(f"Successfully fetched METAR data from {source.name}")

                    # Transform into a dictionary hashed by datetime
                    metar_dict = {
                        self.parse_metar_datetime(line): line
                        for line in metar_lines
                        if self.parse_metar_datetime(line) is not None
                    }

                    return source.name, metar_dict

            except Exception as e:
                if self.debug:
                    print(f"Error with source {source.name}: {e}")

        raise Exception(f"Failed to fetch METAR data for {airport_code}.")

def print_metar_data(metar_data, printer_name="VirtualTextPrinter"):
    """Print the METAR data using the Windows printing API."""
    try:
        # Use the specified printer or fallback to the default
        if not printer_name:
            printer_name = win32print.GetDefaultPrinter()

        # Open the printer and start a print job
        hprinter = win32print.OpenPrinter(printer_name)
        job = win32print.StartDocPrinter(hprinter, 1, ("METAR Print Job", None, "RAW"))
        win32print.StartPagePrinter(hprinter)

        # Send the data to the printer
        win32print.WritePrinter(hprinter, metar_data.encode('utf-8'))
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
        win32print.ClosePrinter(hprinter)

    except Exception as e:
        messagebox.showerror("Print Error", f"Failed to print METAR data: {e}")

def show_metar_data(source_name, metar_dict):
    """
    Display processed METAR data in a new window.

    Args:
        source_name (str): The name of the METAR data source.
        metar_dict (dict): Dictionary with datetime keys and METAR strings as values.
    """
    # Create the new result window
    result_window = tk.Toplevel(root)
    result_window.title(f"METAR Data - {source_name}")
    result_window.configure(bg="#2e2e2e")  # Softer dark gray background

    # Configure grid layout for resizing
    result_window.rowconfigure(2, weight=1)  # Text widget row expands
    result_window.columnconfigure(0, weight=1)

    DarkmodeUtils.apply_dark_mode(result_window)

    # Title label
    try:
        simulator_time = get_simulator_datetime()
        title_text = f"METAR Data (Source: {source_name})\nClosest METAR to Simulator Time: {simulator_time}"
    except Exception as e:
        title_text = f"METAR Data (Source: {source_name})\nError fetching simulator time: {e}"

    title_label = tk.Label(
        result_window,
        text=title_text,
        font=("Arial", 12, "bold"),
        bg="#2e2e2e",
        fg="#d3d3d3",
        justify="left",
    )
    title_label.grid(row=0, column=0, sticky="ew", padx=10, pady=5)

    # Subtitle label for multi-METAR indication
    try:
        result = find_best_metar(metar_dict)
        if isinstance(result, list):  # Multiple METARs are being displayed
            subtitle_text = "WARNING: Could not match METAR - showing all."
        else:  # Single METAR returned
            subtitle_text = None
    except ValueError as e:
        subtitle_text = None

    if subtitle_text:
        subtitle_label = tk.Label(
            result_window,
            text=subtitle_text,
            font=("Arial", 12, "bold"),
            bg="#2e2e2e",
            fg="#FFaaaa",
            justify="left",
        )
        subtitle_label.grid(row=1, column=0, sticky="ew", padx=10, pady=2)

    # Create a frame for the Listbox and scrollbar
    listbox_frame = tk.Frame(result_window, bg="#2e2e2e")
    listbox_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

    # Create the Listbox
    metar_listbox = tk.Listbox(
        listbox_frame,
        font=("Consolas", 12),
        bg="#222222",
        fg="#d3d3d3",
        selectbackground="#444444",
        selectforeground="#ffffff",
        activestyle="none",
        highlightbackground="#3c3c3c",
        highlightcolor="#3c3c3c",
        width=120
    )
    metar_listbox.pack(side="left", fill="both", expand=True)

    sorted_metars = sorted(metar_dict.items(), key=lambda item: item[0])  # Sort by timestamp

    # Populate output window
    if isinstance(result, str):
        metar_listbox.insert("end", result)
        metar_listbox.selection_set(0)
    else:  # Show all results if a match could not be found
        for metar in sorted_metars:
            metar_listbox.insert("end", metar[1])

    def get_selected_content():
        """Get the selected METAR content from the Listbox."""
        if metar_listbox.size() == 1:
            return metar_listbox.get(0)
        selected_indices = metar_listbox.curselection()
        if not selected_indices:
            return None
        return "\n".join(metar_listbox.get(i) for i in selected_indices)

    def results_close():
        result_window.destroy()
        root.quit()

    def print_and_close(event=None):
        print_metar_data(get_selected_content(), printer_name) if get_selected_content() else None,
        results_close()

    # Print Button at the bottom
    print_button = tk.Button(
        result_window,
        text="Print METAR Data",
        command=print_and_close,
        bg="#5A5A5A",
        fg="#FFFFFF",
        activebackground="#3A3A3A",
        activeforeground="#FFFFFF",
        font=("Helvetica", 10),
    )
    print_button.grid(row=3, column=0, padx=10, pady=5)

    result_window.bind("<Return>", print_and_close)
    result_window.bind("<Escape>", lambda event: results_close())
    result_window.protocol("WM_DELETE_WINDOW", results_close)

    # Center the window
    center_window(result_window)

def gui_fetch_metar(root, airport_code):
    """Fetch METAR data with a non-blocking popup loading window."""
    if not airport_code:
        print_warning("Please enter a valid airport ICAO code.")
        return

    print_info("Looking up metar. Please wait...")

    fetcher = MetarFetcher()
    source_name, metar_dict = fetcher.fetch_metar(airport_code)
    show_metar_data(source_name, metar_dict)

def find_best_metar(metar_dict):
    """
    Find the historical METAR closest in time to the simulator's current time,
    ensuring the METAR timestamp is not after the simulator time. If the simulator
    time is outside the range of available data, return all METARs.

    Args:
        metar_dict (dict): Dictionary where keys are datetime objects (METAR timestamps) and
                           values are the corresponding METAR strings.

    Returns:
        str | list: The closest METAR string, or a list of all METARs if the simulator time
                    is outside the data range.

    Raises:
        ValueError: If no METAR data is available.
    """
    simulator_time = get_simulator_datetime()  # Fetch the simulator's current datetime
    #simulator_time = datetime(2025, 1, 15, 1, 0, tzinfo=timezone.utc)
    print(f"Simulator Time: {simulator_time}")

    grace_period = timedelta(minutes=15)  # Allow a 15-minute delay in METAR updates

    if not metar_dict:
        raise ValueError("No METAR data available.")

    # Sort METARs by timestamp
    sorted_metars = sorted(metar_dict.items(), key=lambda item: item[0])

    print_color("METAR List (Sorted):", color="yellow")
    for metar_time, metar in sorted_metars:
        print_debug(f"METAR: {metar_time} - {metar}")

    # Get the earliest and latest timestamps
    earliest_time = sorted_metars[0][0] - timedelta(hours=1)
    latest_time = sorted_metars[-1][0] + timedelta(hours=2)

    # Check if the simulator time is outside the range
    if simulator_time < earliest_time or simulator_time > latest_time:
        print_color(
            "Simulator time is outside the range of available METAR data. Returning all METARs.",
            color="red"
        )
        return [metar for _, metar in sorted_metars]

    # Filter only METARs with timestamps <= simulator_time
    valid_metars = {
        time: metar for time, metar in metar_dict.items() if time <= simulator_time + grace_period
    }

    print_color("Valid METAR List (Filtered):", color="cyan")
    for metar_time, metar in valid_metars.items():
        print_debug(f"Valid METAR: {metar_time} - {metar}")

    if not valid_metars:
        print_color("No valid METARs found. All METARs are in the future.", color="red")
        raise ValueError("No suitable METAR found (all METARs are in the future).")

    # Find the closest METAR by timestamp
    closest_time = max(valid_metars.keys())  # The closest valid METAR will have the largest timestamp <= simulator_time
    closest_metar = valid_metars[closest_time]

    print_color("Closest METAR Found:", color="green")
    print_debug(f"METAR: {closest_metar} at {closest_time}")

    return closest_metar

def main():
    """Main function to initialize the GUI with reference-accurate styling."""
    global root, entry

    initialize_simconnect()
    root = tk.Tk()
    root.withdraw()

    settings = load_settings()
    use_simulator_time = settings.get("use_simulator_time", True)

    print("=" * 80)
    print_color("   METAR Lookup Tool ", color="green")
    print("=" * 80)

    print_color(f"NOTE: [green(]use_simulator_time[)] is currently set to [yellow(]{use_simulator_time}[)]\n")
    print_color(
        "This setting determines whether METAR data is matched to:\n"
        "- The [cyan(]real-world time[)] (if [red(]False[)]), OR\n"
        "- The [cyan(]simulator's in-game time[)] (if [green(]True[)])\n"
    )

    print("Click the 'Open Settings' button to change the settings for this script\n\n")

    while True:
        print("Enter an Airport ICAO Code (or type 'quit' to exit):")
        airport_code = input("> ").strip().lower()

        if airport_code == "quit":
            print("Exiting the program. Goodbye!")
            break

        if not airport_code:
            print("Error: No ICAO code entered. Please try again.")
            continue

        # Create a new Tkinter root for this iteration
        root = tk.Tk()
        root.withdraw()  # Hide the root window (we only use dialogs)



        try:
            # Fetch and display METAR data
            gui_fetch_metar(root, airport_code)
            root.mainloop()  # Start the event loop
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            # Clean up and destroy the root after the GUI closes
            root.destroy()

def on_close():

    root.destroy()

def load_settings():
    """Load settings from the JSON file or create a default one if missing."""
    default_settings = {"use_simulator_time": False}

    # Ensure settings directory exists
    settings_dir = os.path.dirname(SETTINGS_FILE)
    os.makedirs(settings_dir, exist_ok=True)

    if not os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(default_settings, f, indent=4)
        return default_settings

    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        print("Error: Invalid settings file. Using default settings.")
        return default_settings

def get_simulator_datetime():
    """
    Fetch the date/time from either the simulator or real-world time based on settings.
    """
    settings = load_settings()

    if settings.get("use_simulator_time", True):
        global sim_connected
        try:
            if not sim_connected:
                raise ValueError("SimConnect is not connected.")

            absolute_time = aq.get("ABSOLUTE_TIME")
            if absolute_time is None:
                raise ValueError("ABSOLUTE_TIME is unavailable.")

            base_datetime = datetime(1, 1, 1, tzinfo=timezone.utc)
            return base_datetime + timedelta(seconds=float(absolute_time))

        except Exception as e:
            print(f"Failed to retrieve simulator time: {e}")

    # Default to real-world UTC time if simulator time is disabled or unavailable
    return datetime.now(timezone.utc)

def initialize_simconnect():
    """
    Initialize the connection to SimConnect and set up global variables.
    Establishes a connection to the simulator and prepares for data retrieval.
    """
    global sm, aq, sim_connected
    try:
        # Initialize the SimConnect connection
        sm = SimConnect()  # Create the SimConnect object to establish communication
        aq = AircraftRequests(sm, _time=0)  # Create the AircraftRequests object for querying data
        sim_connected = True
        print("SimConnect initialized successfully.")
    except Exception as e:
        sim_connected = False
        print(f"Failed to initialize SimConnect: {e}")

def center_window(window):
    """
    Center a Tkinter window on the screen.

    Args:
        window: The window to center (e.g., root or Toplevel instance).
        width: The width of the window.
        height: The height of the window.
    """
    # Ensure the window's dimensions are realized
    window.update_idletasks()

    width = window.winfo_width()
    height = window.winfo_height()

    # Get the screen dimensions
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    # Calculate position coordinates
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2

    # Set the geometry of the window
    window.geometry(f"{width}x{height}+{x}+{y}")

    # Bring the window to the foreground
    window.deiconify()  # Make the window visible if it was hidden
    window.lift()       # Raise the window above others
    window.attributes("-topmost", True)  # Temporarily make it always on top
    window.attributes("-topmost", False)  # Disable "always on top"
    window.focus_force()  # Focus on the window
    window.focus_set()

if __name__ == "__main__":
    main()
