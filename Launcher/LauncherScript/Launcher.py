# Launcher.py - main launcher app script for MSFSPyScriptManager

print("---Launcher.py STARTING---")

import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
from multiprocessing import Process, Event
from pathlib import Path
from tkinter import messagebox
from typing import Dict
import ctypes

from threading import Lock

import pstats

import numpy as np
from parse_ansi import AnsiParser

import tkinter as tk
from tkinter import filedialog, scrolledtext, TclError
from tkinter import ttk

import psutil
import re
from ttkthemes import ThemedTk

from ordered_logger import OrderedLogger

import faulthandler
import traceback

import signal
import keyboard

# Add parent directory so Lib path can be found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from Lib.settings_changer import JsonSaveEditor
from Lib.dark_mode import DarkmodeUtils

# Path to the WinPython Python executable and VS Code.exe
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parents[1]
python_path = project_root / "WinPython" / "python-3.13.0rc1.amd64" / "python.exe"
pythonw_path = python_path.with_name("pythonw.exe")
vscode_path = project_root / "WinPython" / "VS Code.exe"
scripts_path = project_root / "Scripts"
data_path = project_root / "Data"

# Define color constants
DARK_BG_COLOR = "#2E2E2E"
BUTTON_BG_COLOR = "#444444"
BUTTON_FG_COLOR = "#EEEEEE"
BUTTON_ACTIVE_BG_COLOR = "#666666"
BUTTON_ACTIVE_FG_COLOR = "#FFFFFF"
TEXT_WIDGET_BG_COLOR = "#171717"
TEXT_WIDGET_FG_COLOR = "#FFFFFF"
TEXT_WIDGET_INSERT_COLOR = "#FFFFFF"
FRAME_BG_COLOR = "#2E2E2E"

# Delay load between scripts
SCRIPT_LOAD_DELAY_MS = 20

