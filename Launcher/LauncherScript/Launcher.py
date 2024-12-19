import os
import sys
import threading
import time  
from pathlib import Path
from typing import Dict, Callable, Optional
import subprocess  
import logging
import psutil  
import tkinter as tk
from tkinter import filedialog, scrolledtext, TclError
from tkinter import ttk  
import queue
from multiprocessing import Process, Event
from ttkthemes import ThemedTk  

# Path to the WinPython Python executable and VS Code.exe
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parents[1]
python_path = project_root / "WinPython" / "python-3.13.0rc1.amd64" / "python.exe"
pythonw_path = python_path.with_name("pythonw.exe")  # Use pythonw.exe to prevent console window
vscode_path = project_root / "WinPython" / "VS Code.exe"  # Dynamically calculated path to VS Code.exe
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

class Tab:
    """Manages the content and behavior of an individual tab (its frame, widgets, etc.)."""
    def __init__(self, title):
        self.title = title

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
    """ Manages the Notebook and all tabs."""
    def __init__(self, root):
        self.notebook = ttk.Notebook(root)
        self.configure_notebook()
        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)
        self.tabs = {}
        self.current_tab_id = 0

        self.processes = {}  # Stores subprocess details by tab ID
        self.stop_events = {}  # Stores threading stop events by tab ID
        self.current_tab_id = 0  # Counter for unique tab IDs

    def generate_tab_id(self):
        """Generate a unique tab ID."""
        self.current_tab_id += 1
        return self.current_tab_id

    def configure_notebook(self):
        """Configure notebook style and behavior."""
        style = ttk.Style()
        style.configure('TNotebook', padding=[0, 0])
        style.configure('TNotebook.Tab', padding=[5, 2])
        style.configure('TFrame', background=DARK_BG_COLOR)

        # Bind right-click to close tabs
        self.notebook.bind("<Button-3>", self.on_tab_right_click)

    def add_tab(self, tab):
        """Add a new tab to the notebook."""
        tab_id = self.generate_tab_id()
        tab.tab_id = tab_id
        tab.initialize_frame(self.notebook)
        tab.build_content()
        self.notebook.add(tab.frame, text=tab.title)
        self.tabs[tab_id] = tab
        self.notebook.select(tab.frame)  
    
    def close_tab(self, tab_id):
        """Close a tab and clean up resources."""
        tab = self.tabs.pop(tab_id, None)
        if not tab:
            print(f"[WARNING] Tab with ID {tab_id} not found.")
            return

        tab.close()  

    def close_all_tabs(self):
        """Close all tabs and clean up resources."""
        print("[INFO] Closing all tabs.")
        for tab_id in list(self.tabs.keys()):  # Copy keys to avoid runtime modification issues
            print(f"[INFO] Closing tab with ID {tab_id}.")
            self.close_tab(tab_id)
        print("[INFO] All tabs closed.")

    def on_tab_right_click(self, event):
        """Handle right-click to close a tab."""
        try:
            clicked_tab_index = self.notebook.index(f"@{event.x},{event.y}")
            self.close_tab_by_index(clicked_tab_index)
        except TclError:
            print("[ERROR] Right-click did not occur on a valid tab. Ignoring.")

    def close_tab_by_index(self, index):
        """Close a tab by its notebook index."""
        try:
            frame = self.notebook.winfo_children()[index]
            for tab_id, tab in self.tabs.items():
                if tab.frame == frame:
                    self.close_tab(tab_id)  # Use the standard close logic
                    return
        except Exception as e:
            print(f"[ERROR] Issue closing tab by index {index}: {e}")

