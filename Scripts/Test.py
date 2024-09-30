import sys
import datetime

def greet_msfs():
    """Simple function to greet the user and show the current date and time."""
    print("Hello, Microsoft Flight Simulator Enthusiast!")
    print("The current date and time is:", datetime.datetime.now())
    print("Python is running from:", sys.executable)

if __name__ == "__main__":
    greet_msfs()