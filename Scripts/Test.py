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

    print_color("Hello, Microsoft Flight Simulator Enthusiast!", color="yellow", bold=True)
    print("Python is running from:", sys.executable)
    print()

    print_color("Click 'Run Script' button to load a different script.", color="green", bold=False)
    print("Load the 'virtual_pos_printer.py' script to run the virtual pop-up printer.")
    print("\nRight-click the tab for this script to close it.")

    print("\nThis script is loaded from the 'script group' file '_autoplay'.  \nDelete or save over this '_autoplay' script group file to stop this script from showing every load.")

if __name__ == "__main__":
    greet_msfs()