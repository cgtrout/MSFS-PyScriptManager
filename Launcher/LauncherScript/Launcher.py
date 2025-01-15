# Launcher.py - main launcher app script for MSFSPyScriptManager

import logging
import os
import queue
import subprocess
import sys
import threading
import time
from multiprocessing import Process, Event
from pathlib import Path
from typing import Dict
import ctypes

# Import parse_ansi_colors from local parse_ansi.py
from parse_ansi import parse_ansi_colors

import tkinter as tk
from tkinter import filedialog, scrolledtext, TclError
from tkinter import ttk

import psutil
import re
from ttkthemes import ThemedTk

from ordered_logger import OrderedLogger

# Path to the WinPython Python executable and VS Code.exe
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parents[1]
python_path = project_root / "WinPython" / "python-3.13.0rc1.amd64" / "python.exe"
pythonw_path = python_path.with_name("pythonw.exe")
vscode_path = project_root / "WinPython" / "VS Code.exe"
scripts_path = project_root / "Scripts"

# Define color constants
DARK_BG_COLOR = "#2E2E2E"
BUTTON_BG_COLOR = "#444444"
BUTTON_FG_COLOR = "#FFFFFF"
BUTTON_ACTIVE_BG_COLOR = "#666666"
BUTTON_ACTIVE_FG_COLOR = "#FFFFFF"
TEXT_WIDGET_BG_COLOR = "#1E1E1E"
TEXT_WIDGET_FG_COLOR = "#FFFFFF"
TEXT_WIDGET_INSERT_COLOR = "#FFFFFF"
FRAME_BG_COLOR = "#2E2E2E"

# Configure logging globally
logging = OrderedLogger(
    filename="shutdown_log.txt",  # Specify the log file
    level=logging.DEBUG,
    log_format="%(asctime)s [%(levelname)s] %(message)s"
)

class Tab:
    """Manages the content and behavior of an individual tab (its frame, widgets, etc.)."""
    def __init__(self, title):
        self.title = title
        self.is_active = False
        self.text_widget = None
        self.frame = None

    def initialize_frame(self, notebook):
        """Create the frame for this tab within the given notebook."""
        self.frame = ttk.Frame(notebook)

    def insert_output(self, text):
        """Insert text into the tab's text widget in a thread-safe way."""
        if not hasattr(self, 'text_widget') or not self.text_widget:
            print(f"[WARNING] Text widget not found in tab '{self.title}'. Skipping output.")
            return

        if self.text_widget.winfo_exists():
            # Schedule the update on the main thread
            self.frame.after(0, lambda: self._safe_insert(text))

    def _safe_insert(self, text):
        """Safely insert text into the text widget."""
        try:
            self.text_widget.insert(tk.END, text)
            self.text_widget.see(tk.END)  # Scroll to the end
        except Exception as e:
            print(f"[ERROR] Issue inserting text into widget: {e}")

    def close(self):
        """Clean up resources associated with the tab."""
        if self.frame:
            self.frame.destroy()
        print(f"[INFO] Tab '{self.title}' closed.")

