from __future__ import annotations

import json
import logging
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

try:
    import tkfilebrowser
except ImportError as e:
    logging.getLogger(__name__).warning("Optional dependency 'tkfilebrowser' is unavailable: %s", e)
    tkfilebrowser = None

try:
    from Lib.dark_mode import DarkmodeUtils
except ImportError as e:
    logging.getLogger(__name__).warning("Optional dependency 'Lib.dark_mode' is unavailable: %s", e)
    DarkmodeUtils = None

logger: logging.Logger = logging.getLogger(__name__)


class ScriptPickerDialog:
    """Custom script picker wrapper with theming, shortcuts, and metadata description column."""

    def __init__(self, root: tk.Tk, scripts_dir: Path, project_root: Path, data_dir: Path) -> None:
        self.root = root
        self.scripts_dir = scripts_dir
        self.project_root = project_root
        self.data_dir = data_dir

    def pick_script(self) -> Path | None:
        """Open script picker and return selected script path or None."""
        dialog_kwargs: dict[str, object] = {
            "parent": self.root,
            "title": "Select Python Script to run",
            "filetypes": [("Python Files", "*.py")],
            "initialdir": str(self.scripts_dir),
        }

        file_path: str = ""
        if tkfilebrowser is not None:
            dialog_width: int = 1200
            dialog_height: int = 720
            dialog = tkfilebrowser.FileBrowser(
                mode="openfile",
                multiple_selection=False,
                **dialog_kwargs,
            )
            self._position_dialog_over_main_window(dialog, dialog_width, dialog_height)
            self._apply_filebrowser_dark_theme(dialog)
            self._customize_filebrowser_shortcuts(dialog)
            self._hide_cache_directories(dialog)
            self._add_filebrowser_description_column(dialog)
            if DarkmodeUtils is not None:
                DarkmodeUtils.apply_dark_mode(dialog)
            dialog.wait_window(dialog)
            file_path = dialog.get_result()
        else:
            file_path = filedialog.askopenfilename(**dialog_kwargs)

        if not file_path:
            return None
        return Path(file_path)

    def _position_dialog_over_main_window(self, dialog: tk.Toplevel, width: int, height: int) -> None:
        """Place a dialog centered over the main window."""
        self.root.update_idletasks()
        root_x: int = self.root.winfo_rootx()
        root_y: int = self.root.winfo_rooty()
        root_w: int = max(self.root.winfo_width(), 1)
        root_h: int = max(self.root.winfo_height(), 1)
        x: int = root_x + max((root_w - width) // 2, 0)
        y: int = root_y + max((root_h - height) // 2, 0)
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def _apply_filebrowser_dark_theme(self, dialog: tk.Toplevel) -> None:
        """Apply a darker theme override to tkfilebrowser widgets."""
        bg_root = "#1F1F1F"
        bg_panel = "#202225"
        bg_field = "#191A1C"
        bg_alt = "#25282C"
        fg_text = "#E6E6E6"
        fg_muted = "#CFCFCF"
        sel_bg = "#2B4E6E"
        sel_fg = "#FFFFFF"
        border = "#34363A"

        dialog.configure(background=bg_root)

        style = ttk.Style(dialog)
        style.configure(".", background=bg_root, foreground=fg_text)
        style.configure("TFrame", background=bg_root)
        style.configure("TLabel", background=bg_root, foreground=fg_text)
        style.configure("TButton", background=bg_panel, foreground=fg_text, bordercolor=border)
        style.map(
            "TButton",
            background=[("active", bg_alt), ("pressed", bg_alt)],
            foreground=[("disabled", fg_muted)],
        )
        style.configure("TEntry", fieldbackground=bg_field, foreground=fg_text)
        style.map("TEntry", fieldbackground=[("readonly", bg_field)])
        style.configure(
            "TCombobox",
            fieldbackground=bg_field,
            background=bg_panel,
            foreground=fg_text,
            arrowcolor=fg_text,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", bg_field)],
            foreground=[("readonly", fg_text)],
            selectbackground=[("readonly", sel_bg)],
            selectforeground=[("readonly", sel_fg)],
        )

        style.configure(
            "right.tkfilebrowser.Treeview",
            background=bg_field,
            fieldbackground=bg_field,
            foreground=fg_text,
            bordercolor=border,
        )
        style.configure(
            "left.tkfilebrowser.Treeview",
            background=bg_panel,
            fieldbackground=bg_panel,
            foreground=fg_text,
            bordercolor=border,
        )
        style.map(
            "right.tkfilebrowser.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", sel_fg)],
        )
        style.map(
            "left.tkfilebrowser.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", sel_fg)],
        )
        style.configure(
            "right.tkfilebrowser.Treeview.Heading",
            background=bg_panel,
            foreground=fg_text,
        )
        style.configure(
            "left.tkfilebrowser.Treeview.Heading",
            background=bg_panel,
            foreground=fg_text,
        )
        style.configure(
            "types.tkfilebrowser.TCombobox",
            fieldbackground=bg_field,
            background=bg_panel,
            foreground=fg_text,
            arrowcolor=fg_text,
        )
        style.configure("listbox.tkfilebrowser.TFrame", background=bg_field)

        right_tree = getattr(dialog, "right_tree", None)
        if right_tree is not None:
            right_tree.tag_configure("0", background=bg_field, foreground=fg_text)
            right_tree.tag_configure("1", background=bg_alt, foreground=fg_text)

        listbox = getattr(dialog, "listbox", None)
        if listbox is not None:
            listbox.configure(
                background=bg_field,
                foreground=fg_text,
                selectbackground=sel_bg,
                selectforeground=sel_fg,
                highlightthickness=0,
            )

    def _customize_filebrowser_shortcuts(self, dialog: tk.Toplevel) -> None:
        """Replace default filebrowser shortcuts with project-specific paths."""
        left_tree: tk.Widget | None = getattr(dialog, "left_tree", None)
        if left_tree is None:
            return

        shortcuts: list[tuple[str, Path]] = [
            ("Scripts", self.scripts_dir),
            ("Tests", self.project_root / "Tests"),
        ]
        existing_children: tuple[str, ...] = left_tree.get_children("")
        if existing_children:
            left_tree.delete(*existing_children)

        folder_icon = getattr(dialog, "im_folder", "")
        for label, path in shortcuts:
            if not path.exists():
                continue
            path_str: str = str(path.resolve())
            left_tree.insert("", "end", iid=path_str, text=label, image=folder_icon)

    def _hide_cache_directories(self, dialog: tk.Toplevel) -> None:
        """Hide __pycache__ directories from the filebrowser listing."""
        display_folder = getattr(dialog, "display_folder", None)
        right_tree = getattr(dialog, "right_tree", None)
        if display_folder is None or right_tree is None:
            return

        def _remove_cache_entries() -> None:
            for item_id in right_tree.get_children(""):
                if Path(item_id).name == "__pycache__":
                    right_tree.delete(item_id)

        def _wrapped_display_folder(*args, **kwargs):
            result = display_folder(*args, **kwargs)
            _remove_cache_entries()
            return result

        setattr(dialog, "display_folder", _wrapped_display_folder)
        _remove_cache_entries()

    def _load_script_descriptions(self, filename: str = "script_metadata.json") -> dict[str, str]:
        """Load per-script descriptions from metadata file, keyed by lowercase filename."""
        metadata_path: Path = self.data_dir / filename
        if not metadata_path.exists():
            return {}

        try:
            metadata_raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to load script metadata descriptions from %s", metadata_path)
            return {}

        descriptions: dict[str, str] = {}
        if not isinstance(metadata_raw, dict):
            return descriptions

        for script_name, script_meta in metadata_raw.items():
            if not isinstance(script_name, str) or not isinstance(script_meta, dict):
                continue
            description = script_meta.get("description")
            if isinstance(description, str) and description.strip():
                descriptions[script_name.lower()] = description.strip()
        return descriptions

    def _add_filebrowser_description_column(self, dialog: tk.Toplevel) -> None:
        """Add and populate a Description column in the file list."""
        right_tree = getattr(dialog, "right_tree", None)
        if right_tree is None:
            return

        descriptions: dict[str, str] = self._load_script_descriptions()

        columns = tuple(right_tree.cget("columns"))
        if "description" not in columns:
            columns = columns + ("description",)
            right_tree.configure(columns=columns)
        right_tree.heading("date", text="Modified", anchor="w")
        sort_by_date = getattr(dialog, "_sort_by_date", None)
        if callable(sort_by_date):
            right_tree.heading("date", command=lambda: sort_by_date(False))
        right_tree.heading("description", text="Description", anchor="w")
        right_tree.column("description", width=520, minwidth=220, stretch=True)

        # Keep filename as the tree column (#0), then show Description before Modified.
        right_tree.configure(displaycolumns=("description", "date"))

        def _apply_descriptions_to_rows() -> None:
            for item_id in right_tree.get_children(""):
                filename = Path(item_id).name.lower()
                description = descriptions.get(filename, "")
                values = tuple(right_tree.item(item_id, "values"))
                if len(values) < 3:
                    values = values + ("",) * (3 - len(values))
                if len(values) == 3:
                    values = values + (description,)
                else:
                    values = values[:3] + (description,)
                right_tree.item(item_id, values=values)

        display_folder = getattr(dialog, "display_folder", None)
        if display_folder is None:
            _apply_descriptions_to_rows()
            return

        def _wrapped_display_folder(*args, **kwargs):
            result = display_folder(*args, **kwargs)
            _apply_descriptions_to_rows()
            return result

        setattr(dialog, "display_folder", _wrapped_display_folder)
        _apply_descriptions_to_rows()
