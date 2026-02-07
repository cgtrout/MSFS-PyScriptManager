"""Manual test for virtual_pos_printer scroll behavior on large print jobs.

Expected behavior:
- Short jobs: popup should render without a scrollbar.
- Large jobs: popup should be height-capped and vertically scrollable.
"""

import subprocess
import time

PRINTER_NAME = "VirtualTextPrinter"


def send_print_job(text: str) -> bool:
    """Send text directly to the configured Windows printer."""
    powershell_cmd = f"""
    $text = @'
{text}
'@;
    $text | Out-Printer -Name '{PRINTER_NAME}'
    """

    result = subprocess.run(
        ["powershell", "-Command", powershell_cmd],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    if result.returncode != 0:
        print("[FAIL] Could not send print job.")
        print(f"stdout: {result.stdout.strip()}")
        print(f"stderr: {result.stderr.strip()}")
        return False

    return True


def build_large_message(line_count: int = 200) -> str:
    """Create a multi-line message large enough to trigger popup scrolling."""
    lines = [f"SCROLL TEST LINE {i:03d} - The quick brown fox jumps over the lazy dog." for i in range(1, line_count + 1)]
    return "\n".join(lines)


def main() -> None:
    print("Manual Test: virtual_pos_printer scroll behavior")
    print("Prerequisite: run Scripts/virtual_pos_printer.py before this test.")
    print()

    short_message = "SHORT TEST: this popup should NOT show a scrollbar."
    large_message = build_large_message()

    print("[STEP 1] Sending short message...")
    if not send_print_job(short_message):
        return
    time.sleep(2)

    print("[STEP 2] Sending large message...")
    if not send_print_job(large_message):
        return
    time.sleep(2)

    print()
    print("Pass Criteria:")
    print("1. Short popup appears without a vertical scrollbar.")
    print("2. Large popup is capped in height and shows a vertical scrollbar.")
    print("3. Mouse wheel scrolls large popup content.")
    print("4. Ctrl+MouseWheel still changes font size.")
    print("5. Right-click still closes each popup.")


if __name__ == "__main__":
    main()
