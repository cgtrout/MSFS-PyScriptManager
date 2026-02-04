# tabs/base.py - Base Tab class for MSFSPyScriptManager

import tkinter as tk
from tkinter import ttk


class Tab:
    """Manages the content and behavior of an individual tab (its frame, widgets, etc.)."""
    def __init__(self, title):
        self.title = title
        self.is_active = False
        self.text_widget = None
        self.frame = None
        self.tabid = None
        self.tab_id = None

    def initialize_frame(self, notebook):
        """Create the frame for this tab within the given notebook."""
        self.frame = ttk.Frame(notebook)

    def build_content(self):
        """Build the content of the tab. Override in subclasses."""
        pass

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

    def on_tab_activated(self):
        """Called when the tab is activated. Override in subclasses."""
        pass

    def close(self):
        """Clean up resources associated with the tab."""
        if self.frame:
            self.frame.destroy()
        print(f"[INFO] Tab '{self.title}' closed.")
