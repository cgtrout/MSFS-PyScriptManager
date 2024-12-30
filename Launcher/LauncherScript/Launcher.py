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

import tkinter as tk
from tkinter import filedialog, scrolledtext, TclError
from tkinter import ttk

import psutil
from ttkthemes import ThemedTk

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
logging.basicConfig(
    level=logging.DEBUG,  # Change to logging.DEBUG for more detailed output
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler("shutdown_log.txt", mode="w")  # Log to file
    ]
)

class Tab:
    """Manages the content and behavior of an individual tab (its frame, widgets, etc.)."""
    def __init__(self, title):
        self.title = title
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

    def build_content(self):
        """Build the content of the ScriptTab."""
        self.text_widget = scrolledtext.ScrolledText(
            self.frame,
            wrap="word",
            bg=TEXT_WIDGET_BG_COLOR,
            fg=TEXT_WIDGET_FG_COLOR,
            insertbackground=TEXT_WIDGET_INSERT_COLOR
        )
        self.text_widget.pack(expand=True, fill="both")

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
        # Define the custom library path
        lib_path = str((Path(__file__).resolve().parents[1] / "Lib").resolve())

        # Set the PYTHONPATH environment variable dynamically
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{lib_path};{env.get('PYTHONPATH', '')}"  # Add lib_path to PYTHONPATH

        # Build the command
        command = [str(pythonw_path.resolve()), "-u", str(self.script_path.resolve())]

        # Start the process with the updated environment
        self.process_tracker.start_process(
            tab_id=self.tab_id,
            command=command,
            stdout_callback=self._insert_stdout,
            stderr_callback=self._insert_stderr,
            script_name=self.script_path.name
        )

    # TODO may not be best place for these
    def _insert_stdout(self, text):
        self._insert_text(text)

    def _insert_stderr(self, text):
        self._insert_text(text)

    def _insert_text(self, text):
        """Safely insert text into the widget, handling both stdout and stderr."""
        if self.text_widget and self.text_widget.winfo_exists():
            self.frame.after(0, lambda: self._safe_insert(text))
        else:
            print(f"[WARNING] Attempt to write to a destroyed widget for Tab ID: {self.tab_id}")

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
            self.process_tracker.terminate_process(self.tab_id)  # Now synchronous
            self.run_script()

        self.process_tracker.scheduler(0, _reload)  # Schedule the reload process

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
        self.process_tracker = ProcessTracker(scheduler=self.root.after)

        # Bind Events
        self.bind_events()

        # Autoplay Scripts
        self.autoplay_script_group()

        # Event for shutdown
        self.shutdown_event = Event()

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
        for tab in self.tab_manager.tabs.values():
            if isinstance(tab, ScriptTab):
                relative_path = os.path.relpath(tab.script_path, group_dir)
                script_paths.append(relative_path)

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