# Configure logging globally
logger = OrderedLogger(
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
        self.tabid = None

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

    def on_tab_activated(self):
        pass

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
        self.next_tab_id = 0        # Counter for unique tab IDs
        self.active_tab_id = 0      # Counter for selected tab id

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

        # Allows ctrl-tab to work
        self.notebook.enable_traversal()

    def on_tab_change(self, event):
        """Update active tab state."""

        # Probably paranoid to call with scheduler as notebook event
        def _update_tab_state():
            """Perform the actual tab state update on the main thread."""
            selected_frame = self.notebook.nametowidget(self.notebook.select())

            # Safely update tabs
            for tab_id, tab in self.tabs.items():
                if tab.frame == selected_frame:
                    tab.is_active = True
                    self.active_tab_id = tab_id
                    tab.on_tab_activated()
                else:
                    tab.is_active = False

        self.scheduler(0, _update_tab_state)

    def configure_notebook(self):
        """Configure notebook style and behavior."""
        style = ttk.Style()
        style.configure('TNotebook', padding=[0, 0], background=DARK_BG_COLOR)
        style.configure('TNotebook.Tab', padding=[5, 2])
        style.configure('TFrame', background=DARK_BG_COLOR)
        style.configure('TNotebook.Tab', foreground=BUTTON_FG_COLOR)

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
        """Swap two tabs in the notebook and update their internal state."""
        if index1 == index2:
            print("[DEBUG] Swap not needed: Dragged tab is already in the correct position.")
            return

        # Get all tabs as a list of frames
        tabs_list = self.notebook.tabs()
        tab1_frame = tabs_list[index1]
        tab2_frame = tabs_list[index2]

        print(f"[DEBUG] Swapping tab frames: {tab1_frame} <-> {tab2_frame}")

        # Swap the positions in the notebook widget
        self.notebook.insert(index2, tab1_frame)
        self.notebook.insert(index1, tab2_frame)

        print(f"[DEBUG] Tabs swapped successfully. Updated tabs: {self.tabs}")

    def generate_tab_id(self):
        """Generate a unique tab ID and log the caller and its caller."""
        self.next_tab_id += 1

        print(f"Generated new tab id: {self.next_tab_id} ")
        return self.next_tab_id

    def add_tab(self, tab):
        """Add a new tab to the notebook."""

        # Extract the caller function from the call stack
        stack = traceback.extract_stack()
        if len(stack) > 2:  # Ensure there's at least one caller before `add_tab`
            caller_info = stack[-3]  # Get the caller before `_add_tab` scheduling
            caller_name = f"{caller_info.name} (at {caller_info.filename})"
        else:
            caller_name = "Unknown"

        print(f"[DEBUG] add_tab called by: {caller_name}")

        def _add_tab():
            tab_id = self.generate_tab_id()  # Generate tab ID on the main thread
            tab.tab_id = tab_id
            tab.initialize_frame(self.notebook)
            tab.build_content()
            self.notebook.add(tab.frame, text=tab.title)
            self.tabs[tab_id] = tab
            self.notebook.select(tab.frame)
            if hasattr(tab, "on_tab_activated"):
                tab.on_tab_activated()

        self.scheduler(0, _add_tab)  # Schedule the entire operation on the main thread

    def close_tab(self, tab_id):
        """Close a tab and clean up resources."""
        def _close_tab():
            logger.debug("close_tab inner")
            print(f"[DEBUG] Type of self.tabs: {type(self.tabs)}")
            tab = self.tabs.pop(tab_id, None)
            if not tab:
                print(f"[WARNING] Tab with ID {tab_id} not found.")
                return
            tab.close()

        logger.debug("Schedule: _close_tab")
        self.scheduler(0, _close_tab)  # Schedule operation on the main thread

    def close_all_tabs(self):
        """Close all tabs and clean up resources."""
        print("[INFO] Closing all tabs.")
        for tab_id in list(self.tabs.keys()):  # Copy keys to avoid runtime modification issues
            print(f"[INFO] Closing tab with ID {tab_id}.")
            self.close_tab(tab_id)
        print("[INFO] All tabs closed.")

    def close_active_tab(self):
        """Close the currently active tab."""
        current_tab = self.notebook.select()  # Get the currently selected tab

        if current_tab:
            # Find the tab ID corresponding to the current tab
            for tab_id, tab in self.tabs.items():
                if tab.frame and str(tab.frame) == current_tab:
                    self.close_tab(tab_id)  # Use the existing close_tab method
                    return
        else:
            print("[INFO] No active tab to close.")

    def reload_all_scripts(self):
        # Get all ScriptTabs
        script_tabs = [tab for tab in self.tabs.values() if isinstance(tab, ScriptTab) ]

        def reload_script_with_delay(index):
            """Reload a script tab with a slight delay."""
            tab = script_tabs[index]
            try:
                print(f"[INFO] Reloading script for tab '{tab.title}' (Index: {index}).")
                tab.reload_script()
            except Exception as e:
                print(f"[ERROR] Failed to reload script in tab '{tab.title}' (Index: {index}): {e}")

        # Schedule reloads with increasing delay
        for i, tab in enumerate(script_tabs):
            delay = i * SCRIPT_LOAD_DELAY_MS
            print(f"delay")
            self.scheduler(delay, reload_script_with_delay, i)

    def on_tab_right_click(self, event):
        def _close_tab_on_click():
            try:
                clicked_tab_index = self.notebook.index(f"@{event.x},{event.y}")

                # Get the actual frame name from the Notebook’s tab list
                frame_name = self.notebook.tabs()[clicked_tab_index]

                # Convert that string name to the actual frame widget
                frame = self.notebook.nametowidget(frame_name)

                # Now find which tab in self.tabs owns that frame
                for tab_id, tab in list(self.tabs.items()):
                    if tab.frame == frame:
                        self.close_tab(tab_id)
                        return
            except TclError:
                print("[ERROR] Right-click did not occur on a valid tab. Ignoring.")

        self.scheduler(0, _close_tab_on_click)

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
        self.script_name = script_path.name
        self.process_tracker:ProcessTracker = process_tracker

        # Define font settings
        self.font_normal = ("Consolas", 12)
        self.font_bold = ("Consolas", 12, "bold")

        self._ansi_parser = AnsiParser()

        # Text buffer
        self.text_buffer = []
        self.is_flushing = False

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
        self.button_frame = tk.Frame(self.frame, bg=FRAME_BG_COLOR)  # Apply dark background color
        self.button_frame.pack(side="bottom", fill="x", padx=5, pady=5)

        # Add the "Edit Script" button
        edit_button = tk.Button(
            self.button_frame,
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
            self.button_frame,
            text="Restart Script (F5)",
            command=self.reload_script,
            bg=BUTTON_BG_COLOR,
            fg=BUTTON_FG_COLOR,
            activebackground=BUTTON_ACTIVE_BG_COLOR,
            activeforeground=BUTTON_ACTIVE_FG_COLOR,
            relief="flat",
            highlightthickness=0
        )
        reload_button.pack(side="left", padx=5, pady=2)

         # Add the "Reload Script" button
        stop_button = tk.Button(
            self.button_frame,
            text="Stop Script",
            command=self.stop_script,
            bg=BUTTON_BG_COLOR,
            fg=BUTTON_FG_COLOR,
            activebackground=BUTTON_ACTIVE_BG_COLOR,
            activeforeground=BUTTON_ACTIVE_FG_COLOR,
            relief="flat",
            highlightthickness=0
        )
        stop_button.pack(side="left", padx=5, pady=2)

        # Bind F5 to reload
        #self.frame.bind("<F5>", lambda event: self.reload_script())
        self.text_widget.bind("<F5>", lambda event: self.reload_script())

        # Check metadata for any commands
        # This allows custom buttons to be assigned for each script
        script_metadata  = self.load_script_metadata()
        if len(script_metadata) > 0:
            self.process_commands(script_metadata)

        # Start the script execution
        self.run_script()

    def load_script_metadata(self, filename="script_metadata.json"):
        """Load script metadata for loaded script"""
        metadata_path = os.path.join(data_path, filename)

        if not os.path.exists(metadata_path):
            print(f"Error: Metadata file not found at {metadata_path}")
            return {}

        try:
            with open(metadata_path, "r", encoding="utf-8") as file:
                metadata = json.load(file)
                return metadata.get(self.script_name, {})  # Return only the section for the given script
        except json.JSONDecodeError as e:
            print(f"Error loading JSON: {e}")
            return {}

    def process_commands(self, script_metadata):
        """Process commands from script metadata"""
        commands = script_metadata.get("commands", [])
        for command in commands:
            command_name = command.get("command_name")
            command_arg = command.get("command_arg")
            description = command.get("description")

            if command_name == "open_settings_editor":
                button = tk.Button(
                    self.button_frame,
                    text=description,
                    command=lambda arg=command_arg: JsonSaveEditor(
                        os.path.normpath(os.path.join(project_root, arg.lstrip("/\\")))
                    ),
                    bg=BUTTON_BG_COLOR,
                    fg=BUTTON_FG_COLOR,
                    activebackground=BUTTON_ACTIVE_BG_COLOR,
                    activeforeground=BUTTON_ACTIVE_FG_COLOR,
                    relief="flat",
                    highlightthickness=0
                )
                button.pack(side="right", padx=0, pady=2)

    def close(self):
        """Clean up resources associated with the tab."""
        print(f"ScriptTab: close tabid={self.tabid}")
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
        """Buffer text for periodic insertion with ANSI color handling."""
        if not (self.text_widget and self.text_widget.winfo_exists()):
            return

        # Parse the ANSI colors and buffer the parsed segments
        parsed_segments = self._ansi_parser.parse_ansi_colors(text)
        self.text_buffer.extend(parsed_segments)

        # Start a flush operation if one is not already scheduled
        if not self.is_flushing:
            self.is_flushing = True
            self.frame.after(50, self._flush_text_buffer)

    def _flush_text_buffer(self):
        """Flush the buffered text into the Text widget."""
        if not (self.text_widget and self.text_widget.winfo_exists()):
            self.is_flushing = False
            return

        # Process all buffered segments
        segments_to_insert = self.text_buffer
        self.text_buffer = []  # Clear the buffer

        # Insert the segments into the Text widget
        self._safe_insert_segments(segments_to_insert)

        # Check if more data was added to the buffer while flushing
        if self.text_buffer:
            interval = self._calculate_flush_interval()
            self.frame.after(interval, self._flush_text_buffer)  # Reschedule flushing
        else:
            self.is_flushing = False

    def _calculate_flush_interval(self):
        """Determine the flush interval dynamically based on workload."""
        buffer_size = len(self.text_buffer)

        # Dynamic intervals - refresh less often with higher workloads
        if buffer_size > 100:  # High workload
            return 10
        elif buffer_size > 50:  # Medium workload
            return 25
        else:  # Low workload
            return 50

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

    def edit_script(self):
        """Open the script in VSCode for editing."""
        try:
            subprocess.Popen([str(vscode_path.resolve()), str(self.script_path)])
            self.insert_output(f"Opening script {self.script_path} for editing in VS Code...\n")
        except Exception as e:
            self.insert_output(f"Error opening script for editing: {e}\n")

    def reload_script(self, clear_text=True):
        """Reload the script by terminating and restarting the process."""
        print(f"[INFO] Reloading script for Tab ID: {self.tab_id}")

        def _reload():
            self.process_tracker.terminate_process(self.tab_id)

            # Clear the text widget (output page)
            if clear_text is True:
                if self.text_widget and self.text_widget.winfo_exists():
                    self.text_widget.delete('1.0', tk.END)

            self.run_script()

        self.process_tracker.scheduler(SCRIPT_LOAD_DELAY_MS, _reload)  # Schedule the reload process

    def stop_script(self):
        """Stop the running of the script"""
        self.process_tracker.terminate_process(self.tab_id)

    def handle_keypress(self, event):
        """Handle keypress events."""
        if not self.is_active:
            return

        key = event.char or ""  # Get the character, default to empty for non-character keys
        if key == "\r":
            key = "\n"  # Handle Enter key

        # Add input to the queue
        try:
            # Retrieve the correct process info
            process_info = self.process_tracker.processes.get(self.tab_id)
            if not process_info:
                return

            # Access the stdin_queue
            stdin_queue = process_info["stdin_queue"]

            # Add the key to the queue
            stdin_queue.put_nowait(key)  # Non-blocking enqueue

        except queue.Full:
            self.insert_output("[WARNING] Input queue is full. Input dropped.\n")
        except KeyError as e:
            self.insert_output(f"[ERROR] Missing key in process info: {e}\n")
        except Exception as e:
            self.insert_output(f"[ERROR] Unexpected error: {e}\n")

    def on_tab_activated(self):
        if self.text_widget and self.text_widget.winfo_exists():
            self.text_widget.focus_force()
        else:
            print("[ERROR] Text widget is not available for focus.")

class PerfTab(Tab):
    """PerfTab - represents performance tab for monitoring performance of scripts"""

    REFRESH_RATE_MS = 50
    MA_WINDOW_SEC = 2
    CALCULATED_MA_WINDOW = int((MA_WINDOW_SEC*1000) / REFRESH_RATE_MS)

    def __init__(self, title, process_tracker):
        super().__init__(title)
        self.process_tracker = process_tracker
        self.performance_metrics_open = True
        self.text_widget = None
        self.cpu_stats = {}
        self.process_objects = {}

    def build_content(self):
        """Add widgets to the performance tab."""
        self.text_widget = tk.Text(
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

        # Schedule the next update
        self.frame.after(self.REFRESH_RATE_MS, self.start_monitoring)

    def refresh_performance_metrics(self, text):
        """Refresh the performance metrics text widget."""
        if self.text_widget and self.text_widget.winfo_exists():
            current_yview = self.text_widget.yview()  # Store current scroll position

            # Replace all text but keep scroll position
            self.text_widget.delete("1.0", tk.END)  # Clear old content
            self.text_widget.insert("1.0", text)  # Insert new content at top

            # Restore previous scroll position
            self.text_widget.yview_moveto(current_yview[0])

    def generate_metrics_text(self):
        """Generate a text representation of performance metrics."""
        metrics = []
        processes = self.process_tracker.list_processes()

        if not processes:
            return "No scripts are currently running."

        # Ensure cpu_stats exists for tracking cumulative CPU stats
        if not hasattr(self, 'cpu_stats'):
            self.cpu_stats = {}

        for tab_id, process_info in processes.items():
            process = process_info.get("process")
            script_name = process_info.get("script_name", "Unknown")

            if process and process.pid:
                try:
                    # Reuse existing process object if available, else create a new one
                    if tab_id not in self.process_objects:
                        self.process_objects[tab_id] = psutil.Process(process.pid)

                    proc = self.process_objects[tab_id]

                    if proc.is_running():
                        # Initialize stats for new processes
                        if tab_id not in self.cpu_stats:
                            self.cpu_stats[tab_id] = {
                                "cumulative_cpu": 0.0,
                                "count": 0,
                                "short_ma": RingMovingAverage(self.CALCULATED_MA_WINDOW)
                            }

                        # Calculate current CPU usage (non-blocking, reusing process object)
                        cpu_usage = proc.cpu_percent(interval=None)
                        memory_usage = proc.memory_info().rss / (1024 ** 2)  # Convert to MB

                        # Update cumulative stats
                        self.cpu_stats[tab_id]["cumulative_cpu"] += cpu_usage
                        self.cpu_stats[tab_id]["count"] += 1
                        self.cpu_stats[tab_id]["short_ma"].add(cpu_usage)

                        # Calculate average CPU usage
                        avg_cpu_usage = (
                            self.cpu_stats[tab_id]["cumulative_cpu"]
                            / self.cpu_stats[tab_id]["count"]
                        )

                        short_ma = self.cpu_stats[tab_id]["short_ma"].get_average()

                        # Add metrics to the output
                        metrics.append(
                            f"Script: {script_name}\n"
                            f"  PID: {process.pid}\n"
                            f"  Current CPU Usage: {short_ma:.2f}%\n"
                            f"  Average CPU Usage: {avg_cpu_usage:.2f}%\n"
                            f"  Memory Usage: {memory_usage:.2f} MB\n"
                        )
                    else:
                        metrics.append(f"Script: {script_name}\n  Status: Not Running\n")
                        if tab_id in self.process_objects:
                            del self.process_objects[tab_id]
                except psutil.NoSuchProcess:
                    metrics.append(f"Script: {script_name}\n  Status: Terminated\n")
                    if tab_id in self.process_objects:
                        del self.process_objects[tab_id]
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

class CommandLineTab(Tab):
    """A tab that provides a terminal-like command-line interface."""
    def __init__(self, title, command_callback):
        super().__init__(title)
        self.output_widget = None
        self.input_entry = None
        self.process = None
        self.stop_event = threading.Event()
        self.command_callback = command_callback

        # Initialize the cached current working directory
        self.cached_cwd = scripts_path

        # Autocomplete state
        self.is_autocompleting = False
        self.cached_input = ""  # Tracks input at the start of the autocomplete cycle
        self.original_partial_path = ""  # Tracks the prefix for the current autocomplete cycle
        self.autocomplete_matches = []
        self.autocomplete_index = -1

        # Simple command history
        self.history = []
        self.history_index = -1

    def build_content(self):
        """Create the interactive terminal interface."""
        # Output display area
        consolas_font = ("Consolas", 12)

        # Create a frame to hold the text widget and scrollbar
        content_frame = tk.Frame(self.frame, bg=FRAME_BG_COLOR)
        content_frame.pack(expand=True, fill="both", padx=5, pady=5)

        # Create the ScrolledText widget without a built-in scrollbar
        self.output_widget = tk.Text(
            content_frame,
            wrap="word",
            bg=TEXT_WIDGET_BG_COLOR,
            fg=TEXT_WIDGET_FG_COLOR,
            state="normal",
            height=20,
            font=consolas_font
        )
        self.output_widget.pack(side="left", expand=True, fill="both", padx=5, pady=5)

        # Use a ttk.Scrollbar for styling compatibility
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=self.output_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_widget.configure(yscrollcommand=scrollbar.set)

        # Input area
        input_frame = tk.Frame(self.frame, bg=FRAME_BG_COLOR)
        input_frame.pack(fill="x", padx=5, pady=5)

        self.input_entry = tk.Entry(
            input_frame,
            bg=TEXT_WIDGET_BG_COLOR,
            fg=TEXT_WIDGET_FG_COLOR,
            insertbackground=TEXT_WIDGET_INSERT_COLOR,
            font=consolas_font
        )
        self.input_entry.pack(fill="x", padx=5, pady=5)

        self.input_entry.bind("<Return>", self.send_input)
        self.input_entry.bind("<KeyRelease>", self.on_user_input)
        self.input_entry.bind("<Tab>", self.autocomplete)
        self.input_entry.bind("<Up>", self.handle_up_arrow)
        self.input_entry.bind("<Down>", self.handle_down_arrow)
        self.input_entry.bind("<Control-c>", lambda event: self.handle_ctrl_c())

        self.input_entry.focus_set()

        # Start the shell process
        self.start_shell()

    def start_shell(self):
        """Start a persistent shell process in a hidden pseudo-console."""
        if self.process and self.process.isalive():
            self.insert_output("[INFO] Shell is already running.\n")
            return

        try:
            # Lazy load the winpty library
            import winpty
        except ImportError:
            self.insert_output(
                "[ERROR] The 'winpty' library is required to start the console. "
                "Please install it by running 'pip install pywinpty' in WinPython cmd prompt.\n"
            )
            return

        try:
            # Use the predefined WinPython path
            scripts_dir = str(scripts_path.resolve())

            # Build a custom environment inheriting from os.environ
            custom_env = os.environ.copy()
            winpython_bin = str((project_root / "WinPython" / "python-3.13.0rc1.amd64").resolve())

            # Ensure the WinPython binary and scripts folder are in PATH
            custom_env["PATH"] = f"{winpython_bin};{winpython_bin}\\Scripts;{custom_env.get('PATH', '')}"
            custom_env["PYTHONPATH"] = f"{winpython_bin};{custom_env.get('PYTHONPATH', '')}"
            custom_env["VIRTUAL_ENV"] = winpython_bin

            # Spawn a pseudo-console with the correct environment
            self.process = winpty.PtyProcess.spawn("cmd", cwd=scripts_dir, env=custom_env)
            threading.Thread(target=self._read_output, daemon=True).start()

            self.insert_output(f"[INFO] Shell started in {scripts_dir}. Type commands below.\n")
            self.run_shell_command("dir *.py")
        except Exception as e:
            self.insert_output(f"[ERROR] Failed to start shell: {e}\n")

    def on_user_input(self, event):
        """Reset autocomplete state for non-autocomplete keys."""
        # Ignore Tab (used for autocomplete)
        if event.keysym == "Tab":
            return

        # Reset autocomplete for all other keypresses
        self.is_autocompleting = False

    def send_input(self, event=None):
        """Capture and send user input to the shell process."""
        user_input = self.input_entry.get().strip()

        if not user_input:
            return  # Ignore empty input

        # Add the command to history
        self.history.append(user_input)
        self.history_index = len(self.history)  # Reset to “one past the end”

        # Parse the base command and arguments
        command_parts = user_input.split()
        base_command = command_parts[0]
        args = command_parts[1:]

        # Try to handle the command via `command_callback`
        success, message = self.command_callback(base_command, args, self.cached_cwd)
        if success:
            if message:
                self.insert_output(f"[INFO] {message}\n")
        else:
            # If not handled, send the command to the shell
            self.run_shell_command(user_input)

        # Clear the input field
        self.input_entry.delete(0, tk.END)

    def run_shell_command(self, command):
        """Send a command to the pseudo-console."""
        if not self.process or not self.process.isalive():
            self.insert_output("[ERROR] No active shell process to send commands to.\n")
            return

        try:
            # Write the command followed by a newline to simulate Enter
            self.process.write(command + "\r\n")
        except Exception as e:
            self.insert_output(f"[ERROR] Failed to send command to shell: {e}\n")

    def autocomplete(self, event):
        """Handle tab-completion logic."""
        # Get the current input and cursor position
        current_input = self.input_entry.get()
        cursor_position = self.input_entry.index(tk.INSERT)
        base_command, partial_path = self.parse_command(current_input[:cursor_position])

        # Start a new autocomplete cycle if not already active
        if not self.is_autocompleting:
            # New cycle: fetch matches and reset state
            self.original_partial_path = partial_path
            self.autocomplete_matches = self.get_autocomplete_matches(partial_path)
            self.autocomplete_index = -1
            self.is_autocompleting = True

            if not self.autocomplete_matches:
                self.insert_output("[INFO] No matches found.\n")
                self.is_autocompleting = False
                return "break"

        # Cycle through matches
        self.autocomplete_index = (self.autocomplete_index + 1) % len(self.autocomplete_matches)
        selected_match = self.autocomplete_matches[self.autocomplete_index]
        full_command = f"{base_command} {selected_match}" if base_command else selected_match

        # Programmatically update the input field with the selected match
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, full_command)
        self.input_entry.icursor(len(full_command))  # Place the cursor at the end

        return "break"

    def parse_command(self, command):
        """
        Parse the command to split the base command from the partial path.
        For example:
        - Input: "python te"
        - Output: ("python", "te")
        """
        print(f"[DEBUG] Parsing command: '{command}'")
        # Split the command into parts by spaces
        parts = command.rsplit(" ", 1)
        if len(parts) == 1:
            # No space in the command, treat the whole thing as the path
            base, path = "", parts[0]
        else:
            base, path = parts[0], parts[1]

        print(f"[DEBUG] Parsed result - Base: '{base}', Path: '{path}'")
        return base, path

    def get_autocomplete_matches(self, prefix):
        """Dynamically fetch files and directories matching the prefix, prioritizing files."""
        try:
            cwd = Path(self.cached_cwd)  # Use the cached working directory
            files_and_dirs = cwd.iterdir()  # List all files and directories

            # Perform case-insensitive matching
            matches = [
                f.name + ("/" if f.is_dir() else "")
                for f in files_and_dirs
                if f.name.lower().startswith(prefix.lower())
            ]

            # Sort matches: prioritize files, then directories
            matches.sort(key=lambda x: (x.endswith("/"), x.lower()))
            return matches
        except Exception as e:
            self.insert_output(f"[ERROR] Failed to list directory contents: {e}\n")
            return []

    def handle_up_arrow(self, event):
        """Cycle backward through command history."""
        if not self.history:
            return "break"  # No history to cycle

        if self.history_index > 0:
            self.history_index -= 1
        else:
            self.history_index = 0  # Ensure index doesn't go below 0

        # Fetch the command and update the input field
        cmd = self.history[self.history_index]
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, cmd)
        self.input_entry.icursor(len(cmd))  # Move cursor to the end

        return "break"

    def handle_down_arrow(self, event):
        """Cycle forward through command history."""
        if not self.history:
            return "break"  # No history to cycle

        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            cmd = self.history[self.history_index]
        else:
            # If at the end of history, clear the input field
            self.history_index = len(self.history)
            cmd = ""

        # Update the input field
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, cmd)
        self.input_entry.icursor(len(cmd))  # Move cursor to the end

        return "break"

    def debug_associated_processes(self):
        """Find and print all processes associated with the current process."""
        if not self.process or not self.process.pid:
            print("[ERROR] No process is currently running or the process PID is not set.")
            return

        try:
            pid = self.process.pid
            print(f"[DEBUG] Inspecting processes associated with PID: {pid}")

            # Get the parent process
            parent_process = psutil.Process(pid)
            print(f"[DEBUG] Parent Process: PID={parent_process.pid}, Name={parent_process.name()}, Status={parent_process.status()}")

            # Get all child processes
            children = parent_process.children(recursive=True)
            if not children:
                print(f"[DEBUG] No child processes found for PID={pid}.")
            else:
                print(f"[DEBUG] Found {len(children)} child processes:")
                for child in children:
                    print(f"  - Child PID={child.pid}, Name={child.name()}, Status={child.status()}")

        except psutil.NoSuchProcess:
            print(f"[ERROR] No process found with PID: {self.process.pid}. It may have exited.")
        except Exception as e:
            print(f"[ERROR] Unexpected error while inspecting processes: {e}")

    def handle_ctrl_c(self, target="child"):
        """
        Handle the Ctrl+C event to send SIGINT to the specified target.
        """
        if not self.process or not self.process.pid:
            print("[ERROR] No process is currently running or the process PID is not set.")
            return

        try:
            parent_pid = self.process.pid
            print(f"[DEBUG] Inspecting processes associated with PID: {parent_pid}")

            # Get the parent process and its children
            parent = psutil.Process(parent_pid)
            children = parent.children(recursive=True)

            if target == "parent":
                print("[INFO] Sending CTRL+C to the parent process...")
                self._send_ctrl_c_to_process(parent_pid, target="parent")

            elif target == "conhost":
                conhost_process = next((p for p in children if p.name().lower() == "conhost.exe"), None)
                if conhost_process:
                    print("[INFO] Sending CTRL+C to the conhost process...")
                    self._send_ctrl_c_to_process(conhost_process.pid, target="conhost")
                else:
                    print("[INFO] No conhost process found among children.")

            elif target == "child":
                other_children = [p for p in children if p.name().lower() != "conhost.exe"]
                if not other_children:
                    print("[INFO] No child processes found (excluding conhost).")
                for child in other_children:
                    print(f"[INFO] Sending CTRL+C to child process PID={child.pid}, Name={child.name()}...")
                    self._send_ctrl_c_to_process(child.pid, target=f"child PID={child.pid}")

            else:
                print(f"[ERROR] Invalid target specified: {target}")

        except psutil.NoSuchProcess:
            print(f"[ERROR] Parent process PID {parent_pid} no longer exists.")
        except Exception as e:
            print(f"[ERROR] Unexpected error during handle_ctrl_c: {e}")

    def _send_ctrl_c_to_process(self, pid, target="unknown"):
        """Send Ctrl+C to the process in the pseudo-console."""
        if self.process and self.process.isalive():
            try:
                # Log the target for debugging
                self.insert_output(f"[INFO] Sending Ctrl+C to target: {target} (PID={pid}).\n")
                self.process.write("\x03")  # Send Ctrl+C (ASCII code)
                self.insert_output("[INFO] Sent Ctrl+C to the process.\n")
            except Exception as e:
                self.insert_output(f"[ERROR] Failed to send Ctrl+C: {e}\n")
        else:
            self.insert_output(f"[ERROR] No active process to send Ctrl+C to for target: {target}.\n")

    ANSI_ESCAPE_PATTERN = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def _read_output(self):
        """Read and display output from the pseudo-console process, using regex for ANSI codes and artifacts."""
        try:
            while True:
                if self.stop_event.is_set():
                    break

                # Read up to 1024 bytes from the pseudo-console
                output = self.process.read(1024)
                if not output:
                    break

                # Safeguard against widget destruction
                if not self.output_widget or not self.output_widget.winfo_exists():
                    break

                # Remove ANSI escape sequences
                clean_output = self.ANSI_ESCAPE_PATTERN.sub('', output)

                # Normalize carriage returns (\r) by removing them
                clean_output = clean_output.replace('\r', '')

                # Directly remove the specific artifact
                artifact_to_remove = "0;C:\\Windows\\system32\\cmd.EXE\x07"
                filtered_output = clean_output.replace(artifact_to_remove, "")

                # Insert filtered output
                self.insert_output(filtered_output)

                # Detect paths directly in the clean output
                for match in re.finditer(r"^[A-Za-z]:\\.*>", clean_output, re.MULTILINE):
                    # Extract the path without the trailing '>'
                    detected_path = match.group(0).rstrip(">")
                    self.cached_cwd = detected_path
                    print(f"[INFO] Current directory updated to: {self.cached_cwd}\n")

        except Exception as e:
            self.insert_output(f"[ERROR] Failed to read console output: {e}\n")

    def insert_output(self, text):
        """Insert shell output into the output widget."""
        if not self.output_widget or not self.output_widget.winfo_exists():
            return  # Widget has been destroyed, skip

        self.output_widget.config(state="normal")
        self.output_widget.insert(tk.END, text)
        self.output_widget.see(tk.END)
        self.output_widget.config(state="disabled")

    def on_tab_activated(self):
        if self.input_entry and self.input_entry.winfo_exists():
            self.input_entry.focus_force()
            print("[DEBUG] Focus set to input_entry.")
        else:
            print("[ERROR] Input textbox is not available for focus.")

    def close(self):
        """Terminate the pseudo-console process and clean up resources."""
        if self.process and self.process.isalive():
            # Send Ctrl+C to interrupt any running commands
            self.handle_ctrl_c()

            # Allow some time for the process to terminate gracefully
            time.sleep(0.5)

            # If the process is still running, terminate it forcefully
            if self.process.isalive():
                try:
                    self.process.terminate()
                except Exception as e:
                    self.insert_output(f"[ERROR] Failed to terminate shell process: {e}\n")

        # Signal the _read_output thread to stop
        self.stop_event.set()

        # Call the parent close method to clean up tab resources
        super().close()

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

        # Bind key press globally - for script keyboard input support
        self.root.bind("<Key>", self.on_key_press)

        # Bind Control+` for toggling the console window
        self.root.bind_all("<Control-`>", self.handle_control_tilde)

        self.root.bind_all("<Control-w>", lambda event: self.tab_manager.close_active_tab())

    def start(self):
        """Start the app"""
        # Autoplay Scripts
        self.autoplay_script_group()

    def handle_control_tilde(self, event=None):
        """Bring up the CommandLineTab: Select if exists, create if not."""
        # Check if a CommandLineTab exists
        for tab_id, tab in self.tab_manager.tabs.items():
            if isinstance(tab, CommandLineTab):
                # Select the existing CommandLineTab
                self.tab_manager.notebook.select(tab.frame)

        # No CommandLineTab exists, create a new one
        self.add_command_line_tab()

    def configure_root(self):
        """Configure the main root window."""
        self.root.title("MSFS-PyScriptManager")
        self.root.geometry("1000x600")
        self.root.configure(bg=DARK_BG_COLOR)
        try:
            photo = tk.PhotoImage(file="Data/letter-m-svgrepo-com.png")
            self.root.wm_iconphoto(False, photo)
        except tk.TclError as e:
            print(f"Error loading icon: {e}")

    def create_toolbar(self):
        """Create the top toolbar with action buttons."""
        self.toolbar = tk.Frame(self.root, bg=DARK_BG_COLOR)
        self.toolbar.pack(side="top", fill="x", padx=5, pady=5)

        # Add buttons to the toolbar with their placement side
        buttons = [
            ("Run Script", self.select_and_run_script, "left"),
            ("Restart ALL", self.reload_all_scripts, "left"),
            ("Load Script Group", self.load_script_group, "right"),
            ("Save Script Group", self.save_script_group, "right"),
            ("Performance Metrics", self.open_performance_metrics_tab, "right"),
            ("Command Line", self.add_command_line_tab, "right")
        ]

        for text, command, side in buttons:
            button = tk.Button(
                self.toolbar, text=text, command=command,
                bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR,
                activebackground=BUTTON_ACTIVE_BG_COLOR,
                activeforeground=BUTTON_ACTIVE_FG_COLOR,
                relief="flat", highlightthickness=0
            )
            button.pack(side=side, padx=(0,5), pady=2)

    def select_and_run_script(self):
        """Opens file dialog for script selection and then runs it"""
        file_path = filedialog.askopenfilename( title="Select Python Script",
                                                filetypes=[("Python Files", "*.py")],
                                                initialdir=str(scripts_path) )
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

    def reload_all_scripts(self):
        shift_held = is_shift_held()
        if not shift_held:
            if not messagebox.askyesno("Confirm Reload",
                                       "Are you sure you want to reload ALL scripts?\n\n"
                                       "Note you can hold shift to bypass this check"):
                return  # User canceled, do not proceed

        self.tab_manager.reload_all_scripts()

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

    def add_command_line_tab(self):
        """Create and add a CommandLineTab."""
        command_line_tab = CommandLineTab(
            title="Command Line",
            command_callback=self.handle_command  # Pass the generalized callback
        )
        self.tab_manager.add_tab(command_line_tab)

    def handle_command(self, command, args, current_dir):
        """Generalized command handler with directory context."""
        if command in ["python", "py"]:
            return self.handle_python_command(args, current_dir)
        elif command in ["switch", "s"]:
            return self.switch_tab_by_name(args)
        elif command == "reload":
            return self.handle_reload_command()
        else:
            return False, f"Unknown command: {command}"

    def handle_python_command(self, args, current_dir):
        """Handle intercepted Python commands with directory context."""
        if not args:
            return False, "No script specified for 'python'."

        script_name = args[0]
        extra_args = args[1:]  # Additional arguments for the script

        # Resolve the script path relative to the current directory
        script_path = Path(current_dir) / script_name
        if not script_path.exists():
            return False, f"Script '{script_path}' not found."

        # Launch the script in a new ScriptTab
        script_tab = ScriptTab(
            title=script_path.name,
            script_path=script_path,
            process_tracker=self.process_tracker
        )
        self.tab_manager.add_tab(script_tab)

        return True, None  # Success

    def switch_tab_by_name(self, args):
        """Switch to the tab with the specified script name."""
        if not args:
            return False, "No script name provided. Usage: switch <script_name>"

        script_name = args[0]
        for tab_id, tab in self.tab_manager.tabs.items():
            if isinstance(tab, ScriptTab) and tab.script_path.name.lower() == script_name.lower():
                self.tab_manager.notebook.select(tab.frame)
                return True, None  # Success

        return False, f"No tab found for script: {script_name}"

    def handle_reload_command(self):
        """Switch to the tab with the specified script name."""
        self.tab_manager.reload_all_scripts()
        return True, None  # Success

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
            filetypes=[("Script Group Files", "*.script_group")],
            initialdir=str(scripts_path)
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
            script_paths = [group_dir / Path(line.strip()) for line in f.readlines() if line.strip()]

        # Use a set to avoid loading duplicate scripts
        loaded_scripts = set()
        script_paths = [script_path.resolve() for script_path in script_paths if script_path]

        def load_script_with_delay(index):
            """Load a script with a slight delay."""
            script_path = script_paths[index]
            if str(script_path) not in loaded_scripts:
                loaded_scripts.add(str(script_path))
                print(f"[INFO] Loading script '{script_path.name}' (Index: {index}).")
                self.load_script_from_path(script_path)

        # Schedule each script to load with an increasing delay
        for i, script_path in enumerate(script_paths):
            delay = i * SCRIPT_LOAD_DELAY_MS
            self.root.after(delay, load_script_with_delay, i)

    def on_shutdown(self):
        logger.info("Shutdown signal received. Triggering shutdown_event.")
        logger.debug(f"[DEBUG] on_shutdown shutdown_event ID: {id(self.shutdown_event)}")

        # Set shutdown_event which will trigger launcher shutdown
        self.shutdown_event.set()

    def on_close(self, callback=None):
        """Handle application shutdown."""
        print("[INFO] Shutting down application.")
        logger.info("Shutting down application")
        self.tab_manager.close_all_tabs()

        def finalize_shutdown():
            print("[INFO] Application closed successfully.")
            logger.info("finalize_shutdown()")
            if callback:
                callback()  # Execute the callback after shutdown is fully complete.

        logger.debug("Schedule: finalize shutdown")
        self.root.after(0, lambda: (self.root.destroy(), finalize_shutdown()))

    def on_key_press(self, event):
        """Route keypress events to the active tab if it supports keypress handling."""
        active_tab_id = self.tab_manager.active_tab_id
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

