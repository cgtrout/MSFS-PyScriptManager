import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from ttkthemes import ThemedTk  # Import ThemedTk to apply dark theme
from threading import Thread, Event
import subprocess
from pathlib import Path
from tkinter import TclError

# Path to the WinPython Python executable and VS Code.exe
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parents[1]
python_path = project_root / "WinPython" / "python-3.13.0rc1.amd64" / "python.exe"
pythonw_path = python_path.with_name("pythonw.exe")  # Use pythonw.exe to prevent console window
vscode_path = project_root / "WinPython" / "VS Code.exe"  # Dynamically calculated path to VS Code.exe
print(f"Python path: {pythonw_path.resolve()}")
print(f"VS Code path: {vscode_path.resolve()}")

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

class ScriptLauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Script Launcher")
        self.root.geometry("800x600")
        self.root.configure(bg=DARK_BG_COLOR)  # Dark background

        # Create a toolbar frame to hold buttons at the top, with flat relief
        self.toolbar = tk.Frame(self.root, bg=DARK_BG_COLOR)
        self.toolbar.pack(side="top", fill="x", padx=5, pady=5)

        # Add a button to the toolbar for selecting and running scripts
        self.run_button = tk.Button(self.toolbar, text="Select and Run Script", command=self.select_and_run_script,
                                    bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR, activebackground=BUTTON_ACTIVE_BG_COLOR,
                                    activeforeground=BUTTON_ACTIVE_FG_COLOR, relief="flat", highlightthickness=0)
        self.run_button.pack(side="left", padx=5, pady=2)

        # Add buttons for saving and loading script groups
        self.save_group_button = tk.Button(self.toolbar, text="Save Script Group", command=self.save_script_group,
                                           bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR, activebackground=BUTTON_ACTIVE_BG_COLOR,
                                           activeforeground=BUTTON_ACTIVE_FG_COLOR, relief="flat", highlightthickness=0)
        self.save_group_button.pack(side="left", padx=5, pady=2)

        self.load_group_button = tk.Button(self.toolbar, text="Load Script Group", command=self.load_script_group,
                                           bg=BUTTON_BG_COLOR, fg=BUTTON_FG_COLOR, activebackground=BUTTON_ACTIVE_BG_COLOR,
                                           activeforeground=BUTTON_ACTIVE_FG_COLOR, relief="flat", highlightthickness=0)
        self.load_group_button.pack(side="left", padx=5, pady=2)

        # Create a notebook to show multiple tabs (for script output)
        self.notebook = ttk.Notebook(self.root)

        # Set notebook style to reduce padding and border size
        style = ttk.Style()
        style.configure('TNotebook', padding=[0, 0])
        style.configure('TNotebook.Tab', padding=[5, 2])
        style.configure('TFrame', background=DARK_BG_COLOR)

        self.notebook.pack(expand=True, fill="both", padx=5, pady=5)

        # Bind right-click to notebook tabs for closing functionality
        self.notebook.bind("<Button-3>", self.on_tab_right_click)

        # Store script execution details
        self.processes = {}
        self.stop_events = {}
        self.tab_frames = {}
        self.current_tab_id = 0  # Initialize the unique tab ID counter

        # Override close window behavior to ensure all processes are killed
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def generate_tab_id(self):
        """Generates a unique tab ID by incrementing the counter."""
        self.current_tab_id += 1
        return self.current_tab_id

    def create_output_text_widget(self, parent):
        """Create a scrollable text widget to display script output."""
        text_widget = tk.Text(parent, wrap="word", bg=TEXT_WIDGET_BG_COLOR, fg=TEXT_WIDGET_FG_COLOR, 
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
        self.processes[tab_id]['script_path'] = str(script_path)

        def read_output(pipe, insert_function, tab_id):
            """Read from the provided pipe and insert output into the GUI."""
            try:
                with pipe:
                    for line in iter(pipe.readline, ''):
                        insert_function(tab_id, line)
            except Exception as e:
                print(f"Error reading output: {e}")

        def run():
            print(f"Starting script: {script_path}")
            try:
                self.processes[tab_id]['process'] = subprocess.Popen(
                    [str(pythonw_path.resolve()), "-u", str(script_path.resolve())],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

                process = self.processes[tab_id]['process']
                stdout_thread = Thread(target=read_output, args=(process.stdout, self.insert_output, tab_id))
                stderr_thread = Thread(target=read_output, args=(process.stderr, self.insert_output, tab_id))

                stdout_thread.start()
                stderr_thread.start()

                process.wait()

                stdout_thread.join()
                stderr_thread.join()

                exit_code = process.returncode
                if tab_id in self.processes:
                    self.insert_output(tab_id, f"\nScript finished with exit code {exit_code}\n")
                    self.processes[tab_id]['process'] = None

            except KeyError:
                print(f"Tab {tab_id} was closed before the script finished.")

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
        """Save the currently open tabs (scripts) to a .script_group file."""
        file_path = filedialog.asksaveasfilename(
            title="Save Script Group",
            defaultextension=".script_group",
            filetypes=[("Script Group Files", "*.script_group")]
        )

        if not file_path:
            return

        script_paths = [process_info['script_path'] for process_info in self.processes.values() if 'script_path' in process_info]
        with open(file_path, 'w') as f:
            f.writelines(f"{path}\n" for path in script_paths)

    def load_script_group(self):
        """Load scripts from a .script_group file and launch them in new tabs."""
        file_path = filedialog.askopenfilename(
            title="Select Script Group",
            filetypes=[("Script Group Files", "*.script_group")]
        )

        if not file_path:
            return

        with open(file_path, 'r') as f:
            script_paths = [line.strip() for line in f.readlines() if line.strip()]

        for script_path in script_paths:
            tab_id = len(self.processes) + 1
            self.run_script_with_tab(Path(script_path), tab_id)

    def edit_script(self, tab_id):
        """Open the selected script in VSCode for editing."""
        if tab_id in self.processes:
            script_path = self.processes[tab_id]['script_path']
            print(f"Opening script {script_path} for editing in VS Code...")
            subprocess.Popen([str(vscode_path.resolve()), script_path])

    def reload_script(self, tab_id):
        """Reload the selected script by re-running it."""
        if tab_id in self.processes:
            # Get the current script path
            script_path = Path(self.processes[tab_id]['script_path'])
            
            # Close the existing tab if it exists
            self.close_tab(tab_id)
            
            # Run the script again in a new tab
            self.run_script_with_tab(script_path, tab_id)

    def close_tab(self, tab_id):
        """Close a specific tab and terminate the script."""
        if tab_id in self.processes:
            process = self.processes[tab_id].get('process')
            if process is not None:
                self.stop_events[tab_id].set()
                process.terminate()

            self.notebook.forget(self.tab_frames[tab_id])

            del self.processes[tab_id]
            del self.stop_events[tab_id]
            del self.tab_frames[tab_id]

    def on_tab_right_click(self, event):
        """Handle right-click event on notebook tabs."""
        try:
            clicked_tab_index = self.notebook.index(f"@{event.x},{event.y}")
        except TclError:
            return

        for tab_id, frame in self.tab_frames.items():
            if self.notebook.index(frame) == clicked_tab_index:
                self.close_tab(tab_id)
                return

    def on_close(self):
        """Handle window close event: terminate all running scripts and close the application."""
        for tab_id, process_info in self.processes.items():
            process = process_info.get('process')
            if process is not None:
                try:
                    process.terminate()
                except Exception as e:
                    print(f"Error terminating process {tab_id}: {e}")
        self.root.destroy()

# Create the main window (root) for the UI with a dark theme
root = ThemedTk(theme="black")  # Applying dark theme using ThemedTk

# Create the app using the root window
app = ScriptLauncherApp(root)

# Start the Tkinter event loop
root.mainloop()
