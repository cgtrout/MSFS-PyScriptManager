"""Automated test to verify command-line argument passing through the launcher."""
import subprocess
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from Lib.color_print import print_info, print_error, print_color

# Find pythonw.exe in WinPython
pythonw_path = PROJECT_ROOT / "WinPython" / "python-3.14.2.amd64" / "pythonw.exe"
if not pythonw_path.exists():
    # Fallback: use current Python interpreter
    pythonw_path = Path(sys.executable)

def test_arguments_passed():
    """Test that arguments are correctly passed to scripts."""
    print_info("Running automated argument passing test...")

    # Path to the test script
    test_script = PROJECT_ROOT / "Tests" / "test_script_args.py"

    # Test arguments
    test_args = ["hello", "world", "--debug", "--mode=test"]

    # Build command exactly as ScriptTab.run_script() does
    command = [
        str(pythonw_path.resolve()),
        "-u",
        str(test_script.resolve())
    ] + test_args

    print_color(f"\nRunning command:", color="cyan", bold=True)
    print_color(f"  {' '.join(command)}", color="cyan")

    # Execute the script
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=5
        )

        output = result.stdout
        print_color(f"\n{'='*60}", color="cyan")
        print_color("Script Output:", color="cyan", bold=True)
        print_color(f"{'='*60}", color="cyan")
        print(output)
        print_color(f"{'='*60}\n", color="cyan")

        # Verify the output contains our arguments
        success = True
        for i, arg in enumerate(test_args, start=1):
            expected = f"arg[{i}]: '{arg}'"
            if expected in output:
                print_color(f"[PASS] Found {expected}", color="green")
            else:
                print_error(f"[FAIL] Missing {expected}")
                success = False

        # Check that it received the correct number of args
        expected_count = f"Number of arguments: {len(test_args)}"
        if expected_count in output:
            print_color(f"[PASS] Correct argument count: {len(test_args)}", color="green")
        else:
            print_error(f"[FAIL] Wrong argument count (expected {len(test_args)})")
            success = False

        print()
        if success:
            print_color("="*60, color="green", bold=True)
            print_color("[PASS] TEST PASSED: All arguments were correctly passed!", color="green", bold=True)
            print_color("="*60, color="green", bold=True)
            return True
        else:
            print_color("="*60, color="red", bold=True)
            print_color("[FAIL] TEST FAILED: Some arguments were not passed correctly", color="red", bold=True)
            print_color("="*60, color="red", bold=True)
            return False

    except subprocess.TimeoutExpired:
        print_error("Test timed out!")
        return False
    except Exception as e:
        print_error(f"Test failed with exception: {e}")
        return False

if __name__ == "__main__":
    print_color("\n" + "="*60, color="cyan", bold=True)
    print_color("AUTOMATED SCRIPT ARGUMENT PASSING TEST", color="cyan", bold=True)
    print_color("="*60 + "\n", color="cyan", bold=True)

    success = test_arguments_passed()

    print()
    sys.exit(0 if success else 1)
