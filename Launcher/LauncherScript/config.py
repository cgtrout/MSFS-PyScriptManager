# config.py - Configuration, constants, and path setup for MSFSPyScriptManager

import configparser
import os
import sys
from pathlib import Path

# Path to the WinPython Python executable and VS Code.exe
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parents[1]

# Color constants
DARK_BG_COLOR = "#2E2E2E"
BUTTON_BG_COLOR = "#444444"
BUTTON_FG_COLOR = "#EEEEEE"
BUTTON_ACTIVE_BG_COLOR = "#666666"
BUTTON_ACTIVE_FG_COLOR = "#FFFFFF"
TEXT_WIDGET_BG_COLOR = "#171717"
TEXT_WIDGET_FG_COLOR = "#FFFFFF"
TEXT_WIDGET_INSERT_COLOR = "#FFFFFF"
FRAME_BG_COLOR = "#2E2E2E"

# Delay load between scripts
SCRIPT_LOAD_DELAY_MS = 20

# GitHub repository for update checks
UPDATE_REPO_OWNER = "cgtrout"
UPDATE_REPO_NAME = "MSFS-PyScriptManager"


def find_system_vscode():
    """Search for VS Code in common installation locations."""
    import shutil

    # Common VS Code locations on Windows
    common_paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Microsoft VS Code/Code.exe",
        Path("C:/Program Files/Microsoft VS Code/Code.exe"),
        Path("C:/Program Files (x86)/Microsoft VS Code/Code.exe"),
    ]

    for p in common_paths:
        if p.exists():
            return str(p)

    # Try to find 'code' in PATH
    code_path = shutil.which("code")
    if code_path:
        return code_path

    return None


def read_launcher_config():
    """Read launcher configuration from launcher.ini file."""
    config = configparser.ConfigParser()
    ini_path = project_root / "Launcher" / "launcher.ini"

    # Default values
    python_dir = "WinPython/Winpython64-3.13.0.1dotrc1/python-3.13.0rc1.amd64"

    if ini_path.exists():
        try:
            config.read(ini_path)
            if config.has_option('Python', 'PythonDir'):
                python_dir = config.get('Python', 'PythonDir').strip().replace('\\', '/')
                # Treat leading slash as a mistaken "rooted relative" path and normalize it.
                # Example: "\WinPython\WPy64-313110\python" -> "WinPython/WPy64-313110/python"
                python_dir_path = Path(python_dir)
                if (python_dir.startswith(("/", "\\")) and not python_dir_path.drive):
                    python_dir = python_dir.lstrip("/\\")
            print(f"[INFO] Loaded configuration from {ini_path}")
        except Exception as e:
            print(f"[WARNING] Error reading launcher.ini: {e}. Using defaults.")
    else:
        print(f"[INFO] launcher.ini not found at {ini_path}. Using default paths.")

    # Check if the configured Python path actually exists
    configured_python = project_root / python_dir / "python.exe"
    if not configured_python.exists():
        # Fall back to system Python (the one running this script)
        print("")
        print("=" * 80)
        print("                    RUNNING WITH SYSTEM PYTHON (BYO MODE)")
        print("=" * 80)
        print(f"  Python: {sys.executable}")
        print(f"  Version: {sys.version}")
        print("")
        print("  WARNING: You are running with your system Python installation.")
        print("  This configuration is not officially supported.")
        print("  For best compatibility, use the bundled WinPython distribution.")
        print("=" * 80)
        print("", flush=True)

        # Return the directory containing sys.executable
        system_python_dir = str(Path(sys.executable).parent)
        vscode_path_str = find_system_vscode()
        return system_python_dir, vscode_path_str

    # Derive VS Code launch script from Python directory
    # winvscode.bat properly forwards arguments to the real code.exe;
    # "VS Code.exe" in the same directory is a WinPython GUI launcher that does not.
    # e.g., WinPython/WPy64-313110/python
    #    -> WinPython/WPy64-313110/scripts/winvscode.bat
    python_path_obj = Path(python_dir)
    vscode_path_str = str(python_path_obj.parent / "scripts" / "winvscode.bat")

    return python_dir, vscode_path_str