class TabManager:
    """Manages the Notebook and all tabs."""
    def __init__(self, root, scheduler):
        self.notebook = ttk.Notebook(root)
        self.configure_notebook()
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)
        self.tabs = {}
        self.current_tab_id = 0  # Counter for unique tab IDs

        self.scheduler = scheduler

        # Track the original name of the currently highlighted tab
        self.current_highlighted_tab = None
        self.original_tab_name = None

        # Store drag state
        self.drag_start_tab = None
        self.drag_target_tab = None

        # Bind events for drag-and-drop
        self.notebook.bind("<ButtonPress-1>", self.on_tab_drag_start)
        self.notebook.bind("<B1-Motion>", self.on_tab_drag_motion)
        self.notebook.bind("<ButtonRelease-1>", self.on_tab_drag_release)

        # Bind the tab change event
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

    def on_tab_change(self, event):
        """Update active tab state."""
        selected_frame = self.notebook.nametowidget(self.notebook.select())
        for tab_id, tab in self.tabs.items():
            if tab.frame == selected_frame:
                # Mark the new tab as active
                tab.is_active = True
                self.current_tab_id = tab_id
            else:
                # Mark other tabs as inactive
                tab.is_active = False

    def configure_notebook(self):
        """Configure notebook style and behavior."""
        style = ttk.Style()
        style.configure('TNotebook', padding=[0, 0])
        style.configure('TNotebook.Tab', padding=[5, 2])
        style.configure('TFrame', background=DARK_BG_COLOR)

        # Bind right-click to close tabs
        self.notebook.bind("<Button-3>", self.on_tab_right_click)

    def on_tab_drag_start(self, event):
        """Record the index of the tab being dragged."""
        try:
            self.drag_start_tab = self.notebook.index(f"@{event.x},{event.y}")
            print(f"[DEBUG] Drag started on tab index: {self.drag_start_tab}")
        except TclError:
            self.drag_start_tab = None
            print("[DEBUG] Drag start: No tab found under the cursor.")

    def on_tab_drag_motion(self, event):
        """Dynamically highlight the tab under the cursor."""
        try:
            # Get the tab currently under the cursor
            self.drag_target_tab = self.notebook.index(f"@{event.x},{event.y}")

            # If the tab under the cursor has changed, update the highlight
            if self.drag_target_tab != self.current_highlighted_tab:
                # Restore the original name of the previously highlighted tab
                if self.current_highlighted_tab is not None:
                    self.notebook.tab(
                        self.current_highlighted_tab, text=self.original_tab_name
                    )

                # Save the original name of the new target tab
                self.current_highlighted_tab = self.drag_target_tab
                self.original_tab_name = self.notebook.tab(
                    self.current_highlighted_tab, "text"
                )

                # Highlight the new target tab
                self.notebook.tab(
                    self.current_highlighted_tab,
                    text=f"< {self.original_tab_name} >",
                )
        except TclError:
            pass  # Cursor is outside tabs

    def on_tab_drag_release(self, event):
        """Restore tab titles and perform the tab swap."""
        try:
            # Restore the original tab title if it was highlighted
            if self.current_highlighted_tab is not None:
                self.notebook.tab(
                    self.current_highlighted_tab, text=self.original_tab_name
                )

            # Perform the tab swap if both start and target are valid
            if self.drag_start_tab is not None and self.drag_target_tab is not None:
                self.swap_tabs(self.drag_start_tab, self.drag_target_tab)

            # Reset the drag state
            self.current_highlighted_tab = None
            self.original_tab_name = None
            self.drag_start_tab = None
            self.drag_target_tab = None
        except TclError as e:
            print(f"[ERROR] Drag release failed: {e}")

    def swap_tabs(self, index1, index2):
        """Swap two tabs in the notebook."""
        if index1 == index2:
            print("[DEBUG] Swap not needed: Dragged tab is already in the correct position.")
            return

        tab1_frame = self.notebook.tabs()[index1]
        tab2_frame = self.notebook.tabs()[index2]

        print(f"[DEBUG] Swapping tab frames: {tab1_frame} <-> {tab2_frame}")

        self.notebook.insert(index2, tab1_frame)
        self.notebook.insert(index1, tab2_frame)

        print("[DEBUG] Tabs swapped successfully.")

    def generate_tab_id(self):
        """Generate a unique tab ID."""
        self.current_tab_id += 1
        return self.current_tab_id

    def add_tab(self, tab):
        """Add a new tab to the notebook."""

        def _add_tab():
            tab_id = self.generate_tab_id()  # Generate tab ID on the main thread
            tab.tab_id = tab_id
            tab.initialize_frame(self.notebook)
            tab.build_content()
            self.notebook.add(tab.frame, text=tab.title)
            self.tabs[tab_id] = tab
            self.notebook.select(tab.frame)

        self.scheduler(0, _add_tab)  # Schedule the entire operation on the main thread

    def close_tab(self, tab_id):
        """Close a tab and clean up resources."""
        def _close_tab():
            logging.debug("close_tab inner")
            tab = self.tabs.pop(tab_id, None)
            if not tab:
                print(f"[WARNING] Tab with ID {tab_id} not found.")
                return
            tab.close()

        logging.debug("Schedule: _close_tab")
        self.scheduler(0, _close_tab)  # Schedule operation on the main thread

    def close_all_tabs(self):
        """Close all tabs and clean up resources."""
        print("[INFO] Closing all tabs.")
        for tab_id in list(self.tabs.keys()):  # Copy keys to avoid runtime modification issues
            print(f"[INFO] Closing tab with ID {tab_id}.")
            self.close_tab(tab_id)
        print("[INFO] All tabs closed.")

    def on_tab_right_click(self, event):
        """Handle right-click to close a tab."""
        def _close_tab_on_click():
            try:
                clicked_tab_index = self.notebook.index(f"@{event.x},{event.y}")
                self.close_tab_by_index(clicked_tab_index)
            except TclError:
                print("[ERROR] Right-click did not occur on a valid tab. Ignoring.")

        self.scheduler(0, _close_tab_on_click)  # Schedule operation on the main thread

    def close_tab_by_index(self, index):
        """Close a tab by its notebook index."""
        def _close_by_index():
            try:
                frame = self.notebook.winfo_children()[index]
                for tab_id, tab in list(self.tabs.items()):
                    if tab.frame == frame:
                        self.close_tab(tab_id)  # Use the standard close logic
                        return
            except Exception as e:
                print(f"[ERROR] Issue closing tab by index {index}: {e}")

        self.scheduler(0, _close_by_index)  # Schedule operation on the main thread