class ScriptTab(Tab):
    def __init__(self, title, script_path, process_tracker):
        super().__init__(title)
        self.script_path = script_path
        self.process_tracker = process_tracker
        self.tab_id = None

    def build_content(self):
        """Build the content of the ScriptTab."""
        # Create the text widget for script output
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
        """Safely insert stdout text into the widget."""
        self.frame.after(0, lambda: self.text_widget.insert(tk.END, text))

    def _insert_stderr(self, text):
        """Safely insert stderr text into the widget."""
        self.frame.after(0, lambda: self.text_widget.insert(tk.END, text))

    def edit_script(self):
        """Open the script in VSCode for editing."""
        try:
            subprocess.Popen([str(vscode_path.resolve()), str(self.script_path)])
            self.insert_output(f"Opening script {self.script_path} for editing in VS Code...\n")
        except Exception as e:
            self.insert_output(f"Error opening script for editing: {e}\n")

    def reload_script(self):
        """Reload the script by restarting the process."""
        self.process_tracker.terminate_process(self.tab_id)
        self.run_script()

    def _insert_output(self, text):
        """Insert text into the text widget."""
        if self.text_widget and self.text_widget.winfo_exists():
            self.frame.after(0, lambda: self.text_widget.insert(tk.END, text))

    def stop_script(self):
        """Stop the script process."""
        process_info = self.process_tracker.get_process(self.id)
        if process_info:
            process = process_info.get("process")
            stop_event = process_info.get("stop_event")

            if process and process.poll() is None:  # Check if the process is running
                print(f"[INFO] Terminating process for Tab ID {self.id}.")
                stop_event.set()  # Signal the threads to stop
                self.process_tracker.terminate_process(self.id)  # Delegate cleanup to ProcessTracker
        else:
            print(f"[WARNING] Process for Tab ID {self.id} not found. It may have already been removed.")

class PerfTab(Tab):
    def __init__(self, title, process_tracker):
        super().__init__(title)
        self.process_tracker = process_tracker
        self.performance_metrics_open = True
        self.text_widget = None

    def build_content(self):
        """Add widgets to the performance tab."""
        self.text_widget = scrolledtext.ScrolledText(
            self.frame, wrap="word", 
            bg=TEXT_WIDGET_BG_COLOR, fg=TEXT_WIDGET_FG_COLOR,
            insertbackground=TEXT_WIDGET_INSERT_COLOR
        )
        self.text_widget.pack(expand=True, fill="both")
        self.start_monitoring()

    def initialize_cpu_percent(self):
        """Initialize CPU percent measurement for each process and its children."""
        try:
            for tab_id, process_info in self.process_tracker.list_processes().items():
                process = process_info.get("process")
                if process and process.pid:
                    proc = psutil.Process(process.pid)
                    proc.cpu_percent(interval=0)  # Initialize CPU tracking for the parent process
                    for child in proc.children(recursive=True):
                        child.cpu_percent(interval=0)  # Initialize for child processes
        except Exception as e:
            print(f"[ERROR] Issue initializing CPU metrics: {e}")

    def start_monitoring(self):
        """Start monitoring performance metrics using tkinter's after."""
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

    def safe_refresh_performance_metrics(self, text):
        # Only update if tab and widget still exist
        if self.performance_metrics_open and hasattr(self, 'performance_text_widget'):
            if self.performance_text_widget.winfo_exists():
                self.performance_text_widget.delete('1.0', tk.END)
                self.performance_text_widget.insert(tk.END, text)

    def generate_metrics_text(self):
        """Generate a text representation of performance metrics with average CPU time."""
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
                            self.cpu_stats[tab_id]["cumulative_cpu"] / self.cpu_stats[tab_id]["count"]
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
    def __init__(self, root):
        # Root Window Setup
        self.root = root
        self.configure_root()

        # Toolbar Setup
        self.create_toolbar()

        self.tab_manager = TabManager(root)
        self.process_tracker = ProcessTracker()

        # Bind Events
        self.bind_events()

        # Autoplay Scripts
        self.autoplay_script_group()

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
        file_path = filedialog.askopenfilename(title="Select Python Script", filetypes=[("Python Files", "*.py")])
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
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def open_performance_metrics_tab(self):
        """Open a new performance metrics tab."""
        perf_tab = PerfTab(
            title="Performance Metrics",
            process_tracker=self.process_tracker
        )
        self.tab_manager.add_tab(perf_tab)

    def autoplay_script_group(self):
        """Automatically load a script group file named '_autoplay.script_group' located in the Scripts directory."""
        # Set path to '_autoplay.script_group' within the Scripts directory
        autoplay_path = scripts_path / "_autoplay.script_group"
        
        # Check if the file exists and load it if it does
        if autoplay_path.exists():
            print(f"[INFO] Autoplay: Loading script group from {autoplay_path}")
            self.load_script_group_from_path(autoplay_path)
        else:
            print("[INFO] Autoplay: No '_autoplay.script_group' file found at startup. Skipping autoplay.")

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
        with open(file_path, 'w') as f:
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

        with open(file_path, 'r') as f:
            script_paths = [group_dir / Path(line.strip()) for line in f.readlines() if line.strip()]

        # Use a set to avoid loading duplicate scripts
        loaded_scripts = set()

        for script_path in script_paths:
            absolute_path = script_path.resolve()
            if str(absolute_path) not in loaded_scripts:
                loaded_scripts.add(str(absolute_path))
                self.load_script_from_path(absolute_path)

    def terminate_tracked_processes_on_close(self):
        """Terminate any remaining processes on app close."""
        self.process_tracker.terminate_all_processes()

    def on_close(self):
        """Handle application shutdown."""
        print("[INFO] Shutting down application.")
        self.tab_manager.close_all_tabs()  # Close all tabs first
        self.root.destroy()  # Destroy the main window
        print("[INFO] Application closed successfully.")

