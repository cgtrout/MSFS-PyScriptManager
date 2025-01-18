# metar_load.py: looks up a list of historical metars for a given airport code
import tkinter as tk
from tkinter import ttk, messagebox
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

except ImportError:
    print("Failed to import 'Lib.color_print'. Please ensure /Lib/color_print.py is present")
    sys.exit(1)

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

    def fetch(self, airport_code):
        url = "https://aviationweather.gov/api/data/metar"
        headers = {
            "Accept": "application/json",
        }

        all_metars = []
        # Fetch data
        for hours in range(1, 25, 1):  # Fetch in hourly increments
            params = {
                "ids": airport_code,
                "format": "json",
                "hours": hours,
            }

            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            raw_data = response.json()

            if raw_data:
                all_metars.extend(raw_data)

        return all_metars

    def parse(self, raw_data):
        metar_lines = []
        for metar in raw_data:
            raw_observation = metar.get("rawOb")
            if raw_observation:
                metar_lines.append(raw_observation)
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

    # Text widget with scrollbar in a frame
    text_frame = tk.Frame(result_window, bg="#2e2e2e")
    text_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

    text_widget = tk.Text(
        text_frame,
        wrap="none",
        font=("Consolas", 12),
        bg="#222222",
        fg="#d3d3d3",
        insertbackground="#d3d3d3",  # Cursor color
        highlightbackground="#3c3c3c",  # Border color
        highlightcolor="#3c3c3c",
        relief="flat",  # Remove border styles
        height=1
    )
    text_widget.pack(side="left", fill="both", expand=True)

    # Populate the text widget
    if isinstance(result, list):  # If multiple METARs are returned
        text_widget.config(height=min(len(result), 20))
        content = "\n".join(result)
    else:  # Single METAR returned
        content = result

    text_widget.insert("1.0", content)
    text_widget.configure(state="disabled")

    # Print Button at the bottom
    print_button = tk.Button(
        result_window,
        text="Print METAR Data",
        command=lambda: print_metar_data(content, printer_name),
        bg="#5A5A5A",
        fg="#FFFFFF",
        activebackground="#3A3A3A",
        activeforeground="#FFFFFF",
        font=("Helvetica", 10),
    )
    print_button.grid(row=3, column=0, padx=10, pady=5)

    print("Text widget height:", text_widget.cget("height"))
    print("Text widget geometry:", text_widget.winfo_geometry())

    # Center the window
    result_window.update_idletasks()  # Force geometry update
    window_width = result_window.winfo_width()
    window_height = result_window.winfo_height()
    center_window(result_window, window_width, window_height)

def gui_fetch_metar():
    """Fetch METAR data with a non-blocking popup loading window."""
    airport_code = entry.get().strip().upper()
    if not airport_code:
        messagebox.showerror("Error", "Please enter a valid airport ICAO code.")
        return

    # Create a popup loading window
    loading_popup = tk.Toplevel(root)
    loading_popup.title("Loading")

    # Set size and center the popup window
    popup_width, popup_height = 300, 100
    center_window(loading_popup, popup_width, popup_height)

    loading_popup.configure(bg="#2E2E2E")

    # Add a loading label
    loading_label = tk.Label(
        loading_popup,
        text="Fetching METAR data, please wait...",
        font=("Helvetica", 12, "italic"),
        bg="#2E2E2E",
        fg="#FFFFFF"
    )
    loading_label.pack(expand=True, fill="both", pady=20)

    def fetch_data():
        try:
            fetcher = MetarFetcher()
            source_name, metar_dict = fetcher.fetch_metar(airport_code)

            root.after(0, lambda: show_metar_data(source_name, metar_dict))
        except Exception as e:
            root.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
             # Safely destroy the popup and join the thread
            root.after(0, lambda: (loading_popup.destroy()))

    # Run the fetch_data function in a background thread
    thread = threading.Thread(target=fetch_data, daemon=True)
    thread.start()

def find_best_metar(metar_dict):
    """
    Find the historical METAR closest in time to the simulator's current time, ensuring it's not in the future.

    Args:
        metar_dict (dict): Dictionary where keys are datetime objects (METAR timestamps) and
                           values are the corresponding METAR strings.

    Returns:
        str: The METAR string closest in time (ignoring date mismatches but ensuring it's not in the future).

    Raises:
        ValueError: If no suitable METAR is found.
    """
    simulator_time = get_simulator_datetime()  # Fetch the simulator's current datetime
    print(f"Simulator Time: {simulator_time}")

    if not metar_dict:
        raise ValueError("No METAR data available.")

    # Sort METARs by datetime in reverse order (newest first)
    sorted_metars = sorted(metar_dict.items(), key=lambda item: item[0], reverse=True)

    # First print list for debugging purposes
    print_color("METAR List:", color="yellow")
    for metar_time, metar in sorted_metars:
        print_debug(f"METAR: {metar_time} - {metar}")

    print_color("Now Finding Best METAR:", color="yellow")

    previous_metar_seconds = None  # To track the previous METAR's seconds
    crossed_midnight = False  # Track whether we have crossed midnight

    # Simulator time in seconds since midnight
    simulator_seconds = ( simulator_time.hour * 3600 + simulator_time.minute * 60 + simulator_time.second )

    for metar_time, metar in sorted_metars:
        metar_seconds = (
            metar_time.hour * 3600 + metar_time.minute * 60 + metar_time.second
        )  # METAR time in seconds since midnight

        print_debug(f"--Checking METAR: {metar_time} - {metar}-----------")
        print_debug(f"Simulator seconds: {simulator_seconds}, METAR seconds: {metar_seconds}")

        # Detect midnight crossing if metar_seconds jumps backward
        if previous_metar_seconds is not None and metar_seconds > previous_metar_seconds:
            print_debug("Detected midnight crossing based on time jump.\n")
            crossed_midnight = True

        previous_metar_seconds = metar_seconds  # Update for the next iteration

        # Logic before or after midnight crossing
        if not crossed_midnight:
            if metar_seconds > simulator_seconds:
                print_debug("Skipping future METAR.\n")
                continue
            else:
                print_debug(f"Found valid METAR before midnight crossing: {metar}")
                return metar
        else:
            # After midnight crossing, allow the first valid METAR
            if metar_seconds > simulator_seconds:
                print_debug(f"Found valid METAR after midnight crossing: {metar}")
                return metar

    # If no valid METAR is found, raise an error
    raise ValueError("No suitable METAR found.")