class ScriptTab(Tab):
    """Represents one running script in a tab"""
    def __init__(self, title, script_path, process_tracker):
        super().__init__(title)
        self.script_path = script_path
        self.process_tracker = process_tracker
        self.tab_id = None

        # Define font settings
        self.font_normal = ("Consolas", 12)
        self.font_bold = ("Consolas", 12, "bold")

    def build_content(self):
        """Build the content of the ScriptTab."""

        # Create a frame to hold the text widget and scrollbar
        content_frame = tk.Frame(self.frame, bg=FRAME_BG_COLOR)
        content_frame.pack(side="top", expand=True, fill="both")  # Allow it to expand

        # Create the text widget without a built-in scrollbar
        self.text_widget = tk.Text(
            content_frame,
            wrap="word",
            bg=TEXT_WIDGET_BG_COLOR,
            fg=TEXT_WIDGET_FG_COLOR,
            insertbackground=TEXT_WIDGET_INSERT_COLOR,
            font=self.font_normal
        )
        self.text_widget.pack(side="left", expand=True, fill="both")

        # Create a styled ttk.Scrollbar and attach it to the text widget
        scrollbar = ttk.Scrollbar(
            content_frame,
            orient="vertical",
            command=self.text_widget.yview

        )
        self.text_widget.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")  # Place the scrollbar next to the text widget

        # Create the bottom frame for control buttons
        button_frame = tk.Frame(self.frame, bg=FRAME_BG_COLOR)  # Apply dark background color
        button_frame.pack(side="bottom", fill="x", padx=5, pady=5)

        # Add the "Edit Script" button
        edit_button = tk.Button(
            button_frame,
            text="Edit Script",
            command=self.edit_script,
            bg=BUTTON_BG_COLOR,
            fg=BUTTON_FG_COLOR,
            activebackground=BUTTON_ACTIVE_BG_COLOR,
            activeforeground=BUTTON_ACTIVE_FG_COLOR,
            relief="flat",
            highlightthickness=0
        )
        edit_button.pack(side="left", padx=5, pady=2)

        # Add the "Reload Script" button
        reload_button = tk.Button(
            button_frame,
            text="Reload Script",
            command=self.reload_script,
            bg=BUTTON_BG_COLOR,
            fg=BUTTON_FG_COLOR,
            activebackground=BUTTON_ACTIVE_BG_COLOR,
            activeforeground=BUTTON_ACTIVE_FG_COLOR,
            relief="flat",
            highlightthickness=0
        )
        reload_button.pack(side="left", padx=5, pady=2)

        # Start the script execution
        self.run_script()

    def close(self):
        """Clean up resources associated with the tab."""
        self.process_tracker.terminate_process(self.tab_id)
        super().close()

    def run_script(self):
        """Run the script using ProcessTracker."""
        # Build the command
        command = [str(pythonw_path.resolve()), "-u", str(self.script_path.resolve())]

        # Start the process with the updated environment
        self.process_tracker.start_process(
            tab_id=self.tab_id,
            command=command,
            stdout_callback=self._insert_stdout,
            stderr_callback=self._insert_stderr,
            script_tab=self,
            script_name=self.script_path.name,
        )

    # TODO may not be best place for these
    def _insert_stdout(self, text):
        self._insert_text(text)

    def _insert_stderr(self, text):
        self._insert_text(text)

    def _insert_text(self, text):
        """Parse and insert text with ANSI color handling."""
        if self.text_widget and self.text_widget.winfo_exists():
            parsed_segments = parse_ansi_colors(text)
            self.frame.after(0, lambda: self._safe_insert_segments(parsed_segments))

    def ensure_tag(self, color=None, bold=False):
        """
        Ensure that a text tag for the given color and bold style is defined in the widget.
        """
        # Generate a unique tag name based on color and bold
        tag = f"color-{color}-bold-{bold}" if color else f"bold-{bold}"

        if tag not in self.text_widget.tag_names():
            tag_config = {}

            # Set the foreground color if specified
            if color:
                tag_config["foreground"] = color

            # Set the font explicitly for bold or normal text
            if bold:
                tag_config["font"] = self.font_bold
            else:
                tag_config["font"] = self.font_normal

            # Configure the tag in the widget
            self.text_widget.tag_configure(tag, **tag_config)

        return tag

    def _safe_insert_segments(self, segments):
        """Safely insert text segments with colors and bold styles into the text widget."""
        try:
            for segment, style in segments:
                color = style.get("color")  # Extract the color
                bold = style.get("bold", False)  # Extract bold

                if color or bold:
                    # Ensure the tag exists for this combination of color and bold
                    tag = self.ensure_tag(color=color, bold=bold)
                    self.text_widget.insert(tk.END, segment, tag)
                else:
                    # Insert plain text with no formatting
                    self.text_widget.insert(tk.END, segment)

            self.text_widget.see(tk.END)  # Scroll to the end
        except TclError as e:
            print(f"[WARNING] _safe_insert_segments: TclError encountered: {e}")
        except Exception as e:
            print(f"[ERROR] _safe_insert_segments: Unexpected error: {e}")

    def _safe_insert(self, text):
        """Safely insert text into the text widget"""
        try:
            if self.text_widget and self.text_widget.winfo_exists():
                self.text_widget.insert(tk.END, text)
                self.text_widget.see(tk.END)  # Scroll to the end
        except TclError as e:
            print(f"[WARNING] _safe_insert: TclError encountered while writing to the widget: {e}")
        except Exception as e:
            print(f"[ERROR] _safe_insert: Unexpected exception while writing to the widget: {e}")

    def edit_script(self):
        """Open the script in VSCode for editing."""
        try:
            subprocess.Popen([str(vscode_path.resolve()), str(self.script_path)])
            self.insert_output(f"Opening script {self.script_path} for editing in VS Code...\n")
        except Exception as e:
            self.insert_output(f"Error opening script for editing: {e}\n")

    def reload_script(self):
        """Reload the script by terminating and restarting the process."""
        print(f"[INFO] Reloading script for Tab ID: {self.tab_id}")

        def _reload():
            self.process_tracker.terminate_process(self.tab_id)

            # Clear the text widget (output page)
            if self.text_widget and self.text_widget.winfo_exists():
                self.text_widget.delete('1.0', tk.END)

            self.run_script()

        self.process_tracker.scheduler(0, _reload)  # Schedule the reload process

    def handle_keypress(self, event):
        """Handle keypress events."""
        if not self.is_active:
            return

        key = event.char or ""  # Get the character, default to empty for non-character keys
        if key == "\r":
            key = "\n"  # Handle Enter key

        # Add input to the queue
        if self.tab_id in self.process_tracker.processes:
            input_queue = self.process_tracker.queues[self.tab_id]["stdin"]
            try:
                input_queue.put_nowait(key)  # Non-blocking enqueue
                self.insert_output(key)  # Optionally echo input in the GUI
            except queue.Full:
                self.insert_output("[WARNING] Input queue is full. Input dropped.\n")


