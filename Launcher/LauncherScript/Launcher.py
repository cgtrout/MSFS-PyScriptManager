import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from ttkthemes import ThemedTk  # Import ThemedTk to apply dark theme
from threading import Thread, Event
import subprocess
from pathlib import Path
from tkinter import TclError
from tkinter import scrolledtext
import psutil  # Import psutil for process management
import os
import time  # Import time for handling timeouts
from threading import Lock

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

def terminate_process_tree(pid, force=False):
    """Terminate a process and all its child processes."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)  # Get all child processes

        # Terminate children first
        for child in children:
            print(f"Terminating child process: {child.pid}")
            if not force:
                child.terminate()
            else:
                child.kill()

        # Terminate the parent process
        print(f"Terminating parent process: {pid}")
        if not force:
            parent.terminate()  # Try graceful termination
        else:
            parent.kill()  # Force kill
    except psutil.NoSuchProcess:
        print(f"Process with PID {pid} not found (might already be terminated).")
    except Exception as e:
        print(f"Error terminating process tree: {e}")

def attempt_graceful_shutdown(process, timeout=5):
    """Try to terminate the process gracefully, and force kill if it doesn't terminate within the timeout."""
    try:
        print(f"Attempting graceful termination of process with PID {process.pid}")
        process.terminate()  # Attempt graceful termination
        process.wait(timeout=timeout)  # Wait for the process to exit
        print(f"Process {process.pid} terminated gracefully.")
        return True
    except subprocess.TimeoutExpired:
        print(f"Process {process.pid} did not terminate within {timeout} seconds. Forcing termination...")
        terminate_process_tree(process.pid, force=True)  # Force termination if it doesn't exit in time
        return False
    except Exception as e:
        print(f"Error during graceful termination attempt: {e}")
        return False