class ProcessTracker:
    """Manages runtime of collection of processes"""
    def __init__(self, scheduler):
        self.processes = {}  # Maps tab_id to process metadata
        self.queues = {}  # Maps tab_id to queues for stdout and stderr
        self.scheduler = scheduler  # Store the scheduler
        self.script_name = None
        self.queuefull_warning_issued = False

    def start_process(self, tab_id, command, stdout_callback, stderr_callback, script_name=None):
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
                text=True,
                bufsize=1,
                env=custom_env,
            )
            print(f"[INFO] Started process: {script_name}, PID: {process.pid}, Tab ID: {tab_id}")

            self.script_name = script_name
            self.processes[tab_id] = {"process": process, "script_name": script_name or "Unknown"}

            # Create queues for communication
            self.queues[tab_id] = {
                "stdout": queue.Queue(maxsize=1000),
                "stderr": queue.Queue(maxsize=1000),
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

        except Exception as e:
            print(f"[ERROR] Failed to start process for Tab ID {tab_id}: {e}")

    def _read_output(self, stream, q, tab_id, stream_name):
        """Read subprocess output line-by-line for real-time updates."""
        print(f"[INFO] Starting output reader for {stream_name}, Tab ID: {tab_id}")
        try:
            while not self.queues[tab_id]["stop_event"].is_set():
                line = stream.readline()  # Read one line at a time
                if not line:  # End of stream
                    print(f"[INFO] End of stream detected for {stream_name}, Tab ID: {tab_id}")
                    break

                # print(f"[DEBUG] Line read for {stream_name}, Tab ID {tab_id}: {line.strip()}")
                q.put_nowait(line)

        except queue.Full:
            # Handle scenario where queue is full
            if not self.queuefull_warning_issued:
                print(f"\n[WARNING] Queue line buffer limit reached for {self.script_name} - logging skipped.\n")
                self.queuefull_warning_issued = True
        except Exception as e:
            print(f"[ERROR] Error reading {stream_name} for Tab ID {tab_id}: {e}")
        finally:
            q.put(None)  # Sentinel to indicate EOF
            try:
                stream.close()  # Safely close the stream
                print(f"[INFO] {stream_name} stream closed successfully, Tab ID: {tab_id}")
            except Exception as e:
                print(f"[WARNING] Error closing {stream_name}: {e}")
            print(f"[INFO] Output reader for {stream_name} finished, Tab ID: {tab_id}")

    def _dispatch_queue(self, q, callback):
        """Consume items from the queue and invoke the callback."""
        print("[INFO] Starting dispatcher thread.")
        while True:
            try:
                line = q.get(timeout=1)  # Avoid indefinite blocking
                #print("[DEBUG] Dispatcher received line from queue.")
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
            print(f"[INFO] Process with PID {pid} already terminated. "
                  "Checking for orphaned children.")
            # Attempt to clean up orphaned child processes
            self._terminate_orphaned_children(pid)
            return
        except Exception as e:
            print(f"[ERROR] Failed to initialize process PID {pid}: {e}")
            return

        try:
            children = parent.children(recursive=True)
            print(f"[INFO] Found {len(children)} child processes for PID {pid}."
                  f"Terminating children first.")

            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    continue
                except psutil.AccessDenied:
                    print(f"[WARNING] Access denied to terminate child PID {child.pid}.")

            # Wait for all children to terminate
            _, alive = psutil.wait_procs(children, timeout=timeout)

            if alive and force:
                print(f"[WARNING] {len(alive)} child processes did not terminate. "
                      "Forcing termination.")
                for proc in alive:
                    try:
                        proc.kill()
                    except psutil.NoSuchProcess:
                        continue
                    except psutil.AccessDenied:
                        print(f"[WARNING] Access denied to kill child PID {proc.pid}.")

            # Terminate the parent process
            parent.terminate()
            _, alive = psutil.wait_procs([parent], timeout=timeout)

            if alive and force:
                print(f"[WARNING] Parent process PID {parent.pid} did not terminate. Forcing kill.")
                for proc in alive:
                    try:
                        proc.kill()
                    except psutil.NoSuchProcess:
                        continue
                    except psutil.AccessDenied:
                        print(f"[WARNING] Access denied to kill PID {proc.pid}.")
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
    """Monitor the named pipe for shutdown signals."""
    logging.info("Monitoring shutdown pipe in subprocess. Pipe: %s", pipe_name)

    def pipe_reader():
        """Threaded pipe reader."""
        try:
            with open(pipe_name, "r", encoding="utf-8") as pipe:
                logging.info("Successfully connected to the shutdown pipe.")
                while not shutdown_event.is_set():
                    try:
                        line = pipe.readline().strip()  # Blocking call
                        if line:
                            logging.debug("Read line from pipe: %s", line)
                            if line == "shutdown":
                                logging.info("Shutdown signal received in subprocess.")
                                shutdown_event.set()
                                break
                    except Exception as e:
                        logging.error("Exception while reading pipe: %s", e)
                        break
        except Exception as e:
            logging.error("Failed to monitor shutdown pipe: %s", e)
        finally:
            logging.info("Exiting pipe_reader thread.")

    # Start the reader thread
    reader_thread = threading.Thread(target=pipe_reader, daemon=True)
    reader_thread.start()

    # Wait for shutdown event while pipe read runs in thread
    while not shutdown_event.is_set():
        time.sleep(1)

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

        root.mainloop()

        logging.info("Tkinter main loop has exited.")
    finally:
        logging.info("Finalizing application shutdown...")

        # Ensure subprocess cleanup
        if monitor_process:
            app.shutdown_event.set()  # Ensure the subprocess knows to exit
            logging.debug("Waiting for shutdown monitoring process to exit...")
            monitor_process.join(timeout=5)
            if monitor_process.is_alive():
                logging.warning("Forcibly terminating the shutdown monitoring process.")
                monitor_process.terminate()

        logging.info("Application closed successfully.")

if __name__ == "__main__":
    main()