class PerfTab(Tab):
    """PerfTab - represents performance tab for monitoring performance of scripts"""
    def __init__(self, title, process_tracker):
        super().__init__(title)
        self.process_tracker = process_tracker
        self.performance_metrics_open = True
        self.text_widget = None
        self.cpu_stats = {}

    def build_content(self):
        """Add widgets to the performance tab."""
        self.text_widget = scrolledtext.ScrolledText(
            self.frame, wrap="word",
            bg=TEXT_WIDGET_BG_COLOR, fg=TEXT_WIDGET_FG_COLOR,
            insertbackground=TEXT_WIDGET_INSERT_COLOR
        )
        self.text_widget.pack(expand=True, fill="both")
        self.start_monitoring()

    def start_monitoring(self):
        """Start monitoring performance metrics"""
        if not self.performance_metrics_open:
            return

        # Update metrics
        metrics_text = self.generate_metrics_text()
        self.refresh_performance_metrics(metrics_text)

        # Schedule the next update after 1000 ms (1 second)
        self.frame.after(1000, self.start_monitoring)

    def refresh_performance_metrics(self, text):
        """Refresh the performance metrics text widget."""
        if self.text_widget and self.text_widget.winfo_exists():
            self.text_widget.delete('1.0', tk.END)
            self.text_widget.insert(tk.END, text)

    def generate_metrics_text(self):
        """Generate a text representation of performance metrics."""
        metrics = []
        processes = self.process_tracker.list_processes()

        if not processes:
            return "No scripts are currently running."

        total_cores = psutil.cpu_count(logical=True)

        # Ensure cpu_stats exists for tracking cumulative CPU stats
        if not hasattr(self, 'cpu_stats'):
            self.cpu_stats = {}

        for tab_id, process_info in processes.items():
            process = process_info.get("process")
            script_name = process_info.get("script_name", "Unknown")

            if process and process.pid:
                try:
                    proc = psutil.Process(process.pid)
                    if proc.is_running():
                        # Initialize stats for new processes
                        if tab_id not in self.cpu_stats:
                            self.cpu_stats[tab_id] = {"cumulative_cpu": 0, "count": 0}

                        # Calculate current CPU usage (normalized as a percentage of total cores)
                        cpu_usage = proc.cpu_percent(interval=0.1) / total_cores
                        memory_usage = proc.memory_info().rss / (1024 ** 2)  # Convert to MB

                        # Update cumulative stats
                        self.cpu_stats[tab_id]["cumulative_cpu"] += cpu_usage
                        self.cpu_stats[tab_id]["count"] += 1

                        # Calculate average CPU usage
                        avg_cpu_usage = (
                            self.cpu_stats[tab_id]["cumulative_cpu"]
                                / self.cpu_stats[tab_id]["count"]
                        )

                        # Add metrics to the output
                        metrics.append(
                            f"Script: {script_name}\n"
                            f"  PID: {process.pid}\n"
                            f"  Current CPU Usage: {cpu_usage:.2f}%\n"
                            f"  Average CPU Usage: {avg_cpu_usage:.2f}%\n"
                            f"  Memory Usage: {memory_usage:.2f} MB\n"
                        )
                    else:
                        metrics.append(f"Script: {script_name}\n  Status: Not Running\n")
                except psutil.NoSuchProcess:
                    metrics.append(f"Script: {script_name}\n  Status: Terminated\n")
            else:
                metrics.append(f"Script: {script_name}\n  Status: Not Running\n")

        return "\n".join(metrics)

    def stop_performance_monitoring(self):
        """Stop monitoring performance metrics."""
        self.performance_metrics_open = False

    def create_metrics_widget(self):
        """Create and add a text widget for displaying performance metrics."""
        text_widget = tk.Text(self.frame, wrap="word")
        text_widget.pack(expand=True, fill="both")
        return text_widget

