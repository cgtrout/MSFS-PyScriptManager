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

        # Override close window behavior to ensure all processes are killed
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Call autoplay_script_group to automatically load the script _auto group file at startup
        self.autoplay_script_group()

    def open_performance_metrics_tab(self):
        """Open a single instance of the Performance Metrics tab."""
        if self.performance_metrics_open:
            # Bring the existing tab to the front if it's already open
            self.notebook.select(self.performance_metrics_tab)
            print("Performance Metrics tab is already open.")
            return

        # Create the tab and set the flag
        self.performance_metrics_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.performance_metrics_tab, text="Performance Metrics")
        self.notebook.select(self.performance_metrics_tab)

        self.performance_text_widget = scrolledtext.ScrolledText(
            self.performance_metrics_tab, wrap="word", bg=TEXT_WIDGET_BG_COLOR, fg=TEXT_WIDGET_FG_COLOR,
            insertbackground=TEXT_WIDGET_INSERT_COLOR
        )
        self.performance_text_widget.pack(expand=True, fill="both")

        # Track the tab and start monitoring
        tab_id = self.generate_tab_id()
        self.tab_frames[tab_id] = self.performance_metrics_tab
        self.performance_metrics_tab_id = tab_id
        self.performance_metrics_open = True  # Set the flag

        self.monitor_performance_metrics()  # Start the monitoring thread

    def monitor_performance_metrics(self):
        """Periodically update the performance metrics tab."""
        def update_metrics():
            while True:
                if not hasattr(self, 'performance_metrics_tab'):
                    break  # Exit if the tab has been closed

                metrics_text = self.generate_metrics_text()
                self.root.after(0, lambda: self.refresh_performance_metrics(metrics_text))
                
                time.sleep(0.5)  # Refresh every 0.5 seconds for more frequent updates

        self.performance_thread = Thread(target=update_metrics, daemon=True)
        self.performance_thread.start()


    def generate_metrics_text(self):
        """Generate a text representation of performance metrics dynamically."""
        metrics = []
        processes_copy = self.processes.copy()  # Create a snapshot to avoid iteration issues
        for tab_id, process_info in processes_copy.items():
            process = process_info.get('process')
            script_name = Path(process_info.get('script_path', 'Unknown')).name
            if process and process.pid:
                try:
                    proc = psutil.Process(process.pid)
                    if proc.is_running():
                        # Aggregate CPU and memory usage
                        total_cpu_usage = proc.cpu_percent(interval=0.1) / psutil.cpu_count()
                        total_memory_usage = proc.memory_info().rss  # In bytes
                        for child in proc.children(recursive=True):
                            if child.is_running():
                                total_cpu_usage += child.cpu_percent(interval=0.1) / psutil.cpu_count()
                                total_memory_usage += child.memory_info().rss

                        # Track stats for averages and peaks
                        if tab_id not in self.cpu_stats:
                            self.cpu_stats[tab_id] = {"cumulative_cpu": 0, "count": 0, "peak_cpu": 0}

                        self.cpu_stats[tab_id]["cumulative_cpu"] += total_cpu_usage
                        self.cpu_stats[tab_id]["count"] += 1
                        self.cpu_stats[tab_id]["peak_cpu"] = max(self.cpu_stats[tab_id]["peak_cpu"], total_cpu_usage)

                        avg_cpu_usage = self.cpu_stats[tab_id]["cumulative_cpu"] / self.cpu_stats[tab_id]["count"]
                        peak_cpu_usage = self.cpu_stats[tab_id]["peak_cpu"]

                        # Convert memory usage to MB
                        total_memory_usage_mb = total_memory_usage / (1024 ** 2)

                        metrics.append(
                            f"Script: {script_name}\n"
                            f"  PID: {process.pid}\n"
                            f"  Current CPU Usage: {total_cpu_usage:.2f}%\n"
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
        self.current_tab_id += 1
        return self.current_tab_id

    def create_output_text_widget(self, parent):
        text_widget = scrolledtext.ScrolledText(parent, wrap="word", bg=TEXT_WIDGET_BG_COLOR, fg=TEXT_WIDGET_FG_COLOR, 
                                                insertbackground=TEXT_WIDGET_INSERT_COLOR)
        text_widget.pack(expand=True, fill="both")
        
        return text_widget

    def insert_output(self, tab_id, text):
        """Insert text into the corresponding Text widget in a thread-safe way."""
        self.root.after(0, lambda: self._insert_output(tab_id, text))

    def _insert_output(self, tab_id, text):
        """Actual insertion of text into the Text widget."""
        if tab_id in self.processes:
            tab = self.processes[tab_id].get('tab')
            if tab:
                tab.insert(tk.END, text)
                tab.see(tk.END)  # Scroll to the end

    def run_script(self, script_path, tab_id):
        """Run the selected script using the portable Python interpreter and display output."""
        print(f"run_script: {script_path} tab_id: {tab_id}")
        self.processes[tab_id]['script_path'] = str(script_path)

        def read_output(pipe, insert_function, tab_id):
            """Read from the provided pipe and insert output into the GUI."""
            try:
                with pipe:
                    for line in iter(pipe.readline, ''):
                        if self.stop_events[tab_id].is_set():
                            break  # Exit reading loop if stop event is set
                        insert_function(tab_id, line)
            except Exception as e:
                error_message = f"Error reading output for tab {tab_id}: {e}\n"
                self.insert_output(tab_id, error_message)

        def run():
            process = None
            try:
                process = subprocess.Popen(
                    [str(pythonw_path.resolve()), "-u", str(script_path.resolve())],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

                # Track the PID of this process
                self.process_pids.append(process.pid)

                self.processes[tab_id]['process'] = process
                self.stop_events[tab_id] = Event()

                stdout_thread = Thread(target=read_output, args=(process.stdout, self.insert_output, tab_id))
                stderr_thread = Thread(target=read_output, args=(process.stderr, self.insert_output, tab_id))

                stdout_thread.start()
                stderr_thread.start()

                self.processes[tab_id]['stdout_thread'] = stdout_thread
                self.processes[tab_id]['stderr_thread'] = stderr_thread

                process.wait()

                stdout_thread.join()
                stderr_thread.join()

                exit_code = process.returncode
                if tab_id in self.processes:
                    self.insert_output(tab_id, f"\nScript finished with exit code {exit_code}\n")
                    self.processes[tab_id]['process'] = None

            except Exception as e:
                error_message = f"Error running script {script_path}: {e}\n"
                self.insert_output(tab_id, error_message)
                if process and process.pid:
                    terminate_process_tree(process.pid)

        Thread(target=run, daemon=True).start()

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
        for tab_id, frame in self.tab_frames.items():
            if self.notebook.index(frame) == tab_index:
                print(f"Closing tab with index: {tab_index}")
                self.close_tab(tab_id)
                return

    def close_tab(self, tab_id):
        """Close a specific tab and terminate the script or stop monitoring."""
        # Handle "Performance Metrics" tab
        if tab_id == getattr(self, 'performance_metrics_tab_id', None):
            print(f"Closing Performance Metrics tab (tab_id: {tab_id})")
            self.stop_performance_monitoring()  # Stop the monitoring thread

            try:
                self.notebook.forget(self.performance_metrics_tab)  # Remove the tab from the notebook
            except Exception as e:
                print(f"Error while removing Performance Metrics tab: {e}")

            # Clean up associated state
            if tab_id in self.tab_frames:
                del self.tab_frames[tab_id]
            if hasattr(self, 'performance_metrics_tab'):
                del self.performance_metrics_tab
            if hasattr(self, 'performance_text_widget'):
                del self.performance_text_widget
            if hasattr(self, 'performance_metrics_tab_id'):
                del self.performance_metrics_tab_id

            self.performance_metrics_open = False  # Reset the flag
            return
        
        # Handle other script tabs
        if tab_id in self.processes:
            print(f"Closing script tab (tab_id: {tab_id})")
            process_info = self.processes[tab_id]
            process = process_info.get('process')
            stdout_thread = process_info.get('stdout_thread')
            stderr_thread = process_info.get('stderr_thread')

            # Stop process threads
            self.stop_events[tab_id].set()
            cleanup_thread = Thread(target=self.terminate_and_cleanup, args=(tab_id, process, stdout_thread, stderr_thread))
            cleanup_thread.daemon = True
            cleanup_thread.start()

            # Remove the tab from the notebook
            try:
                self.notebook.forget(self.tab_frames[tab_id])
                print(f"Script tab (tab_id: {tab_id}) removed from notebook.")
            except KeyError:
                print(f"Tab {tab_id} not found in tab_frames.")
            except Exception as e:
                print(f"Error while removing script tab: {e}")

            # Clean up associated state
            del self.processes[tab_id]
            del self.stop_events[tab_id]
            del self.tab_frames[tab_id]

    def on_tab_right_click(self, event):
        """Handle right-click event on notebook tabs for direct tab closing."""
        # Get the index of the clicked tab
        try:
            clicked_tab_index = self.notebook.index(f"@{event.x},{event.y}")
            print(f"Right-clicked on tab with index: {clicked_tab_index}")
            self.close_tab_by_index(clicked_tab_index)  # Directly close the tab
        except TclError:
            return

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
                self.process_pids.remove(pid)  # Remove PID from tracking after termination
                print(f"Removed PID {pid} from tracked process list.")
            except psutil.NoSuchProcess:
                print(f"Process with PID {pid} not found (might already be terminated).")
            except Exception as e:
                print(f"Error terminating process with PID {pid}: {e}")

    def on_close(self):
        """Handle window close event: terminate all running scripts and close the application."""
        tab_ids = list(self.processes.keys())
        
        # Try to close all tabs and terminate associated processes
        for tab_id in tab_ids:
            try:
                self.close_tab(tab_id)  # This will invoke terminate_and_cleanup for each tab
            except Exception as e:
                print(f"Error closing tab {tab_id}: {e}")
        
        # Give some time to allow processes to terminate gracefully
        time.sleep(0.5)  # Optional: give a short delay to ensure background threads finish

        print("Ensuring all launched pythonw processes are terminated...")

        # Terminate any remaining tracked processes (just in case some were missed)
        self.terminate_tracked_processes_on_close()

        # Finally, destroy the Tkinter root window
        self.root.destroy()

# Create the main window (root) for the UI with a dark theme
root = ThemedTk(theme="black")  # Applying dark theme using ThemedTk

# Create the app using the root window
app = ScriptLauncherApp(root)

# Start the Tkinter event loop
root.mainloop()