class ProcessTracker:
    def __init__(self):
        """Initialize the ProcessTracker with a thread pool executor."""
        self.processes = {}  # Maps tab_id to process metadata
        self.queues = {}  # Maps tab_id to queues for stdout and stderr
        self.lock = threading.Lock()
    
    def start_process(self, tab_id, command, stdout_callback, stderr_callback, script_name=None):
        """Start a subprocess and manage its I/O."""
       
        lib_path = str((Path(__file__).resolve().parents[1] / "Lib").resolve())
        custom_env = os.environ.copy()  # Create a local environment copy
        custom_env["PYTHONPATH"] = f"{lib_path};{custom_env.get('PYTHONPATH', '')}"  # Add 'Lib' path


       
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

            self.processes[tab_id] = {"process": process, "script_name": script_name or "Unknown"}
            
            # Create queues for communication
            self.queues[tab_id] = {
                "stdout": queue.Queue(),
                "stderr": queue.Queue(),
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
        """Read subprocess output and write lines to a queue."""
        print(f"[INFO] Starting output reader for {stream_name}, Tab ID: {tab_id}")
        try:
            for line in iter(stream.readline, ""):
                if self.queues[tab_id]["stop_event"].is_set():
                    print(f"[INFO] Stop event triggered for {stream_name}, Tab ID: {tab_id}")
                    break
                #print(f"[DEBUG] {stream_name} line read (Tab ID {tab_id}): {line.strip()}")
                q.put(line)
            stream.close()
        except Exception as e:
            print(f"[ERROR] Error reading {stream_name} for Tab ID {tab_id}: {e}")
        finally:
            q.put(None)  # Sentinel to indicate EOF
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
                    break
                continue

            if line is None:  # Sentinel for end-of-stream
                print("[INFO] Dispatcher received EOF sentinel. Exiting.")
                break

            callback(line)

    def terminate_process(self, tab_id):
        """Terminate the process for a given tab ID."""
        print(f"[INFO] Attempting to terminate process for Tab ID: {tab_id}")
        with self.lock:
            metadata = self.processes.pop(tab_id, None)
            if not metadata:
                print(f"[INFO] No process found for Tab ID {tab_id}.")
                return
            
            process = metadata["process"]
            if process.poll() is None:  # Still running
                print(f"[INFO] Terminating process for Tab ID {tab_id} (PID {process.pid}).")
                self._terminate_process_tree(process.pid)

            # Signal threads to stop
            self.queues[tab_id]["stop_event"].set()
            print(f"[INFO] Stop event set for Tab ID: {tab_id}")
            del self.queues[tab_id]

    def terminate_all_processes(self):
        """Terminate all subprocesses and ensure threads stop."""
        print("[INFO] Terminating all processes.")
        with self.lock:
            for tab_id in list(self.processes.keys()):
                self.terminate_process(tab_id)

            # Signal all threads to stop
            for q in self.queues.values():
                q["stop_event"].set()
            
            # Clear any remaining items in the queues to unblock `Queue.get()`
            for q in self.queues.values():
                q["stdout"].put(None)
                q["stderr"].put(None)

        print("[INFO] All processes and threads terminated.")
    
    def _terminate_process_tree(self, pid, timeout=5, force=True):
        """Terminate a process tree."""
        print(f"[INFO] Terminating process tree for PID: {pid}")
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    continue

            parent.terminate()
            gone, alive = psutil.wait_procs([parent] + children, timeout=timeout)
            if alive and force:
                for proc in alive:
                    print(f"[WARNING] Forcing termination for PID: {proc.pid}")
                    proc.kill()
        except psutil.NoSuchProcess:
            print(f"[INFO] Process with PID {pid} already terminated.")
        except Exception as e:
            print(f"[ERROR] Error terminating process tree for PID {pid}: {e}")

    def _wait_for_process_termination(self, process, timeout):
        """Wait for process termination."""
        try:
            process.wait(timeout)
            return True
        except psutil.TimeoutExpired:
            return False
        
    def list_processes(self) -> Dict[int, Dict]:
        """List all tracked processes and their metadata."""
        return {
            tab_id: {
                "process": metadata["process"],
                "script_name": metadata.get("script_name", "Unknown"),
            }
            for tab_id, metadata in self.processes.items()
        }

# Configure logging globally
logging.basicConfig(
    level=logging.DEBUG,  # Change to logging.DEBUG for more detailed output
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler("shutdown_log.txt", mode="w")  # Log to file
    ]
)