class ScriptLauncherApp:
    """Represents the main application for launching and managing scripts."""
    def __init__(self, root):
        # Root Window Setup
        self.root = root
        self.configure_root()

        # Toolbar Setup
        self.create_toolbar()

        self.tab_manager = TabManager(root, self.root.after)

        # Bind Events
        self.bind_events()

        # Event for shutdown
        self.shutdown_event = Event()

        self.process_tracker = ProcessTracker(scheduler=self.root.after,
                                              shutdown_event=self.shutdown_event)

        # Autoplay Scripts
        self.autoplay_script_group()

        # Bind key press globally - for script keyboard input support
        self.root.bind("<Key>", self.on_key_press)

    def configure_root(self):
        """Configure the main root window."""
        self.root.title("Python Script Launcher")
        self.root.geometry("1000x600")
        self.root.configure(bg=DARK_BG_COLOR)

    def create_toolbar(self):
        """Create the top toolbar with action buttons."""
        self.toolbar = tk.Frame(self.root, bg=DARK_BG_COLOR)
        self.toolbar.pack(side="top", fill="x", padx=5, pady=5)

        # Add buttons to the toolbar with their placement side
        buttons = [
            ("Run Script", self.select_and_run_script, "left"),
            ("Load Script Group", self.load_script_group, "right"),
            ("Save Script Group", self.save_script_group, "right"),
            ("Performance Metrics", self.open_performance_metrics_tab, "right"),
        ]

        for text, command, side in buttons:
            button = tk.Button(
                self.toolbar, text=text, command=command,
                bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR,
                activebackground=BUTTON_ACTIVE_BG_COLOR,
                activeforeground=BUTTON_ACTIVE_FG_COLOR,
                relief="flat", highlightthickness=0
            )
            button.pack(side=side, padx=5, pady=2)

    def select_and_run_script(self):
        """Opens file dialog for script selection and then runs it"""
        file_path = filedialog.askopenfilename(title="Select Python Script",
                                               filetypes=[("Python Files", "*.py")])
        if not file_path:
            print("[INFO] No file selected. Operation cancelled.")
            return
        self.load_script(Path(file_path))

    def load_script(self, script_path):
        """Load and run a script in a new ScriptTab."""
        script_tab = ScriptTab(
            title=script_path.name,
            script_path=script_path,
            process_tracker=self.process_tracker
        )
        self.tab_manager.add_tab(script_tab)

    def bind_events(self):
        # Override close window behavior
        self.root.protocol("WM_DELETE_WINDOW", self.on_shutdown)

    def open_performance_metrics_tab(self):
        """Open a new performance metrics tab."""
        perf_tab = PerfTab(
            title="Performance Metrics",
            process_tracker=self.process_tracker
        )
        self.tab_manager.add_tab(perf_tab)

    def autoplay_script_group(self):
        """
        Automatically load a script group file named '_autoplay.script_group' located in the
        'Scripts' directory.
        """
        # Set path to '_autoplay.script_group' within the Scripts directory
        autoplay_path = scripts_path / "_autoplay.script_group"

        # Check if the file exists and load it if it does
        if autoplay_path.exists():
            print(f"[INFO] Autoplay: Loading script group from {autoplay_path}")
            self.load_script_group_from_path(autoplay_path)
        else:
            print("[INFO] Autoplay: No '_autoplay.script_group' file found at startup. "
                  "Skipping autoplay.")

    def save_script_group(self):
        """Save the currently open tabs (scripts) to a .script_group file with relative paths."""
        file_path = filedialog.asksaveasfilename(
            title="Save Script Group",
            defaultextension=".script_group",
            filetypes=[("Script Group Files", "*.script_group")]
        )

        if not file_path:
            return

        group_dir = Path(file_path).parent

        # Collect script paths from all ScriptTabs
        script_paths = []
        for tab_frame_id in self.tab_manager.notebook.tabs():
            for _, tab in self.tab_manager.tabs.items():
                if tab.frame and str(tab.frame) == tab_frame_id:
                    if isinstance(tab, ScriptTab):
                        relative_path = os.path.relpath(tab.script_path, group_dir)
                        script_paths.append(relative_path)
                    break

        # Write the relative paths to the .script_group file
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(f"{path}\n" for path in script_paths)

    def load_script_from_path(self, script_path_str):
        """Load and run a script from a specified file path."""
        script_path = Path(script_path_str)

        if not script_path.exists():
            print(f"[ERROR] Script '{script_path}' not found.")
            return

        # Add the script as a new tab
        script_tab = ScriptTab(
            title=script_path.name,
            script_path=script_path,
            process_tracker=self.process_tracker
        )
        self.tab_manager.add_tab(script_tab)

    def load_script_group(self):
        """Prompt the user to select a .script_group file and load scripts from it."""
        file_path = filedialog.askopenfilename(
            title="Select Script Group",
            filetypes=[("Script Group Files", "*.script_group")]
        )
        if file_path:
            self.load_script_group_from_path(Path(file_path))

    def load_script_group_from_path(self, file_path):
        """Load scripts from the specified .script_group file and launch them in new tabs."""
        group_dir = file_path.parent

        if not file_path.exists():
            print(f"[ERROR] Script group file '{file_path}' not found.")
            return

        with open(file_path, 'r', encoding="utf-8") as f:
            script_paths = [group_dir / Path(line.strip())
                            for line in f.readlines() if line.strip()]

        # Use a set to avoid loading duplicate scripts
        loaded_scripts = set()

        for script_path in script_paths:
            absolute_path = script_path.resolve()
            if str(absolute_path) not in loaded_scripts:
                loaded_scripts.add(str(absolute_path))
                self.load_script_from_path(absolute_path)

    def on_shutdown(self):
        logging.info("Shutdown signal received. Triggering shutdown_event.")
        logging.debug(f"[DEBUG] on_shutdown shutdown_event ID: {id(self.shutdown_event)}")

        # Set shutdown_event which will trigger launcher shutdown
        self.shutdown_event.set()

    def on_close(self, callback=None):
        """Handle application shutdown."""
        print("[INFO] Shutting down application.")
        logging.info("Shutting down application")
        self.tab_manager.close_all_tabs()

        def finalize_shutdown():
            print("[INFO] Application closed successfully.")
            logging.info("finalize_shutdown()")
            if callback:
                callback()  # Execute the callback after shutdown is fully complete.

        logging.debug("Schedule: finalize shutdown")
        self.root.after(0, lambda: (self.root.destroy(), finalize_shutdown()))

    def on_key_press(self, event):
        """Route keypress events to the active tab if it supports keypress handling."""
        active_tab_id = self.tab_manager.current_tab_id
        if not active_tab_id:
            print("[INFO] No active tab to handle keypress.")
            return  # No active tab to route input to

        # Get the active tab
        active_tab = self.tab_manager.tabs.get(active_tab_id)
        if not active_tab:
            print(f"[ERROR] No tab found for active_tab_id: {active_tab_id}")
            return

        # Check if the active tab has a 'handle_keypress' method
        if callable(getattr(active_tab, "handle_keypress", None)):
            active_tab.handle_keypress(event)
        else:
            print(f"[INFO] Active tab ID {active_tab_id} does not support keypress handling.")

