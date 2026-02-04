# tabs/script_tab.py - ScriptTab for running Python scripts
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, TclError
from typing import TYPE_CHECKING, Callable

from _lib import AnsiParser
from _lib.parse_ansi import AnsiStyle

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from Lib.settings_changer import JsonSaveEditor

from .base import Tab
from config import (
    BUTTON_BG_COLOR, BUTTON_FG_COLOR, BUTTON_ACTIVE_BG_COLOR, BUTTON_ACTIVE_FG_COLOR,
    TEXT_WIDGET_BG_COLOR, TEXT_WIDGET_FG_COLOR, TEXT_WIDGET_INSERT_COLOR, FRAME_BG_COLOR,
    SCRIPT_LOAD_DELAY_MS, data_path, project_root, pythonw_path, vscode_path
)

if TYPE_CHECKING:
    from process_tracker import ProcessTracker


class ScriptTab(Tab):
    """Represents one running script in a tab"""
    def __init__(
        self,
        title: str,
        script_path: Path,
        process_tracker: ProcessTracker,
        open_tab: Callable[[Tab], None] | None = None
    ) -> None:
        super().__init__(title)
        self.script_path: Path = script_path
        self.script_name: str = script_path.name
        self.process_tracker: ProcessTracker = process_tracker
        self.open_tab: Callable[[Tab], None] | None = open_tab

        # Define font settings
        self.font_normal: tuple[str, int] = ("Consolas", 12)
        self.font_bold: tuple[str, int, str] = ("Consolas", 12, "bold")

        self._ansi_parser: AnsiParser = AnsiParser()

        # Text buffer
        self.text_buffer: list[tuple[str, AnsiStyle]] = []
        self.is_flushing: bool = False
        self.button_frame: tk.Frame | None = None

    def build_content(self) -> None:
        """Build the content of the ScriptTab."""

        # Create a frame to hold the text widget and scrollbar
        content_frame: tk.Frame = tk.Frame(self.frame, bg=FRAME_BG_COLOR)
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
        self.text_widget.bind("<F5>", lambda event: self.reload_script())

        # Check metadata for any commands
        # This allows custom buttons to be assigned for each script
        script_metadata = self.load_script_metadata()
        if len(script_metadata) > 0:
            self.process_commands(script_metadata)

        # Start the script execution
        self.run_script()

    def load_script_metadata(self, filename: str = "script_metadata.json") -> dict[str, list[dict[str, str]]]:
        """Load script metadata for loaded script"""
        metadata_path: str = os.path.join(data_path, filename)

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

    def process_commands(self, script_metadata: dict[str, list[dict[str, str]]]) -> None:
        """Process commands from script metadata"""
        # Import here to avoid circular imports
        from .markdown_tab import MarkdownTab

        commands: list[dict[str, str]] = script_metadata.get("commands", [])
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
                button.pack(side="right", padx=4, pady=2)

            elif command_name == "open_help" and self.open_tab:
                md_path = os.path.normpath(os.path.join(project_root, command_arg.lstrip("/\\")))
                button = tk.Button(
                    self.button_frame,
                    text=description,
                    command=lambda path=md_path: self.open_tab(MarkdownTab(
                        title=os.path.basename(path),
                        md_file_path=path,
                        open_tab=self.open_tab
                    )),
                    bg=BUTTON_BG_COLOR,
                    fg=BUTTON_FG_COLOR,
                    activebackground=BUTTON_ACTIVE_BG_COLOR,
                    activeforeground=BUTTON_ACTIVE_FG_COLOR,
                    relief="flat",
                    highlightthickness=0
                )
                button.pack(side="right", padx=4, pady=2)

    def close(self) -> None:
        """Clean up resources associated with the tab."""
        print(f"ScriptTab: close tabid={self.tabid}")
        self.process_tracker.terminate_process(self.tab_id)
        super().close()

    def run_script(self) -> None:
        """Run the script using ProcessTracker."""
        # Build the command
        command: list[str] = [str(pythonw_path.resolve()), "-u", str(self.script_path.resolve())]

        # Start the process with the updated environment
        self.process_tracker.start_process(
            tab_id=self.tab_id,
            command=command,
            stdout_callback=self._insert_stdout,
            stderr_callback=self._insert_stderr,
            script_tab=self,
            script_name=self.script_path.name,
        )

    def _insert_stdout(self, text: str) -> None:
        self._insert_text(text)

    def _insert_stderr(self, text: str) -> None:
        self._insert_text(text)

    def _insert_text(self, text: str) -> None:
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

    def _flush_text_buffer(self) -> None:
        """Flush the buffered text into the Text widget."""
        if not (self.text_widget and self.text_widget.winfo_exists()):
            self.is_flushing = False
            return

        # Process all buffered segments
        segments_to_insert: list[tuple[str, AnsiStyle]] = self.text_buffer
        self.text_buffer = []  # Clear the buffer

        # Insert the segments into the Text widget
        self._safe_insert_segments(segments_to_insert)

        # Check if more data was added to the buffer while flushing
        if self.text_buffer:
            interval = self._calculate_flush_interval()
            self.frame.after(interval, self._flush_text_buffer)  # Reschedule flushing
        else:
            self.is_flushing = False

    def _calculate_flush_interval(self) -> int:
        """Determine the flush interval dynamically based on workload."""
        buffer_size: int = len(self.text_buffer)

        # Dynamic intervals - refresh less often with higher workloads
        if buffer_size > 100:  # High workload
            return 10
        elif buffer_size > 50:  # Medium workload
            return 25
        else:  # Low workload
            return 50

    def _safe_insert_segments(self, segments: list[tuple[str, AnsiStyle]]) -> None:
        """Safely insert text segments with colors and bold styles into the text widget."""
        try:
            for segment, style in segments:
                color: str | None = style.get("color")  # Extract the color
                bold: bool = style.get("bold", False)  # Extract bold

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

    def _safe_insert(self, text: str) -> None:
        """Safely insert text into the text widget"""
        try:
            if self.text_widget and self.text_widget.winfo_exists():
                self.text_widget.insert(tk.END, text)
                self.text_widget.see(tk.END)  # Scroll to the end
        except TclError as e:
            print(f"[WARNING] _safe_insert: TclError encountered while writing to the widget: {e}")
        except Exception as e:
            print(f"[ERROR] _safe_insert: Unexpected exception while writing to the widget: {e}")

    def ensure_tag(self, color: str | None = None, bold: bool = False) -> str:
        """
        Ensure that a text tag for the given color and bold style is defined in the widget.
        """
        # Generate a unique tag name based on color and bold
        tag: str = f"color-{color}-bold-{bold}" if color else f"bold-{bold}"

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

    def edit_script(self) -> None:
        """Open the script in VSCode for editing."""
        if vscode_path is None:
            self.insert_output("[ERROR] VS Code not found. Please install VS Code and add it to your PATH.\n")
            return
        try:
            subprocess.Popen(["cmd", "/c", str(vscode_path.resolve()), str(self.script_path.resolve())])
            self.insert_output(f"Opening script {self.script_path} for editing in VS Code...\n")
        except Exception as e:
            self.insert_output(f"Error opening script for editing: {e}\n")

    def reload_script(self, clear_text: bool = True) -> None:
        """Reload the script by terminating and restarting the process."""
        print(f"[INFO] Reloading script for Tab ID: {self.tab_id}")

        def _reload() -> None:
            self.process_tracker.terminate_process(self.tab_id)

            # Clear the text widget (output page)
            if clear_text is True:
                if self.text_widget and self.text_widget.winfo_exists():
                    self.text_widget.delete('1.0', tk.END)

            self.run_script()

        self.process_tracker.scheduler(SCRIPT_LOAD_DELAY_MS, _reload)  # Schedule the reload process

    def stop_script(self) -> None:
        """Stop the running of the script"""
        self.process_tracker.terminate_process(self.tab_id)

    def handle_keypress(self, event: tk.Event[tk.Misc]) -> None:
        """Handle keypress events."""
        if not self.is_active:
            return

        key: str = event.char or ""  # Get the character, default to empty for non-character keys
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

    def on_tab_activated(self) -> None:
        if self.text_widget and self.text_widget.winfo_exists():
            self.text_widget.focus_force()
        else:
            print("[ERROR] Text widget is not available for focus.")
