# printer_uninstall.py - uninstalls the virtual printer and driver - mostly intended for testing purposes

import subprocess
import os
import time
import sys

# Define constants for printer and driver
PRINTER_SERVER_PORT = 9102
PRINTER_SERVER_ADDRESS = '127.0.0.1'
printer_port = f"{PRINTER_SERVER_ADDRESS}_{PRINTER_SERVER_PORT}"
driver_name = "Generic / Text Only"
printer_name = "VirtualTextPrinter"  # Name of the printer to remove

# Function to create the PowerShell script that includes all commands
def create_powershell_script(output_file):
    powershell_script = f"""
    Import-Module PrintManagement

    # Attempt to remove the printer
    Add-Content -Path "{output_file}" -Value "Attempting to remove printer '{printer_name}'...`n"
    if (Get-Printer -Name '{printer_name}' -ErrorAction SilentlyContinue) {{
        Remove-Printer -Name '{printer_name}'
        Add-Content -Path "{output_file}" -Value "Printer '{printer_name}' removed.`n"
    }} else {{
        Add-Content -Path "{output_file}" -Value "Printer '{printer_name}' not found.`n"
    }}

    # Clear all print jobs
    Add-Content -Path "{output_file}" -Value "Clearing all print jobs...`n"
    Get-Printer | ForEach-Object {{ Get-PrintJob -PrinterName $_.Name | Remove-PrintJob }}

    # Restart the print spooler
    Add-Content -Path "{output_file}" -Value "Restarting the print spooler service...`n"
    Stop-Service -Name Spooler -Force -ErrorAction SilentlyContinue
    Start-Service -Name Spooler

    # Attempt to remove the printer port
    Add-Content -Path "{output_file}" -Value "Attempting to remove the printer port '{printer_port}'...`n"
    $portName = "{printer_port}"
    if (Get-PrinterPort -Name $portName -ErrorAction SilentlyContinue) {{
        Remove-PrinterPort -Name $portName
        Add-Content -Path "{output_file}" -Value "Port '{printer_port}' removed.`n"
    }} else {{
        Add-Content -Path "{output_file}" -Value "Port '{printer_port}' not found.`n"
    }}

    # Attempt to remove the printer driver
    Add-Content -Path "{output_file}" -Value "Attempting to remove driver '{driver_name}'...`n"
    Remove-PrinterDriver -Name '{driver_name}' -RemoveFromDriverStore -ErrorAction SilentlyContinue

    # Show final state
    # List all printers
    Add-Content -Path "{output_file}" -Value "Listing all printers...`n"
    Get-Printer | Format-Table -AutoSize | Out-String | Add-Content -Path "{output_file}"

    # Show list of drivers
    Add-Content -Path "{output_file}" -Value "Driver installations:`n"
    Get-PrinterDriver | Select-Object Name, InfPath, DriverVersion | Format-Table -AutoSize | Out-String | Add-Content -Path "{output_file}"

    # Show printer ports
    Add-Content -Path "{output_file}" -Value "Printer Ports:`n"
    Get-PrinterPort | Select-Object Name, PortType, PortNumber, PrinterHostAddress | Format-Table -AutoSize | Out-String | Add-Content -Path "{output_file}"
    """

    # Write the PowerShell script to a file
    script_path = os.path.join(os.getcwd(), "manage_printer.ps1")
    with open(script_path, "w") as script_file:
        script_file.write(powershell_script)

    return script_path

# Function to remove temporary files
def cleanup_temp_files(script_path, output_file):
    try:
        if os.path.exists(script_path):
            os.remove(script_path)
            print(f"Temporary script file '{script_path}' deleted.")
        if os.path.exists(output_file):
            os.remove(output_file)
            print(f"Temporary output file '{output_file}' deleted.")
    except Exception as e:
        print(f"Error cleaning up temporary files: {e}")

# Main function to execute the PowerShell script and read output
def main():
    # Define the output file for logging
    output_file = os.path.join(os.getcwd(), "powershell_output.txt")

    # Ensure the output file is cleared before starting
    if os.path.exists(output_file):
        os.remove(output_file)

    # Create the PowerShell script
    script_path = create_powershell_script(output_file)

    # Run the PowerShell script with elevated privileges
    try:
        print("Requesting Administrator privileges to run PowerShell script...")
        command = [
            "powershell", "-Command",
            f"Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File \"{script_path}\"' -Verb RunAs"
        ]
        subprocess.run(command, check=True)
        print("PowerShell script executed with Administrator privileges.")
        
        # Wait for a moment to ensure the elevated process has time to complete and write the file
        time.sleep(5)

    except subprocess.CalledProcessError as e:
        print(f"Error running PowerShell script as admin: {e}")
        sys.exit(1)

    # Read and print the output from the file
    try:
        if os.path.exists(output_file):
            with open(output_file, "r") as file:
                output = file.read()
                print(f"PowerShell script output:\n{output}")
        else:
            print("PowerShell output file was not created.")
    except Exception as e:
        print(f"Error reading PowerShell output file: {e}")
    finally:
        # Clean up temporary files
        cleanup_temp_files(script_path, output_file)

if __name__ == "__main__":
    main()
