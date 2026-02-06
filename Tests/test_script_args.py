"""Test script to verify command-line argument passing works correctly."""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from Lib.color_print import print_info, print_color

print_info("Script started!")
print_color(f"Script name: {sys.argv[0]}", color="cyan")
print_color(f"Number of arguments: {len(sys.argv) - 1}", color="cyan")

if len(sys.argv) > 1:
    print_color("\nReceived arguments:", color="green", bold=True)
    for i, arg in enumerate(sys.argv[1:], start=1):
        print_color(f"  arg[{i}]: {arg!r}", color="yellow")
else:
    print_color("\nNo arguments received.", color="yellow")

print_info("Test complete!")
