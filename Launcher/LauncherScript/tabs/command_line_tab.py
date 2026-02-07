# tabs/command_line_tab.py - Terminal-like command line interface tab
from __future__ import annotations

import os
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Callable, ClassVar, Pattern

import psutil

from .base import Tab
from config import (
    TEXT_WIDGET_BG_COLOR, TEXT_WIDGET_FG_COLOR, TEXT_WIDGET_INSERT_COLOR, FRAME_BG_COLOR,
    scripts_path, project_root, python_dir_str
)


class CommandLineTab(Tab):
    """A tab that provides a terminal-like command-line interface."""

    ANSI_ESCAPE_PATTERN: ClassVar[Pattern[str]] = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    CMD_TITLE_ARTIFACT_PATTERN: ClassVar[Pattern[str]] = re.compile(
        r"(?:\x1b\])?0;[A-Za-z]:\\[^\r\n]*?cmd\.exe(?:\x07)?",
        re.IGNORECASE,
    )

    def __init__(self, title: str, command_callback: Callable[[str, list[str], Path | str], tuple[bool, str | None]]) -> None:
        super().__init__(title)
        self.output_widget: tk.Text | None = None
        self.input_entry: tk.Entry | None = None
        self.process: Any | None = None  # winpty.PtyProcess, but dynamically imported
        self.stop_event: threading.Event = threading.Event()
        self.command_callback: Callable[[str, list[str], Path | str], tuple[bool, str | None]] = command_callback

        # Initialize the cached current working directory
        self.cached_cwd: Path | str = scripts_path

        # Autocomplete state
        self.is_autocompleting: bool = False
        self.cached_input: str = ""  # Tracks input at the start of the autocomplete cycle
        self.original_partial_path: str = ""  # Tracks the prefix for the current autocomplete cycle
        self.autocomplete_matches: list[str] = []
        self.autocomplete_index: int = -1

        # Simple command history
        self.history: list[str] = []
        self.history_index: int = -1

    def build_content(self) -> None:
        """Create the interactive terminal interface."""
        # Output display area
        consolas_font: tuple[str, int] = ("Consolas", 12)

        # Create a frame to hold the text widget and scrollbar
        content_frame: tk.Frame = tk.Frame(self.frame, bg=FRAME_BG_COLOR)
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
        scrollbar: ttk.Scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=self.output_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_widget.configure(yscrollcommand=scrollbar.set)

        # Input area
        input_frame: tk.Frame = tk.Frame(self.frame, bg=FRAME_BG_COLOR)
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

    def start_shell(self) -> None:
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
            scripts_dir: str = str(scripts_path.resolve())

            # Build a custom environment inheriting from os.environ
            custom_env: dict[str, str] = os.environ.copy()
            winpython_bin: str = str((project_root / python_dir_str).resolve())

            # Ensure the WinPython binary and scripts folder are in PATH
            custom_env["PATH"] = f"{winpython_bin};{winpython_bin}\\Scripts;{custom_env.get('PATH', '')}"
            custom_env["PYTHONPATH"] = f"{winpython_bin};{custom_env.get('PYTHONPATH', '')}"
            custom_env["VIRTUAL_ENV"] = winpython_bin

            # Spawn a pseudo-console with the correct environment
            self.process = winpty.PtyProcess.spawn("cmd", cwd=scripts_dir, env=custom_env)
            threading.Thread(target=self._read_output, daemon=True).start()

            self.insert_output(
                f"[INFO] Shell started in {scripts_dir}.\nType commands below (try 'help' for built-ins).\n"
            )
        except Exception as e:
            self.insert_output(f"[ERROR] Failed to start shell: {e}\n")

    def on_user_input(self, event: tk.Event[tk.Misc]) -> None:
        """Reset autocomplete state for non-autocomplete keys."""
        # Ignore Tab (used for autocomplete)
        if event.keysym == "Tab":
            return

        # Reset autocomplete for all other keypresses
        self.is_autocompleting = False

    def send_input(self, event: tk.Event[tk.Misc] | None = None) -> None:
        """Capture and send user input to the shell process."""
        assert self.input_entry is not None
        user_input: str = self.input_entry.get().strip()

        if not user_input:
            return  # Ignore empty input

        # Add the command to history
        self.history.append(user_input)
        self.history_index = len(self.history)  # Reset to "one past the end"

        # Parse the base command and arguments
        command_parts: list[str] = user_input.split()
        base_command: str = command_parts[0]
        args: list[str] = command_parts[1:]

        # Try to handle the command via `command_callback`
        success, message = self.command_callback(base_command, args, self.cached_cwd)
        if success:
            if message:
                self.insert_output(f"[INFO] {message}\n")
        else:
            # If callback provided a shell command override, use it; otherwise use raw input
            self.run_shell_command(message if message else user_input)

        # Clear the input field
        self.input_entry.delete(0, tk.END)

    def run_shell_command(self, command: str) -> None:
        """Send a command to the pseudo-console."""
        if not self.process or not self.process.isalive():
            self.insert_output("[ERROR] No active shell process to send commands to.\n")
            return

        try:
            # Write the command followed by a newline to simulate Enter
            self.process.write(command + "\r\n")
        except Exception as e:
            self.insert_output(f"[ERROR] Failed to send command to shell: {e}\n")

    def autocomplete(self, event: tk.Event[tk.Misc]) -> str | None:
        """Handle tab-completion logic."""
        # Do not consume Ctrl+Tab/Ctrl+Shift+Tab; allow global tab switching.
        if event.state & 0x0004:
            return None

        assert self.input_entry is not None
        # Get the current input and cursor position
        current_input: str = self.input_entry.get()
        cursor_position: int = self.input_entry.index(tk.INSERT)
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
        selected_match: str = self.autocomplete_matches[self.autocomplete_index]
        full_command: str = f"{base_command} {selected_match}" if base_command else selected_match

        # Programmatically update the input field with the selected match
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, full_command)
        self.input_entry.icursor(len(full_command))  # Place the cursor at the end

        return "break"

    def parse_command(self, command: str) -> tuple[str, str]:
        """
        Parse the command to split the base command from the partial path.
        For example:
        - Input: "python te"
        - Output: ("python", "te")
        """
        # Split the command into parts by spaces
        parts: list[str] = command.rsplit(" ", 1)
        if len(parts) == 1:
            # No space in the command, treat the whole thing as the path
            base, path = "", parts[0]
        else:
            base, path = parts[0], parts[1]

        return base, path

    def get_autocomplete_matches(self, prefix: str) -> list[str]:
        """Dynamically fetch files and directories matching the prefix, prioritizing files."""
        try:
            cwd: Path = Path(self.cached_cwd)  # Use the cached working directory
            files_and_dirs = cwd.iterdir()  # List all files and directories

            # Perform case-insensitive matching
            matches: list[str] = [
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

    def handle_up_arrow(self, event: tk.Event[tk.Misc]) -> str:
        """Cycle backward through command history."""
        assert self.input_entry is not None
        if not self.history:
            return "break"  # No history to cycle

        if self.history_index > 0:
            self.history_index -= 1
        else:
            self.history_index = 0  # Ensure index doesn't go below 0

        # Fetch the command and update the input field
        cmd: str = self.history[self.history_index]
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, cmd)
        self.input_entry.icursor(len(cmd))  # Move cursor to the end

        return "break"

    def handle_down_arrow(self, _event: tk.Event[tk.Misc]) -> str:
        """Cycle forward through command history."""
        assert self.input_entry is not None
        if not self.history:
            return "break"  # No history to cycle

        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            cmd: str = self.history[self.history_index]
        else:
            # If at the end of history, clear the input field
            self.history_index = len(self.history)
            cmd = ""

        # Update the input field
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, cmd)
        self.input_entry.icursor(len(cmd))  # Move cursor to the end

        return "break"

    def debug_associated_processes(self) -> None:
        """Find and print all processes associated with the current process."""
        if not self.process or not self.process.pid:
            print("[ERROR] No process is currently running or the process PID is not set.")
            return

        try:
            pid: int = self.process.pid
            print(f"[INFO] Inspecting processes associated with PID: {pid}")

            # Get the parent process
            parent_process: psutil.Process = psutil.Process(pid)
            print(f"[INFO] Parent Process: PID={parent_process.pid}, Name={parent_process.name()}, Status={parent_process.status()}")

            # Get all child processes
            children: list[psutil.Process] = parent_process.children(recursive=True)
            if not children:
                print(f"[INFO] No child processes found for PID={pid}.")
            else:
                print(f"[INFO] Found {len(children)} child processes:")
                for child in children:
                    print(f"  - Child PID={child.pid}, Name={child.name()}, Status={child.status()}")

        except psutil.NoSuchProcess:
            print(f"[ERROR] No process found with PID: {self.process.pid}. It may have exited.")
        except Exception as e:
            print(f"[ERROR] Unexpected error while inspecting processes: {e}")

    def handle_ctrl_c(self, target: str = "child") -> None:
        """
        Handle the Ctrl+C event to send SIGINT to the specified target.
        """
        if not self.process or not self.process.pid:
            print("[ERROR] No process is currently running or the process PID is not set.")
            return

        try:
            parent_pid: int = self.process.pid

            # Get the parent process and its children
            parent: psutil.Process = psutil.Process(parent_pid)
            children: list[psutil.Process] = parent.children(recursive=True)

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
                other_children: list[psutil.Process] = [p for p in children if p.name().lower() != "conhost.exe"]
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

    def _send_ctrl_c_to_process(self, pid: int, target: str = "unknown") -> None:
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

    def _read_output(self) -> None:
        """Read and display output from the pseudo-console process, using regex for ANSI codes and artifacts."""
        try:
            while True:
                if self.stop_event.is_set():
                    break

                # Read up to 1024 bytes from the pseudo-console
                output: str = self.process.read(1024)
                if not output:
                    break

                # Safeguard against widget destruction
                if not self.output_widget or not self.output_widget.winfo_exists():
                    break

                # Remove ANSI escape sequences
                clean_output: str = self.ANSI_ESCAPE_PATTERN.sub('', output)

                # Normalize carriage returns (\r) by removing them
                clean_output = clean_output.replace('\r', '')

                filtered_output: str = self._sanitize_shell_output(clean_output)

                # Insert filtered output
                self.insert_output(filtered_output)

                # Detect paths directly in filtered output
                for match in re.finditer(r"^[A-Za-z]:\\.*>", filtered_output, re.MULTILINE):
                    # Extract the path without the trailing '>'
                    detected_path: str = match.group(0).rstrip(">")
                    self.cached_cwd = detected_path
                    print(f"[INFO] Current directory updated to: {self.cached_cwd}\n")

        except Exception as e:
            self.insert_output(f"[ERROR] Failed to read console output: {e}\n")

    @classmethod
    def _sanitize_shell_output(cls, text: str) -> str:
        """Remove cmd title artifacts that can leak into output."""
        return cls.CMD_TITLE_ARTIFACT_PATTERN.sub("", text)

    def insert_output(self, text: str) -> None:
        """Insert shell output into the output widget."""
        if not self.output_widget or not self.output_widget.winfo_exists():
            return  # Widget has been destroyed, skip

        self.output_widget.config(state="normal")
        self.output_widget.insert(tk.END, text)
        self.output_widget.see(tk.END)
        self.output_widget.config(state="disabled")

    def on_tab_activated(self) -> None:
        if self.input_entry and self.input_entry.winfo_exists():
            self.input_entry.focus_force()
        else:
            print("[ERROR] Input textbox is not available for focus.")

    def close(self) -> None:
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