class ProcessTracker:
    """Manages runtime of collection of processes"""
    def __init__(self, scheduler, shutdown_event):
        self.processes = {}  # Maps tab_id to process metadata
        self.scheduler = scheduler  # Store the scheduler
        self.script_name = None
        self.queuefull_warning_issued = False
        self.lock = Lock()
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

            # Create individual queues and stop event
            stdout_queue = queue.Queue(maxsize=1000)
            stderr_queue = queue.Queue(maxsize=1000)
            stdin_queue = queue.Queue(maxsize=1000)
            stop_event = threading.Event()

            with self.lock:
                self.processes[tab_id] = {
                    "process": process,
                    "script_name": script_name or "Unknown",
                    "script_tab": script_tab,
                    "stdout_queue": stdout_queue,
                    "stderr_queue": stderr_queue,
                    "stdin_queue": stdin_queue,
                    "stop_event": stop_event,
                }

            # Start threads for stdout and stderr reading
            threading.Thread(
                target=self._read_output,
                args=(process.stdout, stdout_queue, stop_event, tab_id, "stdout"),
                daemon=True,
                name=f"StdoutThread-{tab_id}"
            ).start()

            threading.Thread(
                target=self._read_output,
                args=(process.stderr, stderr_queue, stop_event, tab_id, "stderr"),
                daemon=True,
                name=f"StderrThread-{tab_id}"
            ).start()

            # Start a thread for writing to stdin
            threading.Thread(
                target=self._write_input,
                args=(process.stdin, stdin_queue, stop_event, tab_id),
                daemon=True,
                name=f"StdinWriter-{tab_id}"
            ).start()

            # Start dispatcher threads to process queues and invoke callbacks
            threading.Thread(
                target=self._dispatch_queue,
                args=(stdout_queue, stdout_callback, stop_event),
                daemon=True,
                name=f"DispatcherStdout-{tab_id}"
            ).start()

            threading.Thread(
                target=self._dispatch_queue,
                args=(stderr_queue, stderr_callback, stop_event),
                daemon=True,
                name=f"DispatcherStderr-{tab_id}"
            ).start()

            # Start process monitoring
            self.schedule_process_check(tab_id)

        except Exception as e:
            print(f"[ERROR] Failed to start process for Tab ID {tab_id}: {e}")

    def _read_output(self, stream, output_queue, stop_event, tab_id, stream_name):
        """
        Read subprocess output with proper handling of lines and partial data.
        """
        print(f"[INFO] Starting output reader for {stream_name}, Tab ID: {tab_id}")

        fd = stream.fileno()  # Get the file descriptor for low-level reads
        buffer = ""  # Accumulate partial lines
        last_flushed_partial = None  # Track the last flushed partial line

        try:
            while not stop_event.is_set():
                try:
                    # Attempt to read a chunk of data
                    chunk = os.read(fd, 4096).decode("utf-8")
                    if not chunk:  # EOF or no data available
                        time.sleep(0.01)
                        continue

                    buffer += chunk

                    # Debug: Log received chunk and updated buffer
                    #print(f"[DEBUG] Chunk received ({len(chunk)} chars): {repr(chunk)}")
                    #print(f"[DEBUG] Current buffer ({len(buffer)} chars): {repr(buffer)}")

                    # Process complete lines in the buffer
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        output_queue.put_nowait(line + "\n")
                        #print(f"[DEBUG] Line enqueued: {repr(line)}")
                        last_flushed_partial = None  # Reset partial tracking

                    # Handle partial line (e.g., prompts or incomplete output)
                    if buffer and buffer != last_flushed_partial:
                        output_queue.put_nowait(buffer)
                        #print(f"[DEBUG] Partial buffer enqueued: {repr(buffer)}")
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
                output_queue.put_nowait(buffer)
                print(f"[DEBUG] Final buffer flushed: {repr(buffer)}")
            output_queue.put(None)  # Signal end of stream to the queue

            try:
                stream.close()  # Close the stream gracefully
            except Exception as close_error:
                print(f"[WARNING] Error closing {stream_name}: {close_error}")

            print(f"[INFO] Output reader for {stream_name} finished, Tab ID: {tab_id}")

    def _write_input(self, stdin, input_queue, stop_event, tab_id):
        """Write input from the queue to the subprocess's stdin."""
        try:
            while not stop_event.is_set():
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

    def _dispatch_queue(self, q, callback, stop_event):
        """Consume items from the queue and invoke the callback."""
        print("[INFO] Starting dispatcher thread.")
        while True:
            try:
                line = q.get(timeout=1)  # Avoid indefinite blocking
            except queue.Empty:
                # Check if this process’s stop_event is set
                if stop_event.is_set():
                    print("[INFO] Dispatcher stopping due to its own stop_event.")
                    logger.debug("Dispatcher stopping due to its own stop_event.")
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
        with self.lock:
            metadata = self.processes.get(tab_id)
            if not metadata:
                return  # Process already cleaned up or not found

        process = metadata["process"]
        script_tab : ScriptTab = metadata.get("script_tab")
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
                        script_tab.insert_output("\n\n\n\n\n")

                        # AutoRestart on delay in case this is in a crash loop as this will limit
                        # performance impact
                        # TODO : this maybe should be based on a script meta-data settings on a
                        # per script basis
                        # TODO: also should limit how often it can restart in a row?
                        script_tab.insert_output("Restarting Script..\n")

                        self.scheduler(SCRIPT_LOAD_DELAY_MS,
                                       lambda: script_tab.reload_script(clear_text=False))

                # Clean up process metadata
                with self.lock:
                    self.processes.pop(tab_id, None)
            except Exception as e:
                print(f"[ERROR] Error notifying ScriptTab for Tab ID {tab_id}: {e}")
            return

        # Reschedule the next check
        self.schedule_process_check(tab_id)

    def terminate_process(self, tab_id):
        """Terminate the process for a given tab ID."""
        print(f"[INFO] Attempting to terminate process for Tab ID: {tab_id}")
        logger.info("[INFO] Attempting to terminate process for Tab ID: %s", tab_id)

        # Remove metadata for this tab
        with self.lock:
            metadata = self.processes.pop(tab_id, None)
            if not metadata:
                print(f"[INFO] No process found for Tab ID {tab_id}.")
                return
            process = metadata["process"]

        # Terminate the process if it is still running
        if process.poll() is None:  # Still running
            print(f"[INFO] Terminating process for Tab ID {tab_id} (PID {process.pid}).")
            self.terminate_process_tree(process.pid)

        # Signal threads to stop
        metadata["stop_event"].set()
        metadata["stdout_queue"].put("[INFO] Process terminated by user.\n")
        metadata["stdout_queue"].put(None)  # Final EOF sentinel

        # Close the process's I/O streams
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

        print(f"[INFO] Process for Tab ID {tab_id} terminated.")
        logger.info("[INFO] Process for Tab ID %s terminated.", tab_id)

    @staticmethod
    def terminate_process_tree(pid, timeout=5, force=True):
        """Terminate a process tree."""
        print(f"[INFO] Terminating process tree for PID: {pid}")
        logger.info("[INFO] Terminating process tree for PID: %s", pid)
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            logger.info(f"Process with PID {pid} already terminated. "
                  "Checking for orphaned children.")
            # Attempt to clean up orphaned child processes
            self.terminate_orphaned_children(pid)
            return
        except Exception as e:
            print(f"[ERROR] Failed to initialize process PID {pid}: {e}")
            return

        try:
            children = parent.children(recursive=True)
            logger.info(f"Found {len(children)} child processes for PID {pid}."
                  f"Terminating children first.")

            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    logger.warning(f"NoSuchProcess {child.pid}.")
                    continue
                except psutil.AccessDenied:
                    logger.warning(f"Access denied to terminate child PID {child.pid}.")

            # Wait for all children to terminate
            _, alive = psutil.wait_procs(children, timeout=timeout)

            if alive and force:
                logger.info(f"[WARNING] {len(alive)} child processes did not terminate. "
                      "Forcing termination.")
                for proc in alive:
                    try:
                        logger.info("proc.kill()")
                        proc.kill()
                    except psutil.NoSuchProcess:
                        logger.warning(f"NoSuchProcess")
                        continue
                    except psutil.AccessDenied:
                        logger.info(f"[WARNING] Access denied to kill child PID {proc.pid}.")

            # Terminate the parent process
            parent.terminate()
            _, alive = psutil.wait_procs([parent], timeout=timeout)

            if alive and force:
                print(f"[WARNING] Parent process PID {parent.pid} did not terminate. Forcing kill.")
                for proc in alive:
                    try:
                        proc.kill()
                        logger.info("proc.kill()")
                    except psutil.NoSuchProcess:
                        logger.warning(f"NoSuchProcess")
                        continue
                    except psutil.AccessDenied:
                        logger.warning(f"Access denied to kill PID {proc.pid}.")

            #logging.info("Made it to end - terminate process tree")

        except psutil.NoSuchProcess:
            print(f"[INFO] Parent process PID {pid} already terminated during cleanup.")
        except Exception as e:
            print(f"[ERROR] Unexpected error terminating process tree for PID {pid}: {e}")

    @staticmethod
    def terminate_orphaned_children(parent_pid):
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

