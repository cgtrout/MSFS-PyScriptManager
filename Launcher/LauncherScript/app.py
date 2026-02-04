# app.py - Main ScriptLauncherApp class
from __future__ import annotations

import logging
import threading
import time
import webbrowser
from multiprocessing import Event
from multiprocessing.synchronize import Event as MultiprocessingEvent
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Callable

from config import (
    DARK_BG_COLOR, BUTTON_BG_COLOR, BUTTON_FG_COLOR,
    BUTTON_ACTIVE_BG_COLOR, BUTTON_ACTIVE_FG_COLOR,
    SCRIPT_LOAD_DELAY_MS, scripts_path, read_update_config
)
from tab_manager import TabManager
from process_tracker import ProcessTracker
from tabs import ScriptTab, PerfTab, CommandLineTab
from update_checker import (
    read_app_version, _parse_version, _format_version_numbers,
    is_newer_version, load_update_cache, save_update_cache, fetch_latest_release
)
from _lib import is_shift_held

logger: logging.Logger = logging.getLogger(__name__)


class ScriptLauncherApp:
    """Represents the main application for launching and managing scripts."""
    def __init__(self, root: tk.Tk, shutdown_event: MultiprocessingEvent | None = None) -> None:
        # Root Window Setup
        self.root: tk.Tk = root
        self.configure_root()

        # Update check configuration
        update_config: tuple[str, str, bool, int] = read_update_config()
        self.update_owner: str = update_config[0]
        self.update_repo: str = update_config[1]
        self.check_on_startup: bool = update_config[2]
        self.check_interval_hours: int = update_config[3]

        # Toolbar Setup
        self.toolbar: tk.Frame | None = None
        self.create_toolbar()

        self.tab_manager: TabManager = TabManager(root, self.root.after)

        # Bind Events
        self.bind_events()

        # Event for shutdown (use provided event or create a new one)
        self.shutdown_event: MultiprocessingEvent = shutdown_event if shutdown_event is not None else Event()

        self.process_tracker: ProcessTracker = ProcessTracker(scheduler=self.root.after,
                                              shutdown_event=self.shutdown_event)

        # Bind key press globally - for script keyboard input support
        self.root.bind("<Key>", self.on_key_press)

        # Bind Control+` for toggling the console window
        self.root.bind_all("<Control-`>", self.handle_control_tilde)

        self.root.bind_all("<Control-w>", lambda event: self.tab_manager.close_active_tab())

    def start(self) -> None:
        """Start the app"""
        # Autoplay Scripts
        self.autoplay_script_group()

        # Optional update check on startup
        if self.check_on_startup:
            self.schedule_update_check()

    def schedule_update_check(self, force: bool = False) -> None:
        """Schedule a background update check."""
        if not self.update_owner or not self.update_repo:
            print("[INFO] Update check skipped: RepoOwner/RepoName not configured.")
            return

        thread: threading.Thread = threading.Thread(
            target=self._update_check_worker,
            args=(force,),
            daemon=True,
            name="UpdateCheckThread"
        )
        thread.start()

    def _update_check_worker(self, force: bool) -> None:
        """Worker thread for update checks."""
        try:
            print("[INFO] Checking for updates...")
            cache: dict[str, str | float] = load_update_cache()
            cache["last_check"] = time.time()
            save_update_cache(cache)

            current_version: str = read_app_version()
            latest: dict[str, str] = fetch_latest_release(self.update_owner, self.update_repo)
            latest_tag: str = (latest.get("tag_name") or "").strip()
            latest_url: str = latest.get("html_url", "")

            if latest_tag and is_newer_version(latest_tag, current_version):
                display_current = _format_version_numbers(_parse_version(current_version)) or current_version
                display_latest = _format_version_numbers(_parse_version(latest_tag)) or latest_tag
                print("!============================== UPDATE AVAILABLE ==============================!")
                print(f"[INFO] Latest: {display_latest} | Installed: {display_current}")
                print("!==============================================================================!")
                last_prompted = cache.get("last_prompted_version", "").strip()
                if force or last_prompted != latest_tag:
                    cache["last_prompted_version"] = latest_tag
                    save_update_cache(cache)
                    self.root.after(0, lambda: self._show_update_prompt(display_current, display_latest, latest_url))
            else:
                display_current = _format_version_numbers(_parse_version(current_version)) or current_version
                print(f"[INFO] Up to date: {display_current}")
        except Exception as e:
            print(f"[WARNING] Update check failed: {e}")

    def _show_update_prompt(self, current_version: str, latest_version: str, latest_url: str) -> None:
        """Show update prompt and optionally open browser."""
        message: str = (
            "An update is available.\n\n"
            f"Installed: {current_version}\n"
            f"Latest: {latest_version}\n\n"
            "Open the download page?"
        )
        if messagebox.askyesno("Update Available", message):
            if latest_url:
                webbrowser.open(latest_url)

    def handle_control_tilde(self, event: tk.Event[tk.Misc] | None = None) -> None:
        """Bring up the CommandLineTab: Select if exists, create if not."""
        # Check if a CommandLineTab exists
        for tab_id, tab in self.tab_manager.tabs.items():
            if isinstance(tab, CommandLineTab):
                # Select the existing CommandLineTab
                self.tab_manager.notebook.select(tab.frame)

        # No CommandLineTab exists, create a new one
        self.add_command_line_tab()

    def configure_root(self) -> None:
        """Configure the main root window."""
        self.root.title("MSFS-PyScriptManager")
        self.root.geometry("1000x600")
        self.root.configure(bg=DARK_BG_COLOR)
        try:
            photo = tk.PhotoImage(file="Data/letter-m-svgrepo-com.png")
            self.root.wm_iconphoto(False, photo)
        except tk.TclError as e:
            print(f"Error loading icon: {e}")

    def create_toolbar(self) -> None:
        """Create the top toolbar with action buttons."""
        self.toolbar = tk.Frame(self.root, bg=DARK_BG_COLOR)
        self.toolbar.pack(side="top", fill="x", padx=5, pady=5)

        # Add buttons to the toolbar with their placement side
        buttons: list[tuple[str, Callable[[], None], str]] = [
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

    def select_and_run_script(self) -> None:
        """Opens file dialog for script selection and then runs it"""
        file_path: str = filedialog.askopenfilename( title="Select Python Script",
                                                filetypes=[("Python Files", "*.py")],
                                                initialdir=str(scripts_path) )
        if not file_path:
            print("[INFO] No file selected. Operation cancelled.")
            return
        self.load_script(Path(file_path))

    def load_script(self, script_path: Path) -> None:
        """Load and run a script in a new ScriptTab."""
        script_tab: ScriptTab = ScriptTab(
            title=script_path.name,
            script_path=script_path,
            process_tracker=self.process_tracker,
            open_tab=self.tab_manager.add_tab
        )
        self.tab_manager.add_tab(script_tab)

    def reload_all_scripts(self) -> None:
        shift_held: bool = is_shift_held()
        if not shift_held:
            if not messagebox.askyesno("Confirm Reload",
                                       "Are you sure you want to reload ALL scripts?\n\n"
                                       "Note you can hold shift to bypass this check"):
                return  # User canceled, do not proceed

        self.tab_manager.reload_all_scripts()

    def bind_events(self) -> None:
        # Override close window behavior
        self.root.protocol("WM_DELETE_WINDOW", self.on_shutdown)

    def open_performance_metrics_tab(self) -> None:
        """Open a new performance metrics tab."""
        perf_tab: PerfTab = PerfTab(
            title="Performance Metrics",
            process_tracker=self.process_tracker
        )
        self.tab_manager.add_tab(perf_tab)

    def add_command_line_tab(self) -> None:
        """Create and add a CommandLineTab."""
        command_line_tab: CommandLineTab = CommandLineTab(
            title="Command Line",
            command_callback=self.handle_command  # Pass the generalized callback
        )
        self.tab_manager.add_tab(command_line_tab)

    def handle_command(self, command: str, args: list[str], current_dir: Path | str) -> tuple[bool, str | None]:
        """Generalized command handler with directory context."""
        if command in ["python", "py"]:
            return self.handle_python_command(args, current_dir)
        elif command in ["switch", "s"]:
            return self.switch_tab_by_name(args)
        elif command == "reload":
            return self.handle_reload_command()
        else:
            return False, f"Unknown command: {command}"

    def handle_python_command(self, args: list[str], current_dir: Path | str) -> tuple[bool, str | None]:
        """Handle intercepted Python commands with directory context."""
        if not args:
            return False, "No script specified for 'python'."

        script_name: str = args[0]
        extra_args: list[str] = args[1:]  # Additional arguments for the script

        # Resolve the script path relative to the current directory
        script_path: Path = Path(current_dir) / script_name
        if not script_path.exists():
            return False, f"Script '{script_path}' not found."

        # Launch the script in a new ScriptTab
        script_tab: ScriptTab = ScriptTab(
            title=script_path.name,
            script_path=script_path,
            process_tracker=self.process_tracker,
            open_tab=self.tab_manager.add_tab
        )
        self.tab_manager.add_tab(script_tab)

        return True, None  # Success

    def switch_tab_by_name(self, args: list[str]) -> tuple[bool, str | None]:
        """Switch to the tab with the specified script name."""
        if not args:
            return False, "No script name provided. Usage: switch <script_name>"

        script_name: str = args[0]
        for tab_id, tab in self.tab_manager.tabs.items():
            if isinstance(tab, ScriptTab) and tab.script_path.name.lower() == script_name.lower():
                self.tab_manager.notebook.select(tab.frame)
                return True, None  # Success

        return False, f"No tab found for script: {script_name}"

    def handle_reload_command(self) -> tuple[bool, None]:
        """Switch to the tab with the specified script name."""
        self.tab_manager.reload_all_scripts()
        return True, None  # Success

    def autoplay_script_group(self) -> None:
        """
        Automatically load a script group file named '_autoplay.script_group' located in the
        'Scripts' directory.
        """
        # Set path to '_autoplay.script_group' within the Scripts directory
        autoplay_path: Path = scripts_path / "_autoplay.script_group"

        # Check if the file exists and load it if it does
        if autoplay_path.exists():
            print(f"[INFO] Autoplay: Loading script group from {autoplay_path}")
            self.load_script_group_from_path(autoplay_path)
        else:
            print("[INFO] Autoplay: No '_autoplay.script_group' file found at startup. "
                  "Creating an empty one.")
            try:
                autoplay_path.write_text("", encoding="utf-8")
            except Exception as e:
                print(f"[WARNING] Autoplay: Failed to create empty group file: {e}")

    def save_script_group(self) -> None:
        """Save the currently open tabs (scripts) to a .script_group file with relative paths."""
        import os
        file_path: str = filedialog.asksaveasfilename(
            title="Save Script Group",
            defaultextension=".script_group",
            filetypes=[("Script Group Files", "*.script_group")]
        )

        if not file_path:
            return

        group_dir: Path = Path(file_path).parent

        # Collect script paths from all ScriptTabs
        script_paths: list[str] = []
        for tab_frame_id in self.tab_manager.notebook.tabs():
            for _, tab in self.tab_manager.tabs.items():
                if tab.frame and str(tab.frame) == tab_frame_id:
                    if isinstance(tab, ScriptTab):
                        relative_path: str = os.path.relpath(tab.script_path, group_dir)
                        script_paths.append(relative_path)
                    break

        # Write the relative paths to the .script_group file
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(f"{path}\n" for path in script_paths)

    def load_script_from_path(self, script_path_str: str | Path) -> None:
        """Load and run a script from a specified file path."""
        script_path: Path = Path(script_path_str)

        if not script_path.exists():
            print(f"[ERROR] Script '{script_path}' not found.")
            return

        # Add the script as a new tab
        script_tab: ScriptTab = ScriptTab(
            title=script_path.name,
            script_path=script_path,
            process_tracker=self.process_tracker,
            open_tab=self.tab_manager.add_tab
        )
        self.tab_manager.add_tab(script_tab)

    def load_script_group(self) -> None:
        """Prompt the user to select a .script_group file and load scripts from it."""
        file_path: str = filedialog.askopenfilename(
            title="Select Script Group",
            filetypes=[("Script Group Files", "*.script_group")],
            initialdir=str(scripts_path)
        )
        if file_path:
            self.load_script_group_from_path(Path(file_path))

    def load_script_group_from_path(self, file_path: Path) -> None:
        """Load scripts from the specified .script_group file and launch them in new tabs."""
        group_dir: Path = file_path.parent

        if not file_path.exists():
            print(f"[ERROR] Script group file '{file_path}' not found.")
            return

        with open(file_path, 'r', encoding="utf-8") as f:
            script_paths: list[Path] = [group_dir / Path(line.strip()) for line in f.readlines() if line.strip()]

        # Use a set to avoid loading duplicate scripts
        loaded_scripts: set[str] = set()
        script_paths = [script_path.resolve() for script_path in script_paths if script_path]

        def load_script_with_delay(index: int) -> None:
            """Load a script with a slight delay."""
            script_path: Path = script_paths[index]
            if str(script_path) not in loaded_scripts:
                loaded_scripts.add(str(script_path))
                print(f"[INFO] Loading script '{script_path.name}' (Index: {index}).")
                self.load_script_from_path(script_path)

        # Schedule each script to load with an increasing delay
        for i, script_path in enumerate(script_paths):
            delay = i * SCRIPT_LOAD_DELAY_MS
            self.root.after(delay, load_script_with_delay, i)

    def on_shutdown(self) -> None:
        logger.info("Shutdown signal received. Triggering shutdown_event.")
        logger.debug(f"[DEBUG] on_shutdown shutdown_event ID: {id(self.shutdown_event)}")

        # Set shutdown_event which will trigger launcher shutdown
        self.shutdown_event.set()

    def on_close(self, callback: Callable[[], None] | None = None) -> None:
        """Handle application shutdown."""
        print("[INFO] Shutting down application.")
        logger.info("Shutting down application")
        self.tab_manager.close_all_tabs()

        def finalize_shutdown() -> None:
            print("[INFO] Application closed successfully.")
            logger.info("finalize_shutdown()")
            if callback:
                callback()  # Execute the callback after shutdown is fully complete.

        logger.debug("Schedule: finalize shutdown")
        self.root.after(0, lambda: (self.root.destroy(), finalize_shutdown()))

    def on_key_press(self, event: tk.Event[tk.Misc]) -> None:
        """Route keypress events to the active tab if it supports keypress handling."""
        active_tab_id: int = self.tab_manager.active_tab_id
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