def read_byo_auto_install_setting():
    """Read the AutoInstallDeps setting from launcher.ini for BYO mode."""
    config = configparser.ConfigParser()
    ini_path = project_root / "Launcher" / "launcher.ini"
    if ini_path.exists():
        try:
            config.read(ini_path)
            if config.has_option('BYO', 'AutoInstallDeps'):
                return config.get('BYO', 'AutoInstallDeps').strip().lower() == 'true'
        except Exception:
            pass
    return None  # Not set yet


def save_byo_auto_install_setting(value: bool):
    """Save the AutoInstallDeps setting to launcher.ini."""
    config = configparser.ConfigParser()
    ini_path = project_root / "Launcher" / "launcher.ini"

    # Read existing config if present
    if ini_path.exists():
        try:
            config.read(ini_path)
        except Exception:
            pass

    # Ensure BYO section exists
    if not config.has_section('BYO'):
        config.add_section('BYO')

    config.set('BYO', 'AutoInstallDeps', str(value).lower())

    with open(ini_path, 'w') as f:
        config.write(f)


def read_update_config():
    """Read update configuration from launcher.ini."""
    config = configparser.ConfigParser()
    ini_path = project_root / "Launcher" / "launcher.ini"

    # Defaults
    update_owner = UPDATE_REPO_OWNER
    update_repo = UPDATE_REPO_NAME
    check_on_startup = True
    check_interval_hours = 24

    if ini_path.exists():
        try:
            config.read(ini_path)
            if config.has_section("Update"):
                update_owner = config.get("Update", "RepoOwner", fallback=update_owner).strip()
                update_repo = config.get("Update", "RepoName", fallback=update_repo).strip()
                check_on_startup = config.getboolean("Update", "CheckOnStartup", fallback=check_on_startup)
                check_interval_hours = config.getint("Update", "CheckIntervalHours", fallback=check_interval_hours)
        except Exception as e:
            print(f"[WARNING] Error reading update config from launcher.ini: {e}. Using defaults.")

    return update_owner, update_repo, check_on_startup, check_interval_hours


# Initialize paths from config
python_dir_str, vscode_path_str = read_launcher_config()

# Handle both relative (WinPython) and absolute (system Python) paths
python_dir_path = Path(python_dir_str)
if python_dir_path.is_absolute():
    # System Python - use absolute path directly
    python_path = python_dir_path / "python.exe"
    pythonw_path = python_dir_path / "pythonw.exe"
else:
    # WinPython - relative to project root
    python_path = project_root / python_dir_str / "python.exe"
    pythonw_path = project_root / python_dir_str / "pythonw.exe"

# Handle VS Code path (can be None for system Python if not found)
if vscode_path_str:
    vscode_path_obj = Path(vscode_path_str)
    if vscode_path_obj.is_absolute():
        vscode_path = vscode_path_obj
    else:
        vscode_path = project_root / vscode_path_str
else:
    vscode_path = None

# Validate pythonw.exe exists - fall back to python.exe if not
# (System Python installs usually have pythonw.exe, but not always)
if not pythonw_path.exists():
    print(f"[WARNING] pythonw.exe not found at {pythonw_path}")
    print(f"[WARNING] Falling back to python.exe (console window may appear for scripts)")
    pythonw_path = python_path

scripts_path = project_root / "Scripts"
data_path = project_root / "Data"
version_file_path = project_root / "Launcher" / "version.txt"
update_cache_path = data_path / "update_cache.json"
logs_path = project_root / "Logs"
logs_path.mkdir(parents=True, exist_ok=True)

# Track if we're running in BYO (system Python) mode
is_byo_mode = python_dir_path.is_absolute()
