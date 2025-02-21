import sys
import datetime

try:
    # Import all color print functions
    from Lib.color_print import *

except ImportError:
    print("Failed to import 'Lib.color_print'. Please ensure /Lib/color_print.py is present")
    sys.exit(1)

def greet_msfs():
    """Simple function to greet the user and show the current date and time."""

    print_color("Welcome to MSFS-PyScriptManager!", color="yellow", bold=True)
    print("Python is running from:\n", sys.executable)
    print("="*100)

    print_color("\nInstructions:\n", color="green", bold=True)
    print_color("1. Click [yellow(]Run Script[)] button to load a different script.")
    print_color("2. Example: To run the virtual Printer: run [yellow(]virtual_pos_printer.py[)]\n")
    print_color("\n  * Right-click the tab for this script  [yellow(]z_intro_script.py[)] to close it.")

    print("\n  * This script is loaded from the 'script group' file '_autoplay'.  "
          "\n  * Delete or save over this '_autoplay' script group file to stop this script "
          "from showing every load.\n\n")

if __name__ == "__main__":
    greet_msfs()