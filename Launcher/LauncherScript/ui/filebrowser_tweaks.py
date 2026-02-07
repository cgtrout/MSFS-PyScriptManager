from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any


def create_hidden_filebrowser(filebrowser_class: type, **kwargs: Any) -> tk.Toplevel:
    """Construct a filebrowser while preventing an initial visible white frame."""
    original_toplevel_init = tk.Toplevel.__init__

    def _patched_toplevel_init(this: tk.Toplevel, *args: Any, **init_kwargs: Any) -> None:
        original_toplevel_init(this, *args, **init_kwargs)
        try:
            this.attributes("-alpha", 0.0)
            this.withdraw()
        except tk.TclError:
            pass

    tk.Toplevel.__init__ = _patched_toplevel_init
    try:
        return filebrowser_class(**kwargs)
    finally:
        tk.Toplevel.__init__ = original_toplevel_init


def prime_dark_theme_defaults(root: tk.Tk) -> None:
    """Seed ttk defaults before filebrowser construction to prevent first-paint flash."""
    bg_root = "#1F1F1F"
    bg_panel = "#202225"
    bg_field = "#191A1C"
    bg_alt = "#25282C"
    fg_text = "#E6E6E6"
    fg_muted = "#CFCFCF"
    sel_bg = "#2B4E6E"
    sel_fg = "#FFFFFF"
    border = "#34363A"

    style = ttk.Style(root)
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
    style.configure("Treeview", background=bg_field, fieldbackground=bg_field, foreground=fg_text)
    style.map("Treeview", background=[("selected", sel_bg)], foreground=[("selected", sel_fg)])

    # Align option-db colors used by listbox/combobox internals in tkfilebrowser.
    root.option_add("*Listbox.background", bg_field)
    root.option_add("*Listbox.foreground", fg_text)
    root.option_add("*Listbox.selectBackground", sel_bg)
    root.option_add("*Listbox.selectForeground", sel_fg)


def apply_filebrowser_dark_theme(dialog: tk.Toplevel) -> None:
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
