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

DEBUG_PRINT = False


def _debug_print(message: str) -> None:
    if DEBUG_PRINT:
        print(message)


class LineEditor:
    """Manages line-editing buffer and echo for stdin input."""

    def __init__(self, text_widget: tk.Text):
        self.text_widget = text_widget
        self._buffer: list[str] = []
        self._cursor: int = 0
        self._mark_name = "input_echo"

    def _log_buffer(self, operation: str) -> None:
        """Log current buffer state for debugging."""
        buffer_str = "".join(self._buffer)
        _debug_print(f"[LineEditor.{operation}] buffer='{buffer_str}' cursor={self._cursor} len={len(self._buffer)}")

    def insert_char(self, char: str) -> None:
        """Insert a printable character at cursor position."""
        _debug_print(f"[LineEditor.insert_char] BEFORE: char='{char}'")
        self._log_buffer("insert_char.before")
        self._buffer.insert(self._cursor, char)
        self._cursor += 1
        self._log_buffer("insert_char.after")
        self._update_echo()

    def backspace(self) -> None:
        """Delete character before cursor."""
        _debug_print(f"[LineEditor.backspace] BEFORE:")
        self._log_buffer("backspace.before")
        if self._cursor > 0:
            self._cursor -= 1
            del self._buffer[self._cursor]
            self._log_buffer("backspace.after")
            self._update_echo()
        else:
            _debug_print(f"[LineEditor.backspace] SKIPPED: cursor already at 0")

    def delete(self) -> None:
        """Delete character at cursor."""
        _debug_print(f"[LineEditor.delete] BEFORE:")
        self._log_buffer("delete.before")
        if self._cursor < len(self._buffer):
            del self._buffer[self._cursor]
            self._log_buffer("delete.after")
            self._update_echo()
        else:
            _debug_print(f"[LineEditor.delete] SKIPPED: cursor at end")

    def move_left(self) -> None:
        if self._cursor > 0:
            self._cursor -= 1
            self._update_echo()

    def move_right(self) -> None:
        if self._cursor < len(self._buffer):
            self._cursor += 1
            self._update_echo()

    def move_home(self) -> None:
        self._cursor = 0
        self._update_echo()

    def move_end(self) -> None:
        self._cursor = len(self._buffer)
        self._update_echo()

    def handle_click(self, event) -> str | None:
        """Handle mouse click to position cursor in the echo buffer."""
        if not self._buffer or self._mark_name not in self.text_widget.mark_names():
            return None  # No buffer active, allow normal selection

        # Get the click position
        click_index = self.text_widget.index(f"@{event.x},{event.y}")
        mark_index = self.text_widget.index(self._mark_name)

        # Calculate offset from mark to click position
        click_pos = float(click_index)
        mark_pos = float(mark_index)

        # If click is before the mark, allow normal selection (selecting output text)
        if click_pos < mark_pos:
            return None

        # Get the line and column of both positions
        click_line, click_col = map(int, click_index.split('.'))
        mark_line, mark_col = map(int, mark_index.split('.'))

        # If on the same line, calculate character offset
        if click_line == mark_line:
            offset = click_col - mark_col
            # Clamp to buffer length
            self._cursor = min(max(0, offset), len(self._buffer))
            self._update_echo()
            return "break"  # We handled cursor positioning in the input buffer

        # Click is after the buffer but not on the same line, allow selection
        return None

    def get_line(self) -> str:
        """Get the current line, finalize echo, and clear buffer."""
        line = "".join(self._buffer)
        self._finalize_echo()
        return line

    def clear(self) -> None:
        """Clear the buffer without finalizing echo."""
        self._buffer.clear()
        self._cursor = 0

    def has_content(self) -> bool:
        """Check if buffer has any content."""
        return bool(self._buffer)

    def _update_echo(self) -> None:
        """Redraw the current line at the end of the text widget."""
        buffer_str = "".join(self._buffer)
        _debug_print(f"[LineEditor._update_echo] ENTRY: buffer='{buffer_str}'")

        if not self.text_widget.winfo_exists():
            _debug_print(f"[LineEditor._update_echo] EXIT: widget doesn't exist")
            return

        # Log ALL content before we start
        all_content_before = self.text_widget.get("1.0", tk.END)
        _debug_print(f"[LineEditor._update_echo] Widget full content BEFORE: {all_content_before!r}")

        # If mark exists, check if it's in the right place (should be on the last line)
        # If not, unset it and we'll recreate it
        if self._mark_name in self.text_widget.mark_names():
            mark_pos = self.text_widget.index(self._mark_name)
            end_pos = self.text_widget.index(tk.END)
            mark_line = int(float(mark_pos))
            end_line = int(float(end_pos))
            _debug_print(f"[LineEditor._update_echo] Mark at {mark_pos} (line {mark_line}), END at {end_pos} (line {end_line})")

            # If mark is not on the last line (or line before due to trailing newline), it's stale
            if mark_line < end_line - 1:
                _debug_print(f"[LineEditor._update_echo] Mark is stale (not on last line), unsetting it")
                self.text_widget.mark_unset(self._mark_name)

        # Now create or use the mark
        if self._mark_name not in self.text_widget.mark_names():
            # No mark - create it at the end of the last non-empty line
            # Get the last line content
            last_line_start = self.text_widget.index("end-1c linestart")
            last_line_content = self.text_widget.get(last_line_start, "end-1c")
            _debug_print(f"[LineEditor._update_echo] Last line content: {last_line_content!r}")

            # Set mark at the very end (before the trailing newline that tk.END includes)
            self.text_widget.mark_set(self._mark_name, "end-1c")
            self.text_widget.mark_gravity(self._mark_name, "left")
            mark_pos = self.text_widget.index(self._mark_name)
            _debug_print(f"[LineEditor._update_echo] Created mark at {mark_pos}")

        mark_pos = self.text_widget.index(self._mark_name)
        _debug_print(f"[LineEditor._update_echo] Using mark at position: {mark_pos}")

        # Get current content between mark and END
        current_echo = self.text_widget.get(self._mark_name, tk.END)
        _debug_print(f"[LineEditor._update_echo] Content from mark to END: {current_echo!r}")

        # Delete old echo
        self.text_widget._orig_delete(self._mark_name, tk.END)
        _debug_print(f"[LineEditor._update_echo] Deleted from mark to END")

        # Check content after delete
        all_content_after_delete = self.text_widget.get("1.0", tk.END)
        _debug_print(f"[LineEditor._update_echo] Widget full content AFTER DELETE: {all_content_after_delete!r}")

        # Insert new buffer
        self.text_widget._orig_insert(tk.END, buffer_str)
        _debug_print(f"[LineEditor._update_echo] Inserted buffer at END: {buffer_str!r}")

        # Position the cursor at the correct location in the buffer
        # The mark is at the start of the echo, cursor should be mark + buffer cursor offset
        cursor_pos = f"{self._mark_name}+{self._cursor}c"
        self.text_widget.mark_set("insert", cursor_pos)
        _debug_print(f"[LineEditor._update_echo] Set cursor to position: {cursor_pos} (buffer cursor={self._cursor})")

        # Check final content
        all_content_final = self.text_widget.get("1.0", tk.END)
        _debug_print(f"[LineEditor._update_echo] Widget full content FINAL: {all_content_final!r}")

        self.text_widget.see("insert")  # Scroll to show the cursor
        _debug_print(f"[LineEditor._update_echo] EXIT")

    def _finalize_echo(self) -> None:
        """Lock in the submitted line: append newline, remove mark, clear buffer."""
        if not self.text_widget.winfo_exists():
            return

        self.text_widget._orig_insert(tk.END, "\n")
        if self._mark_name in self.text_widget.mark_names():
            self.text_widget.mark_unset(self._mark_name)
        self.text_widget.see(tk.END)

        self._buffer.clear()
        self._cursor = 0

    def preserve_echo_for_output(self) -> str:
        """Strip echo if present, return echo text.
        Caller MUST call restore_echo() after inserting output."""
        if not self._buffer or self._mark_name not in self.text_widget.mark_names():
            return ""

        echo_text = "".join(self._buffer)
        self.text_widget._orig_delete(self._mark_name, tk.END)
        return echo_text

    def restore_echo(self, echo_text: str) -> None:
        """Restore echo (if any)."""
        if echo_text:
            self.text_widget.mark_set(self._mark_name, tk.END)
            self.text_widget.mark_gravity(self._mark_name, "left")
            self.text_widget._orig_insert(tk.END, echo_text)


