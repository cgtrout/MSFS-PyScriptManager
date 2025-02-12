import ctypes
import sys

class DarkmodeUtils:
    """Utility class for handling dark mode UI features."""

    @staticmethod
    def is_windows_11():
        """Check if the system is running Windows 11 or later."""
        if hasattr(sys, 'getwindowsversion'):
            version = sys.getwindowsversion()
            # Windows 11 has major version 10 and build number >= 22000
            return (version.major == 10 and version.build >= 22000) or version.major > 10
        return False

    @staticmethod
    def dark_title_bar(hwnd):
        """Enable dark mode for the title bar."""
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)  # Use 1 to enable dark mode
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )
            if result == 0:
                print("[INFO] Dark mode applied successfully.")
            else:
                print(f"[ERROR] Failed to apply dark mode. Error code: {result}")
        except Exception as e:
            print(f"[ERROR] An exception occurred while applying dark mode: {e}")

    @staticmethod
    def is_valid_window(hwnd):
        """Check if the given HWND is a valid window handle."""
        return ctypes.windll.user32.IsWindow(hwnd) != 0

    @staticmethod
    def get_top_level_hwnd(hwnd):
        """Retrieve the top-level window handle."""
        GA_ROOT = 2  # Constant for the top-level ancestor
        return ctypes.windll.user32.GetAncestor(hwnd, GA_ROOT)

    @staticmethod
    def apply_dark_mode(root):
        """Apply dark mode to the top-level window of a Tkinter root."""
        try:
            if DarkmodeUtils.is_windows_11():
                hwnd = int(root.winfo_id())
                top_level_hwnd = DarkmodeUtils.get_top_level_hwnd(hwnd)
                if not DarkmodeUtils.is_valid_window(top_level_hwnd):
                    print("[ERROR] Invalid top-level window handle.")
                    return
                print(f"Applying dark mode to Top-Level HWND: {top_level_hwnd}")
                DarkmodeUtils.dark_title_bar(top_level_hwnd)
                ctypes.windll.user32.RedrawWindow(top_level_hwnd, None, None, 0x85)
        except Exception as e:
            print(f"[ERROR] apply_dark_mode: An exception occurred while applying dark mode: {e}")