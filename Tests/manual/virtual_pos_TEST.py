# virtual_pos_TEST: tests virtual printer by sending new print job every few seconds

import subprocess
import time

# Counter for message numbering
message_counter = 1

def send_test_print_job():
    global message_counter
    printer_name = "VirtualTextPrinter"
    test_message = f"This is a test print job for VirtualTextPrinter - MESSAGE {message_counter}"

    print(f"Sending message directly to printer: '{test_message}'")

    # PowerShell command to send the message directly to the printer
    powershell_cmd = f"""
    $text = '{test_message}';
    $text | Out-Printer -Name '{printer_name}'
    """

    try:
        # Send the message directly to the printer using PowerShell (hidden window)
        result = subprocess.run(
            ["powershell", "-Command", powershell_cmd],
            capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        print(f"PowerShell stdout: {result.stdout}")
        print(f"PowerShell stderr: {result.stderr}")

        if result.returncode == 0:
            print(f"Test print job '{test_message}' sent successfully.")
        else:
            print("Failed to send print job. Check PowerShell output.")

    except subprocess.CalledProcessError as e:
        print(f"Error occurred while sending test print job: {e}")

    # Increment message counter for the next job
    message_counter += 1

# Run the test repeatedly
if __name__ == "__main__":
    try:
        while True:
            send_test_print_job()
            time.sleep(5)  # Wait 5 seconds before sending the next job
    except KeyboardInterrupt:
        print("Stopped sending print jobs.")