class RingMovingAverage:
    """Used to calculate moving average with ring buffer"""
    def __init__(self, window_size):
        self.window_size = window_size
        self.buffer = np.zeros(window_size, dtype=float)
        self.index = 0
        self.count = 0

    def add(self, value):
        """Add to moving average array"""
        self.buffer[self.index] = value
        self.index = (self.index + 1) % self.window_size
        self.count = min(self.count + 1, self.window_size)

    def get_average(self):
        """Get calculated average"""
        return np.mean(self.buffer[:self.count]) if self.count > 0 else 0.0

def monitor_shutdown_pipe(pipe_name, shutdown_event):
    """Monitor the named pipe for shutdown signals and heartbeats."""
    logger.info("Monitoring shutdown pipe in subprocess. Pipe: %s", pipe_name)

    HEARTBEAT_TIMEOUT = 5  # Timeout in seconds to detect missed heartbeats
    last_heartbeat_time = time.time()  # Track the last heartbeat time

    def pipe_reader():
            """Threaded pipe reader."""
            nonlocal last_heartbeat_time
            try:
                with open(pipe_name, "r", encoding="utf-8") as pipe:
                    logger.info("Successfully connected to the shutdown pipe.")
                    while not shutdown_event.is_set():
                        try:
                            # Read line from pipe (blocking)
                            line = pipe.readline().strip()
                            if line:
                                if line == "shutdown":
                                    logger.info("Shutdown signal received in subprocess.")
                                    shutdown_event.set()
                                    break
                                elif line == "HEARTBEAT":
                                    #logging.debug("Heartbeat received.")
                                    last_heartbeat_time = time.time()  # Update last heartbeat time
                        except Exception as e:
                            logger.error("Exception while reading pipe: %s", e)
                            break

                        # Sleep briefly to prevent tight loop
                        time.sleep(0.1)
            except Exception as e:
                logger.error("Failed to monitor shutdown pipe: %s", e)
            finally:
                logger.info("Exiting pipe_reader thread.")

    # Start the reader thread
    reader_thread = threading.Thread(target=pipe_reader, daemon=True)
    reader_thread.start()

    # Wait for shutdown event while pipe read runs in thread
    while not shutdown_event.is_set():
        # Check for heartbeat timeout
        if time.time() - last_heartbeat_time > HEARTBEAT_TIMEOUT:
            logger.info("!=================== Heartbeat timeout detected ===================!")
            shutdown_event.set()
            break
        time.sleep(0.5)

    logger.debug("join reader_thread")
    reader_thread.join(timeout=1)  # Allow the thread to exit

