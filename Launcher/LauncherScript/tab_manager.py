# tab_manager.py - TabManager for managing notebook tabs

import traceback
import tkinter as tk
from tkinter import ttk, TclError

from config import DARK_BG_COLOR, BUTTON_FG_COLOR, SCRIPT_LOAD_DELAY_MS
from tabs import ScriptTab


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
        except TclError:
            self.drag_start_tab = None

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
            return

        # Get all tabs as a list of frames
        tabs_list = self.notebook.tabs()
        tab1_frame = tabs_list[index1]
        tab2_frame = tabs_list[index2]

        # Swap the positions in the notebook widget
        self.notebook.insert(index2, tab1_frame)
        self.notebook.insert(index1, tab2_frame)

    def generate_tab_id(self):
        """Generate a unique tab ID and log the caller and its caller."""
        self.next_tab_id += 1
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
        import logging
        logger = logging.getLogger(__name__)

        def _close_tab():
            logger.debug("close_tab inner")
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
        script_tabs = [tab for tab in self.tabs.values() if isinstance(tab, ScriptTab)]

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
            self.scheduler(delay, reload_script_with_delay, i)

    def on_tab_right_click(self, event):
        def _close_tab_on_click():
            try:
                clicked_tab_index = self.notebook.index(f"@{event.x},{event.y}")

                # Get the actual frame name from the Notebook's tab list
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
