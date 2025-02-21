import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
from Lib.dark_mode import DarkmodeUtils

class JsonSaveEditor(tk.Tk):
    """A GUI-based JSON editor allowing users to edit values in a fixed JSON structure"""

    def __init__(self, file_path=None):
        """Initialize the JSON editor"""

        if file_path is None:
            file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
            if not file_path:
                messagebox.showerror("Error", "No JSON file selected. Exiting.")
                self.destroy()
                return

        super().__init__()
        self.title("Settings File Editor")
        self.geometry("600x400")

        DarkmodeUtils.apply_dark_mode(self)

        self.file_path = file_path
        self.json_data = self.load_json()

        # Apply dark mode styling
        self.configure(bg="#2e2e2e")
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        # Configure Treeview widget style
        self.style.configure("Treeview", background="#333333", foreground="#ffffff",
                             fieldbackground="#333333", rowheight=25)
        self.style.map("Treeview", background=[("selected", "#555555")],
                       foreground=[("selected", "#ffffff")])

        # Remove Treeview border and adjust layout
        self.style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

        # Configure Treeview Heading style
        self.style.configure("Treeview.Heading", background="#444444", foreground="#ffffff",
                             font=("Arial", 10, "bold"))

        # Configure Button style without border or focus highlight
        self.style.configure("TButton", background="#444444", foreground="#ffffff",
                             font=("Arial", 10), padding=5, borderwidth=0, relief="flat",
                             focuscolor="none")
        self.style.map("TButton", background=[("active", "#555555")],
                       foreground=[("active", "#ffffff")])

        # Create a frame for the treeview
        tree_frame = tk.Frame(self, bg="#2e2e2e")
        tree_frame.pack(expand=True, fill="both", padx=0, pady=0)

        # Create Treeview inside the frame
        self.tree = ttk.Treeview(tree_frame, columns=("value",), show="tree", style="Treeview")
        self.tree.heading("#0", text="Key")
        self.tree.heading("value", text="Value")
        self.tree.column("value", width=200)
        self.tree.pack(expand=True, fill="both")

        # Store references to JSON keys for modifications
        self.item_paths = {}
        self.populate_tree("", self.json_data)

        # Bind event for editing JSON values
        self.tree.bind("<Double-1>", self.on_double_click)

        # Create a Save button
        self.save_btn = ttk.Button(self, text="Save Settings", command=self.save_json, style="TButton")
        self.save_btn.pack(pady=5)

        self.editing_entry = None

    def load_json(self):
        """ Load JSON from the given file path. """
        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def populate_tree(self, parent, data):
        """Recursively populate the tree view with JSON keys and values."""

        if isinstance(data, (dict, list)):
            items = data.items() if isinstance(data, dict) else enumerate(data)
            for key, value in items:
                text = key if isinstance(data, dict) else f"[{key}]"
                item_id = self.tree.insert(parent, "end", text=text, values=("",), open=True)
                self.item_paths[item_id] = (data, key)

                # Recursively add nested structures
                if isinstance(value, (dict, list)):
                    self.populate_tree(item_id, value)
                else:
                    self.tree.item(item_id, values=(value,))

    def on_double_click(self, event):
        """Enable editing of a value cell on double-click."""

        # Identify the region of the click event (should be a cell)
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        # Identify the column of the click event (only allow editing in the "value" column)
        column = self.tree.identify_column(event.x)
        if column != "#1":
            return

        # Identify the row (JSON key) of the click event
        item = self.tree.identify_row(event.y)
        if not item:
            return

        # Prevent editing if the item has children
        children = self.tree.get_children(item)
        if children:
            return

        # Get the bounding box (position and size) of the clicked cell
        bbox = self.tree.bbox(item, column=column)
        if not bbox:
            return
        x, y, width, height = bbox

        current_value = self.tree.item(item, "values")[0]
        print(f"current_value={current_value}")

        # Create the Entry widget as a child of self (the top-level window)
        self.editing_entry = tk.Entry(self, bg="#444444", fg="white",
                                      insertbackground="white", bd=1, relief="flat")

        # Use the 'in_' parameter to position the entry over the treeview cell
        self.editing_entry.place(in_=self.tree, x=x, y=y, width=width, height=height)
        self.editing_entry.insert(0, current_value)

        # Force focus to ensure interactivity
        self.editing_entry.focus_force()

        # Bind events to handle finishing editing
        self.editing_entry.bind("<FocusOut>", lambda e: self.finish_edit(item))
        self.editing_entry.bind("<Return>", lambda e: self.finish_edit(item))

    def finish_edit(self, item):
        """Save the modified value and update the JSON structure."""

        # Ensure there is an active editing entry
        if not self.editing_entry:
            print("is not self.editing_entry")
            return

        # Retrieve the new value entered by the user
        new_value = self.editing_entry.get()

        # Remove the entry widget from the UI
        self.editing_entry.destroy()
        self.editing_entry = None

        # Update the displayed value in the Treeview widget
        self.tree.set(item, "value", new_value)

        # Retrieve the corresponding JSON object and key for the modified value
        parent_obj, key = self.item_paths.get(item, (None, None))
        if parent_obj is None or key is None:
            return  # Exit if the item is not found in the mapping

        # Get the original value type to ensure type consistency when modifying the JSON data
        original_value = parent_obj[key]

        # Attempt type conversion
        try:
            if isinstance(original_value, bool):
                if new_value.lower() in ["true", "false"]:
                    converted = new_value.lower() == "true"
                else:
                    raise ValueError("Invalid boolean value. Use 'true' or 'false'.")

            elif isinstance(original_value, int):
                converted = int(new_value)

            elif isinstance(original_value, float):
                converted = float(new_value)

            else:
                converted = new_value  # Default to string

            # If conversion succeeds, update the JSON structure
            parent_obj[key] = converted

        except ValueError as e:
            # Show warning message and revert to old value
            messagebox.showwarning("Invalid Input", f"Error: {e}\nReverting to old value.")
            self.tree.set(item, "value", str(original_value))  # Restore the old value

    def save_json(self):
        """ Overwrite the original JSON file with the modified data. """
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.json_data, f, indent=4)
            messagebox.showinfo("Saved", "Settings file saved successfully!\n\n"
                                "Restart the script to apply the changes")

            self.destroy()
        except Exception as e: # pylint: disable=broad-exception-caught
            messagebox.showerror("Error", f"Failed to save file: {e}")

if __name__ == "__main__":

    app = JsonSaveEditor()
    app.mainloop()