def is_shift_held():
    """Check if Shift key is currently held globally."""
    return keyboard.is_pressed("shift")

def main():
    """Main entry point for the script."""
    args = sys.argv
    logger.debug("args=%s", args)

    # Prime keyboard module
    # This seems necessary or first hold of shift will not be registered
    # Used for shift-click of "Restart All"
    _ = keyboard.is_pressed("shift")

    # Parse the --shutdown-pipe argument
    shutdown_pipe = None
    if "--shutdown-pipe" in args:
        shutdown_pipe = args[args.index("--shutdown-pipe") + 1]
        logger.debug("shutdown_pipe=%s", shutdown_pipe)
    else:
        logger.info("No --shutdown-pipe argument provided. Skipping pipe-based shutdown logic.")

    # Add lib_path to PYTHONPATH
    lib_path = str((Path(__file__).resolve().parents[1] / "Lib").resolve())
    if lib_path not in os.environ.get("PYTHONPATH", "").split(";"):
        os.environ["PYTHONPATH"] = f"{lib_path};{os.environ.get('PYTHONPATH', '')}"
        logger.info(f"Added '{lib_path}' to PYTHONPATH.")

    logger.info("Starting the application.")

    print("Starting Launcher.py -- main()")

    # Start app
    root = ThemedTk(theme="black")
    app = ScriptLauncherApp(root)

    # Add fault handler
    faulthandler.enable()
    traceback_log_file = open("Launcher.log", "w")
    def reset_traceback_timer():
        """Reset the faulthandler timer to prevent a dump."""
        faulthandler.dump_traceback_later(15, file=traceback_log_file, exit=True)
        root.after(5000, reset_traceback_timer)

    #reset_traceback_timer()

    # Start the shutdown monitoring subprocess if a pipe is provided
    monitor_process = None
    if shutdown_pipe:
        monitor_process = Process(target=monitor_shutdown_pipe,
                                  args=(shutdown_pipe, app.shutdown_event))
        monitor_process.start()
        logger.info("Started shutdown monitoring process.")

    try:
        # Periodically check for the shutdown_event
        def check_shutdown():
            if app.shutdown_event.is_set():
                logger.info("Shutdown event detected in main application.")
                app.on_close()
                return
            root.after(100, check_shutdown)  # Recheck every 100ms

        # Start monitoring shutdown_event
        root.after(100, check_shutdown)
        DarkmodeUtils.apply_dark_mode(root)

        app.start()
        root.mainloop()

        logger.info("Tkinter main loop has exited.")
    finally:
        logger.info("Finalizing application shutdown...")

        # Ensure subprocess cleanup
        if monitor_process:
            app.shutdown_event.set()  # Ensure the subprocess knows to exit
            logger.debug("Waiting for shutdown monitoring process to exit...")
            monitor_process.join(timeout=5)
            logger.debug("Past monitor_process join")
            if monitor_process.is_alive():
                logger.warning("Forcibly terminating the shutdown monitoring process.")
                monitor_process.terminate()

        logger.info("Application closed successfully.")
        logger.stop()

if __name__ == "__main__":
    main()