class ProcessTracker:
    """Manages runtime of collection of processes"""
    def __init__(self, scheduler, shutdown_event):
        self.processes = {}  # Maps tab_id to process metadata
        self.queues = {}  # Maps tab_id to queues for stdout and stderr
        self.scheduler = scheduler  # Store the scheduler
        self.script_name = None
        self.queuefull_warning_issued = False

        self.shutdown_event = shutdown_event  # Store the shutdown event

    def start_process(self, tab_id, command, stdout_callback, stderr_callback, script_tab, script_name=None):
        """Start a subprocess and manage its I/O."""

        # Add Lib path
        lib_path = str((Path(__file__).resolve().parents[1] / "Lib").resolve())
        custom_env = os.environ.copy()  # Create a local environment copy
        custom_env["PYTHONPATH"] = f"{lib_path};{custom_env.get('PYTHONPATH', '')}"

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=custom_env,
            )
            print(f"[INFO] Started process: {script_name}, PID: {process.pid}, Tab ID: {tab_id}")

            self.script_name = script_name
            self.processes[tab_id] = {
                "process": process,
                "script_name": script_name or "Unknown",
                "script_tab": script_tab}

            # Create queues for communication
            self.queues[tab_id] = {
                "stdout": queue.Queue(maxsize=1000),
                "stderr": queue.Queue(maxsize=1000),
                "stdin": queue.Queue(maxsize=1000),
                "stop_event": threading.Event()
            }

            # Start threads for stdout and stderr reading
            threading.Thread(
                target=self._read_output,
                args=(process.stdout, self.queues[tab_id]["stdout"], tab_id, "stdout"),
                daemon=True,
                name=f"StdoutThread-{tab_id}"
            ).start()

            threading.Thread(
                target=self._read_output,
                args=(process.stderr, self.queues[tab_id]["stderr"], tab_id, "stderr"),
                daemon=True,
                name=f"StderrThread-{tab_id}"
            ).start()

            # Start a thread for writing to stdin
            threading.Thread(
                target=self._write_input,
                args=(process.stdin, self.queues[tab_id]["stdin"], tab_id),
                daemon=True,
                name=f"StdinWriter-{tab_id}"
            ).start()

            # Start dispatcher threads to process queues and invoke callbacks
            threading.Thread(
                target=self._dispatch_queue,
                args=(self.queues[tab_id]["stdout"], stdout_callback),
                daemon=True,
                name=f"DispatcherStdout-{tab_id}"
            ).start()

            threading.Thread(
                target=self._dispatch_queue,
                args=(self.queues[tab_id]["stderr"], stderr_callback),
                daemon=True,
                name=f"DispatcherStderr-{tab_id}"
            ).start()

            # Start process monitoring
            self.schedule_process_check(tab_id)

        except Exception as e:
            print(f"[ERROR] Failed to start process for Tab ID {tab_id}: {e}")


    def _read_output(self, stream, q, tab_id, stream_name):
        """
        Read subprocess output with proper handling of lines and partial data.
        """
        print(f"[INFO] Starting output reader for {stream_name}, Tab ID: {tab_id}")
        print(f"[DEBUG] Type of stream: {type(stream)}")  # Log the type of the stream

        fd = stream.fileno()  # Get the file descriptor for low-level reads
        buffer = ""  # Accumulate partial lines
        last_flushed_partial = None  # Track the last flushed partial line

        try:
            while not self.queues[tab_id]["stop_event"].is_set():
                try:
                    # Attempt to read a chunk of data (64 bytes at a time)
                    chunk = os.read(fd, 64).decode("utf-8")
                    if not chunk:  # EOF or no data available
                        time.sleep(0.01)
                        continue

                    buffer += chunk

                    # Debug: Log received chunk and updated buffer
                    print(f"[DEBUG] Chunk received ({len(chunk)} chars): {repr(chunk)}")
                    print(f"[DEBUG] Current buffer ({len(buffer)} chars): {repr(buffer)}")

                    # Process complete lines in the buffer
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        q.put_nowait(line + "\n")
                        print(f"[DEBUG] Line enqueued: {repr(line)}")
                        last_flushed_partial = None  # Reset partial tracking

                    # Handle partial line (e.g., prompts or incomplete output)
                    if buffer and buffer != last_flushed_partial:
                        q.put_nowait(buffer)
                        print(f"[DEBUG] Partial buffer enqueued: {repr(buffer)}")
                        last_flushed_partial = buffer

                        # Clear the buffer after enqueueing partial data
                        buffer = ""

                except BlockingIOError:
                    # No data available yet; pause briefly to avoid busy-waiting
                    time.sleep(0.01)
                except Exception as read_error:
                    # Catch unexpected read errors and log them
                    print(f"[ERROR] Exception while reading {stream_name}: {read_error}")
                    break

        except Exception as loop_error:
            # Log any unexpected errors that terminate the loop
            print(f"[ERROR] Unexpected error in output reader for {stream_name}: {loop_error}")

        finally:
            # Handle cleanup: flush remaining buffer and signal end of stream
            if buffer and buffer != last_flushed_partial:
                q.put_nowait(buffer)
                print(f"[DEBUG] Final buffer flushed: {repr(buffer)}")
            q.put(None)  # Signal end of stream to the queue

            try:
                stream.close()  # Close the stream gracefully
            except Exception as close_error:
                print(f"[WARNING] Error closing {stream_name}: {close_error}")

            print(f"[INFO] Output reader for {stream_name} finished, Tab ID: {tab_id}")

    def _write_input(self, stdin, input_queue, tab_id):
        """Write input from the queue to the subprocess's stdin."""
        try:
            while not self.queues[tab_id]["stop_event"].is_set():
                try:
                    input_data = input_queue.get(timeout=1)  # Block until input is available
                    if input_data is None:  # Sentinel for EOF
                        break
                    stdin.write(input_data)
                    stdin.flush()  # Ensure immediate delivery to the subprocess
                except queue.Empty:
                    continue  # Check for stop_event periodically
        except Exception as e:
            print(f"[ERROR] Failed to write to stdin for Tab ID {tab_id}: {e}")
        finally:
            try:
                stdin.close()
            except Exception as e:
                print(f"[WARNING] Failed to close stdin for Tab ID {tab_id}: {e}")

    def _dispatch_queue(self, q, callback):
        """Consume items from the queue and invoke the callback."""
        print("[INFO] Starting dispatcher thread.")
        while True:
            try:
                line = q.get(timeout=1)  # Avoid indefinite blocking
                print(f"[DEBUG] Dispatcher received line from queue: {line}")
            except queue.Empty:
                # Check for shutdown periodically
                if any(queue_data["stop_event"].is_set() for queue_data in self.queues.values()):
                    print("[INFO] Dispatcher stopping due to stop event.")
                    logging.debug("Dispatcher stopping due to stop event.")
                    break
                continue

            if line is None:  # Sentinel for end-of-stream
                print("[INFO] Dispatcher received EOF sentinel. Exiting.")
                break

            # Use the provided scheduler to safely invoke the callback
            self.scheduler(0, lambda l=line: callback(l))

    def schedule_process_check(self, tabid):
        """Schedule a periodic check for process termination."""
        self.scheduler(2000, lambda: self.check_termination(tabid))

    def check_termination(self, tab_id):
        """Check if the process has terminated and notify the associated ScriptTab."""
        metadata = self.processes.get(tab_id)
        if not metadata:
            return  # Process already cleaned up or not found

        process = metadata["process"]
        script_tab = metadata.get("script_tab")
        script_name = metadata.get("script_name", "Unknown")

        if process.poll() is not None:  # Process has stopped
            exit_code = process.poll()

            # Notify the ScriptTab directly
            try:
                if script_tab:
                    if exit_code == 0:
                        script_tab.insert_output(f"[INFO] Script '{script_name}' completed successfully.\n")
                    else:
                        script_tab.insert_output(f"[ERROR] Script '{script_name}' terminated unexpectedly with code {exit_code}.\n")

                # Clean up process metadata
                self.processes.pop(tab_id, None)
            except Exception as e:
                print(f"[ERROR] Error notifying ScriptTab for Tab ID {tab_id}: {e}")
            return

        # Reschedule the next check
        self.schedule_process_check(tab_id)

    def terminate_process(self, tab_id):
        """Terminate the process."""
        metadata = self.processes.pop(tab_id, None)
        if not metadata:
            return

        process = metadata["process"]
        if process.poll() is None:  # Still running
            process.terminate()
        if tab_id in self.queues:
            self.queues[tab_id]["stdout"].put("[INFO] Process terminated by user.\n")
            self.queues[tab_id]["stdout"].put(None)  # Final EOF sentinel
            del self.queues[tab_id]

    def terminate_process(self, tab_id):
        """Terminate the process for a given tab ID."""
        print(f"[INFO] Attempting to terminate process for Tab ID: {tab_id}")
        logging.info("[INFO] Attempting to terminate process for Tab ID: %s", tab_id)

        metadata = self.processes.pop(tab_id, None)
        if not metadata:
            print(f"[INFO] No process found for Tab ID {tab_id}.")
            return

        process = metadata["process"]
        if process.poll() is None:  # Still running
            print(f"[INFO] Terminating process for Tab ID {tab_id} (PID {process.pid}).")
            self._terminate_process_tree(process.pid)

        # Close the process's I/O streams
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

        # Signal threads to stop
        if tab_id in self.queues:
            self.queues[tab_id]["stop_event"].set()
            del self.queues[tab_id]

        print(f"[INFO] Process for Tab ID {tab_id} terminated.")

    def _terminate_process_tree(self, pid, timeout=5, force=True):
        """Terminate a process tree."""
        print(f"[INFO] Terminating process tree for PID: {pid}")
        logging.info("[INFO] Terminating process tree for PID: %s", pid)
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            logging.info(f"Process with PID {pid} already terminated. "
                  "Checking for orphaned children.")
            # Attempt to clean up orphaned child processes
            self._terminate_orphaned_children(pid)
            return
        except Exception as e:
            print(f"[ERROR] Failed to initialize process PID {pid}: {e}")
            return

        try:
            children = parent.children(recursive=True)
            logging.info(f"Found {len(children)} child processes for PID {pid}."
                  f"Terminating children first.")

            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    logging.warning(f"NoSuchProcess {child.pid}.")
                    continue
                except psutil.AccessDenied:
                    logging.warning(f"Access denied to terminate child PID {child.pid}.")

            # Wait for all children to terminate
            _, alive = psutil.wait_procs(children, timeout=timeout)

            if alive and force:
                logging.info(f"[WARNING] {len(alive)} child processes did not terminate. "
                      "Forcing termination.")
                for proc in alive:
                    try:
                        logging.info("proc.kill()")
                        proc.kill()
                    except psutil.NoSuchProcess:
                        logging.warning(f"NoSuchProcess")
                        continue
                    except psutil.AccessDenied:
                        logging.info(f"[WARNING] Access denied to kill child PID {proc.pid}.")

            # Terminate the parent process
            parent.terminate()
            _, alive = psutil.wait_procs([parent], timeout=timeout)

            if alive and force:
                print(f"[WARNING] Parent process PID {parent.pid} did not terminate. Forcing kill.")
                for proc in alive:
                    try:
                        proc.kill()
                        logging.info("proc.kill()")
                    except psutil.NoSuchProcess:
                        logging.warning(f"NoSuchProcess")
                        continue
                    except psutil.AccessDenied:
                        logging.warning(f"Access denied to kill PID {proc.pid}.")

            #logging.info("Made it to end - terminate process tree")

        except psutil.NoSuchProcess:
            print(f"[INFO] Parent process PID {pid} already terminated during cleanup.")
        except Exception as e:
            print(f"[ERROR] Unexpected error terminating process tree for PID {pid}: {e}")

    def _terminate_orphaned_children(self, parent_pid):
        """Terminate orphaned children of a non-existent parent process."""
        try:
            for proc in psutil.process_iter(attrs=["pid", "ppid"]):
                if proc.info["ppid"] == parent_pid:
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except psutil.NoSuchProcess:
                        continue
                    except Exception as e:
                        print(f"[ERROR] Failed to terminate orphaned child PID"
                              f"{proc.info['pid']}: {e}")
        except Exception as e:
            print(f"[ERROR] Error scanning for orphaned children of PID {parent_pid}: {e}")

    def list_processes(self) -> Dict[int, Dict]:
        """List all tracked processes and their metadata."""
        return {
            tab_id: {
                "process": metadata["process"],
                "script_name": metadata.get("script_name", "Unknown"),
            }
            for tab_id, metadata in self.processes.items()
        }

