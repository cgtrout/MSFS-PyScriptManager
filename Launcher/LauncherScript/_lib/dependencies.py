# dependencies.py - dependency installation helpers

from __future__ import annotations

import subprocess
import tkinter as tk
from tkinter import messagebox

from config import (
    project_root, python_path, is_byo_mode,
    read_byo_auto_install_setting, save_byo_auto_install_setting
)


def prompt_byo_install() -> bool:
    """Prompt user whether to auto-install dependencies in BYO mode using a dialog."""
    # Create hidden root window for dialog
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)  # Ensure dialog appears on top

    requirements_path = project_root / "Launcher" / "requirements.txt"
    message = (
        "MSFS-PyScriptManager requires additional Python packages.\n\n"
        f"Requirements file:\n{requirements_path}\n\n"
        "Install dependencies to your system Python?\n\n"
        "(Your choice will be remembered for future runs)"
    )

    result = messagebox.askyesno(
        "BYO Python - Install Dependencies?",
        message,
        icon='question'
    )

    root.destroy()

    if result:
        save_byo_auto_install_setting(True)
        print("[INFO] User approved dependency installation.")
        return True

    save_byo_auto_install_setting(False)
    print("[INFO] User declined dependency installation.")
    print("[INFO] You can manually run: pip install -r Launcher/requirements.txt")
    return False


def ensure_dependencies() -> None:
    """Ensure third-party dependencies are installed."""
    requirements_path = project_root / "Launcher" / "requirements.txt"
    if not requirements_path.exists():
        return

    # In BYO mode, check if user has approved auto-install
    if is_byo_mode:
        auto_install = read_byo_auto_install_setting()
        if auto_install is None:
            # First time - ask user
            if not prompt_byo_install():
                return  # User said no
        elif not auto_install:
            # User previously said no
            print("[INFO] Skipping dependency install (BYO mode, auto-install disabled)")
            return

    print(f"[INFO] Checking dependencies from {requirements_path}...", flush=True)
    process = subprocess.Popen(
        [str(python_path), "-u", "-m", "pip", "install", "--disable-pip-version-check", "--no-warn-script-location", "-r", str(requirements_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    for line in iter(process.stdout.readline, ''):
        if "already satisfied" not in line:
            print(line, end="", flush=True)
    process.wait()
    if process.returncode != 0:
        print(f"[WARNING] pip install returned {process.returncode}. Some packages may be missing.", flush=True)
