"""Helpers for centering and foregrounding Tkinter windows on Windows."""

import ctypes
import sys
import tkinter as tk

try:
    import win32con
    import win32gui

    WINDOWS_API_AVAILABLE = True
except ImportError:
    WINDOWS_API_AVAILABLE = False


def _find_window_handle_by_title(title):
    """Find a window handle by exact title, then by case-insensitive partial match."""
    if sys.platform != "win32":
        return None

    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if hwnd:
        return hwnd

    if not WINDOWS_API_AVAILABLE or not title:
        return None

    target = title.lower()
    matches = []

    def _enum_handler(candidate_hwnd, _):
        if not win32gui.IsWindowVisible(candidate_hwnd):
            return
        text = win32gui.GetWindowText(candidate_hwnd) or ""
        if target in text.lower():
            matches.append(candidate_hwnd)

    try:
        win32gui.EnumWindows(_enum_handler, None)
        return matches[0] if matches else None
    except Exception:
        return None


def force_window_focus_windows(window):
    """
    Use Windows API to force a window to the foreground and steal focus.
    Falls back to Tkinter-only focus methods when unavailable.
    """
    if sys.platform != "win32" or not WINDOWS_API_AVAILABLE:
        window.focus_force()
        return

    try:
        hwnd = int(window.wm_frame(), 16)

        foreground_hwnd = win32gui.GetForegroundWindow()
        foreground_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(
            foreground_hwnd, None
        )
        current_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        if foreground_thread_id != current_thread_id:
            ctypes.windll.user32.AttachThreadInput(
                current_thread_id, foreground_thread_id, True
            )

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
            )
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.SetFocus(hwnd)
        finally:
            if foreground_thread_id != current_thread_id:
                ctypes.windll.user32.AttachThreadInput(
                    current_thread_id, foreground_thread_id, False
                )

    except Exception as exc:
        print(f"Windows API focus failed: {exc}, using Tkinter fallback")
        window.focus_force()


def center_window(
    window,
    keep_on_top=False,
    launcher_title="MSFS-PyScriptManager",
    use_cascade=True,
    cascade_mode="offset",
    cascade_offset=28,
):
    """
    Center/cascade a Tkinter window and aggressively surface it to the foreground.
    """
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    def get_position(target_width, target_height):
        x = max(0, (screen_width - target_width) // 2)
        y = max(0, (screen_height - target_height) // 2)

        if not use_cascade:
            return x, y

        try:
            user32 = ctypes.windll.user32

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            target_hwnd = None
            if launcher_title:
                target_hwnd = _find_window_handle_by_title(launcher_title)
            if not target_hwnd:
                target_hwnd = user32.GetForegroundWindow()

            if target_hwnd:
                rect = RECT()
                if user32.GetWindowRect(target_hwnd, ctypes.byref(rect)):
                    if cascade_mode == "next_to":
                        margin = 14
                        x = rect.right + margin
                        y = rect.top + cascade_offset
                        if x > (screen_width - target_width):
                            x = rect.left - target_width - margin
                    else:
                        x = rect.left + cascade_offset
                        y = rect.top + cascade_offset
                    x = max(0, min(x, max(0, screen_width - target_width)))
                    y = max(0, min(y, max(0, screen_height - target_height)))
        except Exception:
            pass
        return x, y

    window.update_idletasks()
    width = max(window.winfo_width(), window.winfo_reqwidth())
    height = max(window.winfo_height(), window.winfo_reqheight())
    x, y = get_position(width, height)

    window.geometry(f"{width}x{height}+{x}+{y}")

    try:
        window.attributes("-topmost", True)
    except tk.TclError:
        pass

    window.deiconify()
    window.update_idletasks()
    final_width = window.winfo_width()
    final_height = window.winfo_height()
    final_x, final_y = get_position(final_width, final_height)
    window.geometry(f"+{final_x}+{final_y}")
    window.lift()
    force_window_focus_windows(window)

    def enforce_final_position():
        try:
            window.update_idletasks()
            current_width = window.winfo_width()
            current_height = window.winfo_height()
            move_x, move_y = get_position(current_width, current_height)
            if sys.platform == "win32" and WINDOWS_API_AVAILABLE:
                hwnd = int(window.wm_frame(), 16)
                win32gui.SetWindowPos(
                    hwnd,
                    0,
                    move_x,
                    move_y,
                    0,
                    0,
                    win32con.SWP_NOZORDER | win32con.SWP_NOSIZE,
                )
            else:
                window.geometry(f"+{move_x}+{move_y}")
        except tk.TclError:
            return

    def reinforce_focus():
        try:
            enforce_final_position()
            force_window_focus_windows(window)
            if not keep_on_top:
                window.attributes("-topmost", False)
                if sys.platform == "win32" and WINDOWS_API_AVAILABLE:
                    hwnd = int(window.wm_frame(), 16)
                    win32gui.SetWindowPos(
                        hwnd,
                        win32con.HWND_NOTOPMOST,
                        0,
                        0,
                        0,
                        0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
                    )
        except tk.TclError:
            return

    window.after(20, enforce_final_position)
    window.after(250, reinforce_focus)


def focus_window_by_title(window_title):
    """Bring an existing top-level window (by title) to the foreground."""
    if sys.platform != "win32" or not WINDOWS_API_AVAILABLE:
        return False

    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, window_title)
        if not hwnd:
            return False

        foreground_hwnd = win32gui.GetForegroundWindow()
        foreground_thread_id = ctypes.windll.user32.GetWindowThreadProcessId(
            foreground_hwnd, None
        )
        current_thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        if foreground_thread_id != current_thread_id:
            ctypes.windll.user32.AttachThreadInput(
                current_thread_id, foreground_thread_id, True
            )

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
            win32gui.SetFocus(hwnd)
        finally:
            if foreground_thread_id != current_thread_id:
                ctypes.windll.user32.AttachThreadInput(
                    current_thread_id, foreground_thread_id, False
                )

        return True
    except Exception as exc:
        print(f"Failed to focus window '{window_title}': {exc}")
        return False