def monitor_shutdown_pipe(pipe_name, shutdown_event):
    """Monitor the named pipe for shutdown signals."""
    logging.info(f"Monitoring shutdown pipe in subprocess. Pipe: {pipe_name}")
    try:
        with open(pipe_name, "r", encoding="utf-8") as pipe:
            logging.info("Successfully connected to the shutdown pipe.")
            while not shutdown_event.is_set():
                try:
                    line = pipe.readline().strip()  # Blocking read
                    if not line:
                        if shutdown_event.is_set():
                            logging.info("Shutdown event detected. Exiting monitoring loop.")
                            break
                        time.sleep(0.1)
                        continue

                    logging.debug(f"Read line from pipe: {line}")
                    if line == "shutdown":
                        logging.info("Shutdown signal received in subprocess.")
                        shutdown_event.set()  # Notify the parent process
                        return
                except Exception as e:
                    logging.error(f"Exception while reading pipe: {e}")
                    break
    except Exception as e:
        logging.error(f"Failed to monitor shutdown pipe: {e}")
    finally:
        logging.info("Exiting monitor_shutdown_pipe subprocess.")


def main():
    """Main entry point for the script."""
    args = sys.argv
    logging.debug(f"args={args}")

    # Parse the --shutdown-pipe argument
    shutdown_pipe = None
    if "--shutdown-pipe" in args:
        shutdown_pipe = args[args.index("--shutdown-pipe") + 1]
        logging.debug(f"shutdown_pipe={shutdown_pipe}")
    else:
        logging.info("No --shutdown-pipe argument provided. Skipping pipe-based shutdown logic.")

    # Create a multiprocessing Event for shutdown
    shutdown_event = Event()

    # Start the shutdown monitoring subprocess if a pipe is provided
    monitor_process = None
    if shutdown_pipe:
        monitor_process = Process(target=monitor_shutdown_pipe, args=(shutdown_pipe, shutdown_event))
        monitor_process.start()
        logging.info("Started shutdown monitoring process.")

    # Define the main application shutdown logic
    def on_shutdown():
        logging.info("Shutdown signal received. Starting cleanup.")
        shutdown_event.set()  # Signal the subprocess to terminate
        app.on_close()  # Use the main application’s cleanup logic

    try:
        logging.info("Starting the application.")
        # Your main Tkinter application logic here
        root = ThemedTk(theme="black")
        app = ScriptLauncherApp(root)

        # Periodically check for the shutdown_event
        def check_shutdown():
            if shutdown_event.is_set():
                logging.info("Shutdown event detected in main application.")
                on_shutdown()
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
            shutdown_event.set()  # Ensure the subprocess knows to exit
            logging.debug("Waiting for shutdown monitoring process to exit...")
            monitor_process.join(timeout=5)
            if monitor_process.is_alive():
                logging.warning("Forcibly terminating the shutdown monitoring process.")
                monitor_process.terminate()

        logging.info("Application closed successfully.")


if __name__ == "__main__":
    main()