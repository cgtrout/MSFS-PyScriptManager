# metar_load.py: looks up a list of historical metars for a given airport code
import tkinter as tk
from tkinter import ttk, messagebox
import requests
import re
from datetime import datetime, timedelta, timezone
from SimConnect import SimConnect, AircraftRequests
import subprocess
import threading


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
        # Fetch data in 1.5-hour increments up to 12 hours
        for hours in range(1, 13, 1):  # Fetch in hourly increments
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
            "hours": 12  # Fetch METARs for the past 12 hours
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

def show_metar_data(source_name, metar_dict, show_best_only=True):
    """
    Display processed METAR data in a new window.

    Args:
        source_name (str): The name of the METAR data source.
        metar_dict (dict): Dictionary with datetime keys and METAR strings as values.
        show_best_only (bool): If True, only show the METAR closest to the current simulator time.
    """
    # Create the new result window
    result_window = tk.Toplevel(root)
    result_window.title(f"METAR Data - {source_name}")
    result_window.configure(bg="#2e2e2e")  # Softer dark gray background

    # Set a fixed size and center the window
    window_width, window_height = 600, 1000  # Adjusted size
    result_window.geometry(f"{window_width}x{window_height}")
    center_window(result_window, window_width, window_height)

    # Title label (source and closest METAR timestamp)
    try:
        simulator_time = get_simulator_datetime()
        if show_best_only:
            title_text = f"METAR Data (Source: {source_name})\nClosest METAR to Simulator Time: {simulator_time}"
        else:
            title_text = f"METAR Data (Source: {source_name})"
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
    title_label.pack(pady=(5, 10))  # Padding for the title

    # Text widget
    text_widget = tk.Text(
        result_window,
        wrap="none",  # No word wrapping
        font=("Consolas", 12),
        bg="#222222",
        fg="#d3d3d3",
        insertbackground="#d3d3d3",  # Cursor color
        highlightbackground="#3c3c3c",  # Border color
        highlightcolor="#3c3c3c",
        relief="flat",  # Remove border styles
    )
    text_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))  # Padding below for the button

    # Populate the text widget
    if show_best_only:
        try:
            best_metar = find_best_metar(metar_dict)
            content = best_metar  # Only show the closest METAR
        except ValueError as e:
            content = f"Error finding the closest METAR: {e}"
    else:
        content = "\n".join(
            f"{key.strftime('%Y-%m-%d %H:%M:%S')} - {value}" for key, value in metar_dict.items()
        )

    text_widget.insert("1.0", content)
    text_widget.configure(state="disabled")

    # Print METAR Data Function
    def print_metar_data():
        """Print the METAR data in the text widget using PowerShell."""
        metar_data = text_widget.get("1.0", "end").strip()  # Get text content

        try:
            # PowerShell command to send the METAR data directly to the printer
            powershell_cmd = f"""
            $text = "{metar_data}";
            $text | Out-Printer -Name '{printer_name}'
            """

            # Run the PowerShell command
            result = subprocess.run(
                ["powershell", "-Command", powershell_cmd],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )

            # Check if the command was successful
            if result.returncode != 0:
                raise Exception(f"PowerShell Error: {result.stderr.strip()}")

        except Exception as e:
            # Show an error message if printing fails
            messagebox.showerror("Print Error", f"Failed to print METAR data: {e}")

    # Print Button
    print_button = tk.Button(
        result_window,
        text="Print METAR Data",
        command=print_metar_data,
        bg="#5A5A5A",
        fg="#FFFFFF",
        activebackground="#3A3A3A",
        activeforeground="#FFFFFF",
        font=("Helvetica", 10),
    )
    print_button.pack(pady=(5, 5))

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

    # Extract only the time portion of the simulator time
    simulator_time_only = simulator_time.time()

    # Sort METARs by datetime in reverse order (newest first)
    sorted_metars = sorted(metar_dict.items(), key=lambda item: item[0], reverse=True)

    # Find the METAR with the smallest time difference that is not in the future
    best_metar = None
    smallest_time_diff = timedelta.max  # Initialize with a very large time difference

    for metar_time, metar in sorted_metars:
        # Ensure the METAR is not in the future relative to the simulator's current full datetime
        if metar_time > simulator_time:
            continue  # Skip future METARs

        # Extract only the time portion of the METAR timestamp
        metar_time_only = metar_time.time()

        # Calculate the absolute time difference
        time_diff = abs(
            timedelta(
                hours=metar_time_only.hour, minutes=metar_time_only.minute
            ) - timedelta(
                hours=simulator_time_only.hour, minutes=simulator_time_only.minute
            )
        )

        # Update the best METAR if this one is closer
        if time_diff < smallest_time_diff:
            smallest_time_diff = time_diff
            best_metar = metar

    if best_metar is not None:
        return best_metar

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
    Ensures the result is timezone-aware and valid. If unavailable, defaults to the Unix epoch.
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
        # Default to Unix epoch if simulator time is unavailable
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

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