def main():
    """Main function to initialize the GUI with reference-accurate styling."""
    global root, entry

    # Dark mode colors
    bg_color = "#2E2E2E"           # Dark background
    fg_color = "#FFFFFF"           # Light text
    entry_bg_color = "#3A3A3A"     # Slightly lighter background for entries
    entry_fg_color = "#FFFFFF"     # Text color for entries
    button_bg_color = "#5A5A5A"    # Dark button background
    button_fg_color = "#FFFFFF"    # Light button text

    initialize_simconnect()

    # Create the main Tkinter window
    root = tk.Tk()
    root.title("METAR Data Processor")
    root.geometry("300x150")
    root.configure(bg=bg_color)  # Dark background color

    main_width, main_height = 300, 150
    center_window(root, main_width, main_height)
    root.configure(bg="#2E2E2E")

    # Fonts
    small_font = ("Helvetica", 10)
    large_font = ("Helvetica", 14)

    # Label for ICAO input
    tk.Label(
        root,
        text="Enter Airport ICAO Code:",
        bg=bg_color,
        fg=fg_color,
        font=large_font
    ).pack(pady=(20, 10))

    # ICAO Code Entry
    entry = tk.Entry(
        root,
        bg=entry_bg_color,
        fg=entry_fg_color,
        font=large_font,
        insertbackground=entry_fg_color,  # Cursor color
        justify="center",
        width=20
    )
    entry.pack(pady=0)

    # Auto-select the entry box
    entry.focus_set()

    # Button Frame
    button_frame = tk.Frame(root, bg=bg_color)
    button_frame.pack(pady=(20, 10))

    # Fetch Button
    tk.Button(
        button_frame,
        text="Fetch METAR Data",
        command=gui_fetch_metar,
        bg=button_bg_color,
        fg=button_fg_color,
        activebackground=entry_bg_color,  # Slightly lighter background when pressed
        activeforeground=fg_color,       # Retain white text when pressed
        font=small_font,
        width=20
    ).pack(side="left", padx=5)

    # Bind Enter key to Fetch METAR Data
    root.bind("<Return>", lambda event: gui_fetch_metar())

    root.protocol("WM_DELETE_WINDOW", on_close)

    # Start the Tkinter main loop
    root.mainloop()

def on_close():

    root.destroy()

def get_simulator_datetime() -> datetime:
    """
    Fetch the current simulator date and time dynamically (in ZULU/UTC format).
    Ensures the result is timezone-aware and valid. If unavailable, defaults to the current system date/time.
    """
    global sim_connected
    try:
        if not sim_connected:
            raise ValueError("SimConnect is not connected.")

        # Fetch simulator date and time variables directly
        zulu_year = aq.get("ZULU_YEAR")
        zulu_month = aq.get("ZULU_MONTH_OF_YEAR")
        zulu_day = aq.get("ZULU_DAY_OF_MONTH")
        zulu_time_seconds = aq.get("ZULU_TIME")

        # Ensure all values are retrieved and valid
        if None in (zulu_year, zulu_month, zulu_day, zulu_time_seconds):
            raise ValueError("Simulator date/time variables are unavailable or invalid.")

        # Convert variables to proper types
        zulu_year = int(zulu_year)
        zulu_month = int(zulu_month)
        zulu_day = int(zulu_day)
        zulu_time_seconds = float(zulu_time_seconds)

        # Convert ZULU_TIME (seconds since midnight) into hours, minutes, seconds
        hours, remainder = divmod(int(zulu_time_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)

        # Construct and return the datetime object with UTC timezone
        return datetime(zulu_year, zulu_month, zulu_day, hours, minutes, seconds, tzinfo=timezone.utc)

    except Exception as e:
        print(f"get_simulator_datetime: Failed to retrieve simulator datetime: {e}")
        # Fallback to current system date and time in UTC
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

def center_window(window, width, height):
    """
    Center a Tkinter window on the screen.

    Args:
        window: The window to center (e.g., root or Toplevel instance).
        width: The width of the window.
        height: The height of the window.
    """
    # Get the screen dimensions
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    # Calculate position coordinates
    x = (screen_width - width) // 2
    y = (screen_height - height) // 2

    # Set the geometry of the window
    window.geometry(f"{width}x{height}+{x}+{y}")


if __name__ == "__main__":
    main()