def monitor_shutdown_pipe(pipe_name, shutdown_event):
    """Monitor the named pipe for shutdown signals and heartbeats."""
    logging.info("Monitoring shutdown pipe in subprocess. Pipe: %s", pipe_name)

    HEARTBEAT_TIMEOUT = 5  # Timeout in seconds to detect missed heartbeats
    last_heartbeat_time = time.time()  # Track the last heartbeat time

    def pipe_reader():
            """Threaded pipe reader."""
            nonlocal last_heartbeat_time
            try:
                with open(pipe_name, "r", encoding="utf-8") as pipe:
                    logging.info("Successfully connected to the shutdown pipe.")
                    while not shutdown_event.is_set():
                        try:
                            # Read line from pipe (blocking)
                            line = pipe.readline().strip()
                            if line:
                                if line == "shutdown":
                                    logging.info("Shutdown signal received in subprocess.")
                                    shutdown_event.set()
                                    break
                                elif line == "HEARTBEAT":
                                    #logging.debug("Heartbeat received.")
                                    last_heartbeat_time = time.time()  # Update last heartbeat time
                        except Exception as e:
                            logging.error("Exception while reading pipe: %s", e)
                            break

                        # Sleep briefly to prevent tight loop
                        time.sleep(0.1)
            except Exception as e:
                logging.error("Failed to monitor shutdown pipe: %s", e)
            finally:
                logging.info("Exiting pipe_reader thread.")

    # Start the reader thread
    reader_thread = threading.Thread(target=pipe_reader, daemon=True)
    reader_thread.start()

    # Wait for shutdown event while pipe read runs in thread
    while not shutdown_event.is_set():
        # Check for heartbeat timeout
        if time.time() - last_heartbeat_time > HEARTBEAT_TIMEOUT:
            logging.info("!=================== Heartbeat timeout detected ===================!")
            shutdown_event.set()
            break
        time.sleep(0.5)

    logging.debug("join reader_thread")
    reader_thread.join(timeout=1)  # Allow the thread to exit

