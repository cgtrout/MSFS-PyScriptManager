import sys
import datetime

def greet_msfs():
    """Simple function to greet the user and show the current date and time."""
    print("Hello, Microsoft Flight Simulator Enthusiast!")
    print("The current date and time is:", datetime.datetime.now())
    print("Python is running from:", sys.executable)
    
    print("\nClick 'Run Script' to load a different script.")
    print("Load the 'virtual_pos_printer.py' script to run the virtual pop-up printer.")
    print("\nRight-click the tab for this script to close it.")

    print("\nThis script is loaded from the 'script group' file '_autoplay'.  \nDelete or save over this '_autoplay' script group file to stop this script from showing every load.")

if __name__ == "__main__":
    greet_msfs()