class ScriptTab(Tab):
    """Represents one running script in a tab"""
    def __init__(
        self,
        title: str,
        script_path: Path,
        process_tracker: ProcessTracker,
        script_args: list[str] | None = None,
        open_tab: Callable[[Tab], None] | None = None
    ) -> None:
        super().__init__(title)
        self.script_path: Path = script_path
        self.script_name: str = script_path.name
        self.script_args: list[str] = script_args or []
        self.process_tracker: ProcessTracker = process_tracker
        self.open_tab: Callable[[Tab], None] | None = open_tab

        # Define font settings
        self.font_normal: tuple[str, int] = ("Consolas", 12)
        self.font_bold: tuple[str, int, str] = ("Consolas", 12, "bold")

        self._ansi_parser: AnsiParser = AnsiParser()

        # Line-editing state (created after text_widget in build_content)
        self._line_editor: LineEditor | None = None
        self._processing_key: bool = False  # Re-entrance guard

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
            font=self.font_normal,
        )
        self.text_widget.pack(side="left", expand=True, fill="both")

        # Initialize line editor for stdin input management
        self._line_editor = LineEditor(self.text_widget)

        # Block paste/cut operations (we only allow our controlled input)
        self.text_widget.bind("<<Cut>>", lambda _: "break")
        self.text_widget.bind("<<Paste>>", lambda _: "break")
        self.text_widget.bind("<<Clear>>", lambda _: "break")
        self.text_widget.bind("<<PasteSelection>>", lambda _: "break")

        # Override the Text widget's insert and delete methods to prevent direct modification
        # Store original methods so we can still use them internally
        self.text_widget._orig_insert = self.text_widget.insert
        self.text_widget._orig_delete = self.text_widget.delete

        def readonly_insert(*args, **kwargs):
            """Blocked insert - only our code should insert via _orig_insert"""
            _debug_print(f"[BLOCKED] Attempted insert: args={args}")
            return

        def readonly_delete(*args, **kwargs):
            """Blocked delete - only our code should delete via _orig_delete"""
            _debug_print(f"[BLOCKED] Attempted delete: args={args}")
            return

        self.text_widget.insert = readonly_insert
        self.text_widget.delete = readonly_delete

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

        # Intercept all keys on the text widget so default Text insertion is suppressed;
        # line-editing and stdin forwarding are handled by _handle_text_key / _process_key.
        self.text_widget.bind("<Key>", self._handle_text_key)

        # Handle mouse clicks to position cursor in the input buffer
        self.text_widget.bind("<Button-1>", lambda e: self._line_editor.handle_click(e))

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
        # Build the command with script arguments
        command: list[str] = [
            str(pythonw_path.resolve()),
            "-u",
            str(self.script_path.resolve())
        ] + self.script_args

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
            # If the user is mid-line, strip the echo, insert output, then restore it
            # so that script output always appears *before* the partially-typed line.
            echo_text = self._line_editor.preserve_echo_for_output()

            for segment, style in segments:
                color: str | None = style.get("color")  # Extract the color
                bold: bool = style.get("bold", False)  # Extract bold

                if color or bold:
                    # Ensure the tag exists for this combination of color and bold
                    tag = self.ensure_tag(color=color, bold=bold)
                    self.text_widget._orig_insert(tk.END, segment, tag)
                else:
                    # Insert plain text with no formatting
                    self.text_widget._orig_insert(tk.END, segment)

            self._line_editor.restore_echo(echo_text)

            self.text_widget.see(tk.END)  # Scroll to the end
        except TclError as e:
            print(f"[WARNING] _safe_insert_segments: TclError encountered: {e}")
        except Exception as e:
            print(f"[ERROR] _safe_insert_segments: Unexpected error: {e}")

    def _safe_insert(self, text: str) -> None:
        """Safely insert text into the text widget"""
        try:
            if self.text_widget and self.text_widget.winfo_exists():
                echo_text = self._line_editor.preserve_echo_for_output()

                self.text_widget._orig_insert(tk.END, text)

                self._line_editor.restore_echo(echo_text)

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

        # User-initiated reloads (F5/button) pass clear_text=True — reset crash counter
        if clear_text:
            self.process_tracker.reset_restart_state(self.tab_id)

        def _reload() -> None:
            self.process_tracker.terminate_process(self.tab_id)
            if self._line_editor:
                self._line_editor.clear()

            # Clear the text widget (output page)
            if clear_text is True:
                if self.text_widget and self.text_widget.winfo_exists():
                    self.text_widget._orig_delete('1.0', tk.END)

            self.run_script()

        self.process_tracker.scheduler(SCRIPT_LOAD_DELAY_MS, _reload)  # Schedule the reload process

    def stop_script(self) -> None:
        """Stop the running of the script"""
        self.process_tracker.terminate_process(self.tab_id)
        if self._line_editor:
            self._line_editor.clear()

    # ------------------------------------------------------------------
    # Key handling  —  line-editing buffer
    # ------------------------------------------------------------------
    # Raw keystrokes are never written to the pipe individually.  Instead
    # they are accumulated in _input_buffer.  Backspace / Delete / arrows
    # edit the buffer locally; only pressing Enter flushes the finished
    # line (+ "\n") to stdin_queue.  The current buffer contents are
    # echoed at the end of the text widget using a named mark so that
    # script output arriving while the user is mid-line can be inserted
    # *before* the echo without clobbering it.
    # ------------------------------------------------------------------

    def _handle_text_key(self, event: tk.Event[tk.Misc]) -> str | None:
        """Widget-level <Key> binding.  Returns 'break' to suppress the
        default Text-widget character-insertion behaviour."""
        keysym: str = event.keysym
        char: str = event.char or ""

        _debug_print(f"[_handle_text_key] ENTRY: keysym={keysym!r} char={char!r} widget={event.widget}")

        # Let Ctrl/Alt combos propagate (Ctrl+C copy, etc.)
        # but block Ctrl+V — we don't want pasted text silently added
        # to the widget outside of the buffer.
        if event.state & 0x04:  # Ctrl held
            result = "break" if keysym in ("v", "V") else None
            _debug_print(f"[_handle_text_key] EXIT: Ctrl combo, returning {result!r}")
            return result

        # Modifier-only presses: ignore
        if keysym in ("Control_L", "Control_R", "Alt_L", "Alt_R",
                      "Shift_L", "Shift_R", "Super_L", "Super_R"):
            _debug_print(f"[_handle_text_key] EXIT: modifier-only key")
            return None

        # F5  →  reload (replaces the old <F5> widget binding)
        if keysym == "F5":
            _debug_print(f"[_handle_text_key] F5 detected, reloading script")
            self.reload_script()
            return "break"

        _debug_print(f"[_handle_text_key] Calling _process_key")
        self._process_key(event)
        _debug_print(f"[_handle_text_key] EXIT: returning 'break'")
        return "break"

    def handle_keypress(self, event: tk.Event[tk.Misc]) -> None:
        """Global-binding fallback called by app.on_key_press when focus
        is *not* on the text widget (e.g. a button in the tab)."""
        keysym: str = event.keysym
        char: str = event.char or ""

        _debug_print(f"[handle_keypress] ENTRY: keysym={keysym!r} char={char!r} widget={event.widget} is_active={self.is_active}")

        if not self.is_active:
            _debug_print(f"[handle_keypress] EXIT: tab not active")
            return
        # Root's <Key> binding fires for all key events on Windows. If the event
        # originated from text_widget, its binding already handled it → skip.
        if self.text_widget and event.widget is self.text_widget:
            _debug_print(f"[handle_keypress] EXIT: event from text_widget, skipping")
            return
        if event.keysym == "F5":
            _debug_print(f"[handle_keypress] F5 detected, reloading script")
            self.reload_script()
            return

        _debug_print(f"[handle_keypress] Calling _process_key")
        self._process_key(event)
        _debug_print(f"[handle_keypress] EXIT")

    def _process_key(self, event: tk.Event[tk.Misc]) -> None:
        """Core line-editing logic — shared by widget and global paths."""
        keysym: str = event.keysym
        char: str = event.char or ""

        _debug_print(f"[_process_key] ENTRY: keysym={keysym!r} char={char!r} _processing_key={self._processing_key}")

        if self._processing_key:
            _debug_print(f"[_process_key] EXIT: re-entrance guard blocked")
            return  # Already processing a key, prevent re-entrance

        if not self._line_editor:
            _debug_print(f"[_process_key] EXIT: no line editor")
            return

        process_info = self.process_tracker.processes.get(self.tab_id)
        if not process_info:
            _debug_print(f"[_process_key] EXIT: no process info")
            return

        self._processing_key = True
        _debug_print(f"[_process_key] SET _processing_key=True")
        try:
            if keysym == "BackSpace":
                _debug_print(f"[_process_key] Processing BackSpace")
                self._line_editor.backspace()

            elif keysym == "Delete":
                _debug_print(f"[_process_key] Processing Delete")
                self._line_editor.delete()

            elif keysym == "Left":
                _debug_print(f"[_process_key] Processing Left")
                self._line_editor.move_left()

            elif keysym == "Right":
                _debug_print(f"[_process_key] Processing Right")
                self._line_editor.move_right()

            elif keysym == "Home":
                _debug_print(f"[_process_key] Processing Home")
                self._line_editor.move_home()

            elif keysym == "End":
                _debug_print(f"[_process_key] Processing End")
                self._line_editor.move_end()

            elif keysym == "Return":
                _debug_print(f"[_process_key] Processing Return")
                line = self._line_editor.get_line()
                _debug_print(f"[_process_key] Sending line to stdin: {line!r}")
                try:
                    process_info["stdin_queue"].put_nowait(line + "\n")
                except queue.Full:
                    self.insert_output("[WARNING] Input queue is full. Input dropped.\n")

            elif char and char.isprintable():
                _debug_print(f"[_process_key] Processing printable char: {char!r}")
                self._line_editor.insert_char(char)
            else:
                _debug_print(f"[_process_key] No action taken for this key")
        finally:
            self._processing_key = False
            _debug_print(f"[_process_key] EXIT: SET _processing_key=False")

    def on_tab_activated(self) -> None:
        if self.text_widget and self.text_widget.winfo_exists():
            self.text_widget.focus_force()
        else:
            print("[ERROR] Text widget is not available for focus.")