class ScriptLauncherApp:
    def __init__(self, root):
        self.cpu_stats = {}  # Initialize a dictionary to store CPU stats for each script
        self.performance_metrics_open = False  # Track if the metrics tab is open
        self.cpu_stats_lock = Lock()
        self.closing = False

        self.root = root
        self.root.title("Python Script Launcher")
        self.root.geometry("1000x600")
        self.root.configure(bg=DARK_BG_COLOR)  # Dark background

        # Create a toolbar frame to hold buttons at the top, with flat relief
        self.toolbar = tk.Frame(self.root, bg=DARK_BG_COLOR)
        self.toolbar.pack(side="top", fill="x", padx=5, pady=5)

        # Add a button to the toolbar for selecting and running scripts
        self.run_button = tk.Button(self.toolbar, text="Run Script", command=self.select_and_run_script,
                                    bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR, activebackground=BUTTON_ACTIVE_BG_COLOR,
                                    activeforeground=BUTTON_ACTIVE_FG_COLOR, relief="flat", highlightthickness=0)
        self.run_button.pack(side="left", padx=5, pady=2)

        self.load_group_button = tk.Button(self.toolbar, text="Load Script Group", command=self.load_script_group,
                                           bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR, activebackground=BUTTON_ACTIVE_BG_COLOR,
                                           activeforeground=BUTTON_ACTIVE_FG_COLOR, relief="flat", highlightthickness=0)
        self.load_group_button.pack(side="right", padx=5, pady=2)
        
        # Add buttons for saving and loading script groups
        self.save_group_button = tk.Button(self.toolbar, text="Save Script Group", command=self.save_script_group,
                                           bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR, activebackground=BUTTON_ACTIVE_BG_COLOR,
                                           activeforeground=BUTTON_ACTIVE_FG_COLOR, relief="flat", highlightthickness=0)
        self.save_group_button.pack(side="right", padx=5, pady=2)

        self.performance_metrics_button = tk.Button(
                    self.toolbar, text="Performance Metrics", command=self.open_performance_metrics_tab,
                    bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR, activebackground=BUTTON_ACTIVE_BG_COLOR,
                    activeforeground=BUTTON_ACTIVE_FG_COLOR, relief="flat", highlightthickness=0
                )
        self.performance_metrics_button.pack(side="right", padx=5, pady=2)

        # Create a notebook to show multiple tabs (for script output)
        self.notebook = ttk.Notebook(self.root)

        # Set notebook style to reduce padding and border size
        style = ttk.Style()
        style.configure('TNotebook', padding=[0, 0])
        style.configure('TNotebook.Tab', padding=[5, 2])
        style.configure('TFrame', background=DARK_BG_COLOR)

        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Bind right-click to notebook tabs for direct closure
        self.notebook.bind("<Button-3>", self.on_tab_right_click)

        # Store script execution details
        self.processes = {}  # Store subprocess and tab details here
        self.process_pids = []  # Keep track of the PIDs of processes launched by the app
        self.stop_events = {}
        self.tab_frames = {}
        self.current_tab_id = 0  # Initialize the unique tab ID counter
        self.lock = Lock()  # Lock to synchronize access to shared resources

        # Override close window behavior to ensure all processes are killed
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Call autoplay_script_group to automatically load the script _auto group file at startup
        self.autoplay_script_group()

    def initialize_cpu_percent(self):
        """Initialize CPU percent measurement for each process and its children."""
        try:
            for process_info in self.processes.values():
                process = process_info.get('process')
                if process and process.pid:
                    proc = psutil.Process(process.pid)
                    proc.cpu_percent(interval=0.1)  # Initialize for the parent process with a small interval
                    for child in proc.children(recursive=True):
                        child.cpu_percent(interval=0.1)  # Initialize for children with the same interval
        except Exception as e:
            print(f"Error initializing CPU metrics: {e}")


    def open_performance_metrics_tab(self):
        print("Opening performance metrics tab...")
        tab_id = self.generate_tab_id()
        with self.lock:
            self.performance_metrics_tab_id = tab_id
            self.performance_metrics_open = True

        def create_tab():
            print("Creating performance metrics tab...")
            self.performance_metrics_tab = ttk.Frame(self.notebook)
            self.notebook.add(self.performance_metrics_tab, text="Performance Metrics")
            self.notebook.select(self.performance_metrics_tab)

            self.performance_text_widget = scrolledtext.ScrolledText(
                self.performance_metrics_tab, wrap="word", bg=TEXT_WIDGET_BG_COLOR, fg=TEXT_WIDGET_FG_COLOR,
                insertbackground=TEXT_WIDGET_INSERT_COLOR
            )
            self.performance_text_widget.pack(expand=True, fill="both")

            # Add the tab to the tab_frames outside of the lock
            self.tab_frames[self.performance_metrics_tab_id] = self.performance_metrics_tab
            print(f"Performance metrics tab added to tab_frames with ID: {self.performance_metrics_tab_id}")

            # Start monitoring after the tab is created
            self.root.after(100, self.monitor_performance_metrics)

        # Schedule the tab creation
        self.root.after(0, create_tab)

    def monitor_performance_metrics(self):
        """Periodically update the performance metrics tab."""
        def update_metrics():
            while self.performance_metrics_open:
                try:
                    metrics_text = self.generate_metrics_text()
                    self.root.after(0, lambda: self.refresh_performance_metrics(metrics_text))
                except Exception as e:
                    print(f"Error in performance metrics update: {e}")
                time.sleep(1)  # Update every second

        self.performance_thread = Thread(target=update_metrics, daemon=True)
        self.performance_thread.start()

    def refresh_performance_metrics(self, text):
        """Refresh the performance metrics text widget."""
        if hasattr(self, 'performance_text_widget') and self.performance_text_widget.winfo_exists():
            self.performance_text_widget.delete('1.0', tk.END)
            self.performance_text_widget.insert(tk.END, text)

    def safe_refresh_performance_metrics(self, text):
        # Only update if tab and widget still exist
        if self.performance_metrics_open and hasattr(self, 'performance_text_widget'):
            if self.performance_text_widget.winfo_exists():
                self.performance_text_widget.delete('1.0', tk.END)
                self.performance_text_widget.insert(tk.END, text)


    def generate_metrics_text(self):
        """Generate a text representation of performance metrics dynamically."""
        metrics = []

        if not self.processes:
            return "No scripts are currently running."

        total_cores = psutil.cpu_count(logical=True)  # Get total logical cores
        with self.lock:
            processes_snapshot = dict(self.processes)

        for tab_id, process_info in processes_snapshot.items():
            process = process_info.get('process')
            script_name = Path(process_info.get('script_path', 'Unknown')).name

            if process and process.pid:
                try:
                    proc = psutil.Process(process.pid)
                    if proc.is_running():
                        # Initialize stats tracking if not already done
                        if tab_id not in self.cpu_stats:
                            self.cpu_stats[tab_id] = {"cumulative_cpu": 0, "count": 0, "peak_cpu": 0}
                            proc.cpu_percent(interval=None)  # Establish baseline for measurement

                        # Ensure a small delay to avoid sampling conflict
                        total_cpu_usage = proc.cpu_percent(interval=0.1)
                        total_memory_usage = proc.memory_info().rss  # Memory usage in bytes

                        for child in proc.children(recursive=True):
                            if child.is_running():
                                total_cpu_usage += child.cpu_percent(interval=0.1)
                                total_memory_usage += child.memory_info().rss

                        # Normalize CPU usage to total cores
                        normalized_cpu_usage = total_cpu_usage / total_cores
                        self.cpu_stats[tab_id]["cumulative_cpu"] += normalized_cpu_usage
                        self.cpu_stats[tab_id]["count"] += 1
                        self.cpu_stats[tab_id]["peak_cpu"] = max(
                            self.cpu_stats[tab_id]["peak_cpu"], normalized_cpu_usage
                        )

                        # Compute average CPU usage
                        avg_cpu_usage = (
                            self.cpu_stats[tab_id]["cumulative_cpu"] / self.cpu_stats[tab_id]["count"]
                        )
                        peak_cpu_usage = self.cpu_stats[tab_id]["peak_cpu"]

                        # Convert memory usage to MB
                        total_memory_usage_mb = total_memory_usage / (1024 ** 2)

                        metrics.append(
                            f"Script: {script_name}\n"
                            f"  PID: {process.pid}\n"
                            f"  Average CPU Usage: {avg_cpu_usage:.2f}%\n"
                            f"  Peak CPU Usage: {peak_cpu_usage:.2f}%\n"
                            f"  Memory Usage: {total_memory_usage_mb:.2f} MB\n"
                        )
                    else:
                        metrics.append(f"Script: {script_name}\n  Status: Not Running\n")
                except psutil.NoSuchProcess:
                    metrics.append(f"Script: {script_name}\n  Status: Process Terminated\n")
            else:
                metrics.append(f"Script: {script_name}\n  Status: Not Running\n")

        return "\n".join(metrics)


    def stop_performance_monitoring(self):
        """Stop monitoring performance metrics and reset related attributes."""
        if hasattr(self, 'performance_thread') and self.performance_thread:
            print("Stopping performance monitoring thread...")
            self.performance_thread = None  # Mark the thread as stopped
        else:
            print("No active performance monitoring thread to stop.")

    def refresh_performance_metrics(self, text):
        """Clear and refresh the performance metrics text."""
        if hasattr(self, 'performance_text_widget'):
            self.performance_text_widget.delete('1.0', tk.END)  # Clear text
            self.performance_text_widget.insert(tk.END, text)   # Insert updated metrics

    def autoplay_script_group(self):
        """Automatically load a script group file named '_autoplay.script_group' located in the Scripts directory."""
        # Set path to '_autoplay.script_group' within the Scripts directory
        autoplay_path = scripts_path / "_autoplay.script_group"
        
        # Check if the file exists and load it if it does
        if autoplay_path.exists():
            print(f"Autoplay: Loading script group from {autoplay_path}")
            self.load_script_group_from_path(autoplay_path)
        else:
            print("Autoplay: No '_autoplay.script_group' file found at startup. Skipping autoplay.")

    def generate_tab_id(self):
        """Generates a unique tab ID by incrementing the counter."""
        with self.lock:  # Protect access to self.current_tab_id
            self.current_tab_id += 1
            return self.current_tab_id

    def create_output_text_widget(self, parent):
        text_widget = scrolledtext.ScrolledText(parent, wrap="word", bg=TEXT_WIDGET_BG_COLOR, fg=TEXT_WIDGET_FG_COLOR, 
                                                insertbackground=TEXT_WIDGET_INSERT_COLOR)
        text_widget.pack(expand=True, fill="both")
        
        return text_widget

    def insert_output(self, tab_id, text):
        """Insert text into the corresponding Text widget in a thread-safe way."""
        with self.lock:  
            # Safely check if tab_id exists in processes
            if tab_id not in self.processes:
                return
            tab = self.processes[tab_id].get('tab')

        # Use root.after to schedule the update in the main thread
        if tab and tab.winfo_exists():
            self.root.after(0, lambda: self._safe_insert(tab, text))

    def _safe_insert(self, tab, text):
        """Safely insert text into the Text widget."""
        try:
            tab.insert(tk.END, text)
            tab.see(tk.END)  # Scroll to the end
        except Exception as e:
            print(f"Error inserting text into tab: {e}")

    def run_script(self, script_path, tab_id):
        """Run the selected script using the portable Python interpreter and display output."""
        print(f"run_script: {script_path} tab_id: {tab_id}")
        with self.lock:
            self.processes[tab_id]['script_path'] = str(script_path)

        # Start the run method in a separate thread
        Thread(target=self.run, args=(script_path, tab_id), daemon=True).start()

    def run(self, script_path, tab_id):
        """Run the script and manage its process."""
        process = None
        try:
            process = subprocess.Popen(
                [str(pythonw_path.resolve()), "-u", str(script_path.resolve())],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,  # Enable text mode
                bufsize=1   # Line-buffered
            )

            with self.lock: 
                # Track the PID of this process
                self.process_pids.append(process.pid)

                self.processes[tab_id]['process'] = process
                self.stop_events[tab_id] = Event()

            # Create and start threads for reading stdout and stderr
            stdout_thread = Thread(target=self.read_output, args=(process.stdout, tab_id))
            stderr_thread = Thread(target=self.read_output, args=(process.stderr, tab_id))

            stdout_thread.start()
            stderr_thread.start()

            with self.lock: 
                self.processes[tab_id]['stdout_thread'] = stdout_thread
                self.processes[tab_id]['stderr_thread'] = stderr_thread

            # Wait for the process to finish
            process.wait()

            stdout_thread.join()
            stderr_thread.join()

            exit_code = process.returncode
            if tab_id in self.processes:
                self.insert_output(tab_id, f"\nScript finished with exit code {exit_code}\n")
                with self.lock:
                    self.processes[tab_id]['process'] = None

        except Exception as e:
            error_message = f"Error running script {script_path}: {e}\n"
            self.insert_output(tab_id, error_message)
            if process and process.pid:
                terminate_process_tree(process.pid)

    def read_output(self, pipe, tab_id):
        """Read output from the process and insert it into the corresponding tab."""
        try:
            for line in iter(pipe.readline, ''):
                with self.lock:
                    if tab_id in self.stop_events and self.stop_events[tab_id].is_set():
                        break
                # Safely schedule output insertion in the main thread
                self.root.after(0, self._insert_text, tab_id, line)
        except Exception as e:
            # Log the error to the console
            print(f"Error reading output for Tab ID {tab_id}: {e}")

    def _insert_text(self, tab_id, text):
        """Internal function to insert text directly into the widget."""
        # Protect access to shared resources
        with self.lock:
            if tab_id not in self.processes:
                print(f"Tab ID {tab_id} not found in processes. Skipping text insertion.")
                return
            tab = self.processes[tab_id].get('tab')

        # Ensure UI operations are performed in the main thread
        if tab and tab.winfo_exists():
            try:
                tab.insert(tk.END, text)
                tab.see(tk.END)  # Scroll to the end
            except Exception as e:
                print(f"Error inserting text into widget for Tab ID {tab_id}: {e}")

    def select_and_run_script(self):
        """Open a file dialog to select and run a Python script, then create a new tab for it."""
        file_path = filedialog.askopenfilename(
            title="Select Python Script",
            filetypes=[("Python Files", "*.py")],
            initialdir=str(project_root / "Scripts"),
            parent=self.root
        )

        if not file_path:
            return

        # Generate a new, unique tab ID 
        tab_id = self.generate_tab_id()

        # Run the script in a new tab...
        self.run_script_with_tab(Path(file_path), tab_id)

    def run_script_with_tab(self, script_path, tab_id):
        """Helper to run a script in a new tab."""
        script_name = script_path.name
        new_tab = ttk.Frame(self.notebook)
        self.notebook.add(new_tab, text=script_name)

        # Add this line to make the newly created tab the active one
        self.notebook.select(new_tab)

        # Create a text widget in the new tab to display script output
        output_text = self.create_output_text_widget(new_tab)

        # Add a frame at the bottom for buttons
        button_frame = tk.Frame(new_tab, bg=FRAME_BG_COLOR)
        button_frame.pack(side="bottom", fill="x", padx=5, pady=5)

        # Add "Edit" and "Reload" buttons to the button frame
        edit_button = tk.Button(button_frame, text="Edit Script", command=lambda: self.edit_script(tab_id),
                                bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR, activebackground=BUTTON_ACTIVE_BG_COLOR,
                                activeforeground=BUTTON_ACTIVE_FG_COLOR, relief="flat", highlightthickness=0)
        edit_button.pack(side="left", padx=5, pady=2)

        reload_button = tk.Button(button_frame, text="Reload Script", command=lambda: self.reload_script(tab_id),
                                bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR, activebackground=BUTTON_ACTIVE_BG_COLOR,
                                activeforeground=BUTTON_ACTIVE_FG_COLOR, relief="flat", highlightthickness=0)
        reload_button.pack(side="left", padx=5, pady=2)

        # Track the process, stop event, and tab frame
        with self.lock:
            self.processes[tab_id] = {'tab': output_text, 'process': None, 'script_path': str(script_path)}
            self.stop_events[tab_id] = Event()
            self.tab_frames[tab_id] = new_tab

        # Run the script
        self.run_script(script_path, tab_id)

    def save_script_group(self):
        """Save the currently open tabs (scripts) to a .script_group file with relative paths."""
        file_path = filedialog.asksaveasfilename(
            title="Save Script Group",
            defaultextension=".script_group",
            filetypes=[("Script Group Files", "*.script_group")]
        )

        if not file_path:
            return

        # Get the directory of the .script_group file to save relative paths
        group_dir = Path(file_path).parent

        script_paths = []
        for process_info in self.processes.values():
            if 'script_path' in process_info:
                script_absolute_path = Path(process_info['script_path'])
                # Calculate the relative path to the script from the .script_group file location
                relative_path = os.path.relpath(script_absolute_path, group_dir)
                script_paths.append(relative_path)

        # Write the relative paths to the .script_group file
        with open(file_path, 'w') as f:
            f.writelines(f"{path}\n" for path in script_paths)

    def load_script_from_path(self, script_path_str):
        """Load and run a script from a specified file path."""
        script_path = Path(script_path_str)

        # Check if the file exists
        if not script_path.exists():
            print(f"Error: Script '{script_path}' not found.")
            return

        # Generate a unique tab ID for the script
        tab_id = self.generate_tab_id()

        # Load and run the script in a new tab
        self.run_script_with_tab(script_path, tab_id)

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

        # Ensure the file exists before attempting to read
        if not file_path.exists():
            print(f"Error: Script group file '{file_path}' not found.")
            return

        # Read the script paths from the file and resolve them relative to the group file's directory
        with open(file_path, 'r') as f:
            script_paths = [group_dir / Path(line.strip()) for line in f.readlines() if line.strip()]

        # Use a set to avoid loading duplicate scripts
        loaded_scripts = set()

        # Load each script in the script group file
        for script_path in script_paths:
            absolute_path = script_path.resolve()

            if str(absolute_path) not in loaded_scripts:
                loaded_scripts.add(str(absolute_path))
                self.load_script_from_path(absolute_path)

    def edit_script(self, tab_id):
        """Open the selected script in VSCode for editing."""
        if tab_id in self.processes:
            script_path = self.processes[tab_id]['script_path']
            self.insert_output(tab_id, f"Opening script {script_path} for editing in VS Code...\n")
            subprocess.Popen([str(vscode_path.resolve()), script_path])

    def reload_script(self, tab_id):
        if tab_id in self.processes:
            script_path = Path(self.processes[tab_id]['script_path'])
            
            # Close the existing tab and cleanup
            self.close_tab(tab_id)
            
            # Generate a new, unique tab ID for the reload
            new_tab_id = self.generate_tab_id()
            
            # Run the script in a new tab with the new tab ID
            self.run_script_with_tab(script_path, new_tab_id)

    def terminate_and_cleanup(self, tab_id, process, stdout_thread, stderr_thread):
        """Terminate the process, and clean up stdout and stderr threads."""
        # First attempt graceful shutdown
        if process and process.pid:
            print(f"Attempting to terminate process with PID {process.pid} for tab {tab_id}")
            graceful = attempt_graceful_shutdown(process)  # Try graceful termination

            if not graceful:
                print(f"Process {process.pid} had to be forcefully terminated for tab {tab_id}")

        # Wait for the threads to finish without blocking the UI
        if stdout_thread is not None:
            stdout_thread.join()
        if stderr_thread is not None:
            stderr_thread.join()

    def terminate_tracked_processes(self, tab_id):
        """Terminate the process associated with a specific tab_id."""
        process_info = self.processes.get(tab_id)
        if process_info and process_info.get('process'):
            pid = process_info['process'].pid
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    print(f"Attempting graceful shutdown for pythonw process with PID {pid}")
                    graceful = attempt_graceful_shutdown(proc)
                    if not graceful:
                        print(f"Force terminating pythonw process with PID {pid}")
                print(f"Removed PID {pid} from tracked process list.")
            except psutil.NoSuchProcess:
                print(f"Process with PID {pid} not found (might already be terminated).")
            except Exception as e:
                print(f"Error terminating process with PID {pid}: {e}")

    def close_tab_by_index(self, tab_index):
        """Close a tab by its index."""
        # Make a snapshot of the items to avoid modification issues
        with self.lock:
            tab_frames_snapshot = list(self.tab_frames.items())

        for tab_id, frame in tab_frames_snapshot:
            try:
                if self.notebook.index(frame) == tab_index:
                    print(f"Closing tab with index: {tab_index}")
                    self.close_tab(tab_id)
                    return
            except Exception as e:
                print(f"Error accessing tab index {tab_index}: {e}")

    def close_tab(self, tab_id):
        """Close a tab and clean up its associated resources."""
        if tab_id == getattr(self, 'performance_metrics_tab_id', None):
            # Stop monitoring performance metrics
            self.stop_performance_monitoring()

            # Remove the performance metrics tab from the notebook
            if hasattr(self, 'performance_metrics_tab') and self.performance_metrics_tab:
                try:
                    self.notebook.forget(self.performance_metrics_tab)
                except Exception:
                    print(f"Error forgetting the performance metrics tab (ID: {tab_id}).")
            
            # Perform cleanup
            self.cleanup_performance_tab(tab_id)
            return

        # General tab closing logic for other tabs
        with self.lock:
            if tab_id not in self.processes:
                print(f"Tab ID {tab_id} not found. Nothing to close.")
                return

            process_info = self.processes[tab_id]
            process = process_info.get('process')
            stdout_thread = process_info.get('stdout_thread')
            stderr_thread = process_info.get('stderr_thread')

            # Signal threads to stop
            if tab_id in self.stop_events:
                self.stop_events[tab_id].set()

        # Perform process termination
        if process and process.pid:
            attempt_graceful_shutdown(process)

        if stdout_thread and stdout_thread.is_alive():
            stdout_thread.join(timeout=2)
        if stderr_thread and stderr_thread.is_alive():
            stderr_thread.join(timeout=2)

        # Remove tab from the notebook and clean up
        with self.lock:
            if tab_id in self.tab_frames:
                try:
                    self.notebook.forget(self.tab_frames[tab_id])
                except Exception as e:
                    print(f"Error removing tab {tab_id}: {e}")

            self.processes.pop(tab_id, None)
            self.stop_events.pop(tab_id, None)
            self.tab_frames.pop(tab_id, None)

    def cleanup_performance_tab(self, tab_id):
        """Clean up resources associated with the performance metrics tab."""
        with self.lock:
            # Reset attributes related to the performance metrics tab
            if tab_id == getattr(self, 'performance_metrics_tab_id', None):
                self.performance_metrics_tab = None
                self.performance_metrics_tab_id = None
                print("cleanup_perf")
                self.performance_metrics_open = False

            # Remove tab reference from tab frames
            self.tab_frames.pop(tab_id, None)
            print(f"Performance metrics tab (ID: {tab_id}) has been cleaned up.")

    def on_tab_right_click(self, event):
        """Handle right-click event on notebook tabs for direct tab closing."""
        try:
            
            # Get the index of the clicked tab
            print("DEBUG: on_tab_right_click: enter")
            clicked_tab_index = self.notebook.index(f"@{event.x},{event.y}")
            print(f"Right-clicked on tab with index: {clicked_tab_index}")
            self.close_tab_by_index(clicked_tab_index)  # Directly close the tab
        except TclError as e:
            print(f"Error: on_tab_right_click error - Details: {e}")

    def terminate_tracked_processes_on_close(self):
        """Terminate any remaining processes left in self.process_pids on app close."""
        for pid in self.process_pids[:]:
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    print(f"Attempting graceful shutdown for pythonw process with PID {pid}")
                    graceful = attempt_graceful_shutdown(proc)
                    if not graceful:
                        print(f"Force terminating pythonw process with PID {pid}")
                with self.lock: 
                    self.process_pids.remove(pid)  # Remove PID from tracking after termination
                print(f"Removed PID {pid} from tracked process list.")
            except psutil.NoSuchProcess:
                print(f"Process with PID {pid} not found (might already be terminated).")
            except Exception as e:
                print(f"Error terminating process with PID {pid}: {e}")

    def on_close(self):
        """
        Handle window close event: terminate all running scripts and close the application.
        """
        if self.closing:
            print("LAUNCHER: on_close() already called. Skipping redundant cleanup.")
            return

        print("LAUNCHER: on_close() called. Starting cleanup...")
        self.closing = True  # Mark cleanup as started

        # Signal threads to stop
        for tab_id, process_info in self.processes.items():
            stop_event = process_info.get('stop_event')
            if stop_event:
                stop_event.set()  # Signal threads to stop

            stdout_thread = process_info.get('stdout_thread')
            stderr_thread = process_info.get('stderr_thread')

            if stdout_thread and stdout_thread.is_alive():
                stdout_thread.join(timeout=1)
            if stderr_thread and stderr_thread.is_alive():
                stderr_thread.join(timeout=1)

        # Terminate subprocesses and clean up tabs
        print("LAUNCHER: Terminating subprocesses...")
        self.terminate_tracked_processes_on_close()

        for tab_id in list(self.processes.keys()):
            print(f"LAUNCHER: Closing tab {tab_id}...")
            self.close_tab(tab_id)

        # Destroy the root window
        print("LAUNCHER: Stopping mainloop and destroying root...")
        self.root.quit()  # Stop the mainloop
        self.root.destroy()  # Destroy all widgets
        print("LAUNCHER: on_close() completed.")


# Create the main window (root) for the UI with a dark theme
root = ThemedTk(theme="black")  # Applying dark theme using ThemedTk

# Create the app using the root window
app = ScriptLauncherApp(root)

# Start the Tkinter event loop
root.mainloop()