def main():
    """Main entry point for the script."""
    args = sys.argv
    logging.debug("args=%s", args)

    # Parse the --shutdown-pipe argument
    shutdown_pipe = None
    if "--shutdown-pipe" in args:
        shutdown_pipe = args[args.index("--shutdown-pipe") + 1]
        logging.debug("shutdown_pipe=%s", shutdown_pipe)
    else:
        logging.info("No --shutdown-pipe argument provided. Skipping pipe-based shutdown logic.")

    # Add lib_path to PYTHONPATH
    lib_path = str((Path(__file__).resolve().parents[1] / "Lib").resolve())
    if lib_path not in os.environ.get("PYTHONPATH", "").split(";"):
        os.environ["PYTHONPATH"] = f"{lib_path};{os.environ.get('PYTHONPATH', '')}"
        logging.info(f"Added '{lib_path}' to PYTHONPATH.")

    logging.info("Starting the application.")

    # Start app
    root = ThemedTk(theme="black")
    app = ScriptLauncherApp(root)

    # Start the shutdown monitoring subprocess if a pipe is provided
    monitor_process = None
    if shutdown_pipe:
        monitor_process = Process(target=monitor_shutdown_pipe,
                                  args=(shutdown_pipe, app.shutdown_event))
        monitor_process.start()
        logging.info("Started shutdown monitoring process.")

    try:
        # Periodically check for the shutdown_event
        def check_shutdown():
            if app.shutdown_event.is_set():
                logging.info("Shutdown event detected in main application.")
                app.on_close()
                return
            root.after(100, check_shutdown)  # Recheck every 100ms

        # Start monitoring shutdown_event
        root.after(100, check_shutdown)
        root.after(100, lambda: DarkmodeUtils.apply_dark_mode(root))

        root.mainloop()

        logging.info("Tkinter main loop has exited.")
    finally:
        logging.info("Finalizing application shutdown...")

        # Ensure subprocess cleanup
        if monitor_process:
            app.shutdown_event.set()  # Ensure the subprocess knows to exit
            logging.debug("Waiting for shutdown monitoring process to exit...")
            monitor_process.join(timeout=5)
            logging.debug("Past monitor_process join")
            if monitor_process.is_alive():
                logging.warning("Forcibly terminating the shutdown monitoring process.")
                monitor_process.terminate()

        logging.info("Application closed successfully.")
        logging.stop()

class DarkmodeUtils:
    """Utility class for handling dark mode UI features."""

    @staticmethod
    def is_windows_11():
        """Check if the system is running Windows 11 or later."""
        if hasattr(sys, 'getwindowsversion'):
            version = sys.getwindowsversion()
            # Windows 11 has major version 10 and build number >= 22000
            return (version.major == 10 and version.build >= 22000) or version.major > 10
        return False

    @staticmethod
    def dark_title_bar(hwnd):
        """Enable dark mode for the title bar."""
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)  # Use 1 to enable dark mode
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )
            if result == 0:
                print("[INFO] Dark mode applied successfully.")
            else:
                print(f"[ERROR] Failed to apply dark mode. Error code: {result}")
        except Exception as e:
            print(f"[ERROR] An exception occurred while applying dark mode: {e}")

    @staticmethod
    def is_valid_window(hwnd):
        """Check if the given HWND is a valid window handle."""
        return ctypes.windll.user32.IsWindow(hwnd) != 0

    @staticmethod
    def get_top_level_hwnd(hwnd):
        """Retrieve the top-level window handle."""
        GA_ROOT = 2  # Constant for the top-level ancestor
        return ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)

    @staticmethod
    def apply_dark_mode(root):
        """Apply dark mode to the top-level window of a Tkinter root."""
        try:
            if DarkmodeUtils.is_windows_11():
                hwnd = int(root.winfo_id())
                top_level_hwnd = DarkmodeUtils.get_top_level_hwnd(hwnd)
                if not DarkmodeUtils.is_valid_window(top_level_hwnd):
                    print("[ERROR] Invalid top-level window handle.")
                    return
                print(f"Applying dark mode to Top-Level HWND: {top_level_hwnd}")
                DarkmodeUtils.dark_title_bar(top_level_hwnd)
                ctypes.windll.user32.RedrawWindow(top_level_hwnd, None, None, 0x85)
        except Exception as e:
            print(f"[ERROR] apply_dark_mode: An exception occurred while applying dark mode: {e}")

if __name__ == "__main__":
    main()
