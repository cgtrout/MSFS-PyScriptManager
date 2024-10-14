import os
import platform
import shutil
import tkinter as tk
import json
from tkinter import messagebox

def find_usercfg_file():
    print("Detecting operating system...")
    if platform.system() != "Windows":
        print("This script is intended for Windows only.")
        raise EnvironmentError("Non-Windows OS detected.")
    
    print("Locating UserCfg.opt file...")
    possible_usercfg_paths = [
        os.path.join("C:\\", "Users", os.environ['USERNAME'], "AppData", "Local", "Packages", "Microsoft.FlightSimulator_8wekyb3d8bbwe", "LocalCache", "UserCfg.opt"),  # MS Store
        os.path.join("C:\\", "Users", os.environ['USERNAME'], "AppData", "Roaming", "Microsoft Flight Simulator", "UserCfg.opt"),  # Steam or custom install
    ]
    
    for path in possible_usercfg_paths:
        if os.path.exists(path):
            print(f"UserCfg.opt found at {path}")
            return path

    raise FileNotFoundError("UserCfg.opt file not found. Please check for a custom installation path.")

def parse_installed_packages_path(usercfg_path):
    print("Reading the InstalledPackagesPath from UserCfg.opt...")
    try:
        with open(usercfg_path, 'r') as file:
            for line in file:
                if line.strip().startswith("InstalledPackagesPath"):
                    parts = line.split('"')
                    if len(parts) > 1:
                        print(f"InstalledPackagesPath detected: {parts[1]}")
                        return parts[1]
    except Exception as e:
        raise IOError(f"Error reading UserCfg.opt file: {e}")

    raise ValueError("InstalledPackagesPath not found in UserCfg.opt file.")

def find_community_path(installed_packages_path):
    print("Locating the Community folder...")
    community_path = os.path.join(installed_packages_path, "Community")
    if os.path.exists(community_path):
        print(f"Community folder found at {community_path}")
        return community_path
    else:
        raise FileNotFoundError("Community folder not found. Check the InstalledPackagesPath.")

def locate_mod_source_path():
    # Start from the script directory and navigate to the root directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, "../.."))
    
    # Define the relative path to the mod directory
    mod_relative_path = os.path.join(root_dir, "Data", "Community_Install", "chrisaut-toolbar-printouts")
    
    print(f"Checking for mod directory at: {mod_relative_path}")
    if not os.path.exists(mod_relative_path):
        raise FileNotFoundError(f"Mod directory not found at expected location: {mod_relative_path}")
    
    print(f"Mod directory located at: {mod_relative_path}")
    return mod_relative_path

def show_files_to_copy(mod_source_path, destination_path):
    mod_name = os.path.basename(mod_source_path)
    final_destination = os.path.join(destination_path, mod_name)
    
    print(f"Testing Copy: Showing files that would be copied from {mod_source_path} to {final_destination}")
    
    for root, dirs, files in os.walk(mod_source_path):
        relative_path = os.path.relpath(root, mod_source_path)
        dest_dir = os.path.join(final_destination, relative_path)
        
        for file in files:
            source_file = os.path.join(root, file)
            dest_file = os.path.join(dest_dir, file)
            print(f"Would copy: {source_file} to {dest_file}")

def validate_copy(mod_source_path, destination_path):
    print("Validating copied files...")
    source_files = {}
    destination_files = {}

    # Build dictionary of source files with modification times
    for root, _, files in os.walk(mod_source_path):
        for file in files:
            source_file_path = os.path.join(root, file)
            relative_path = os.path.relpath(source_file_path, mod_source_path)
            source_files[relative_path] = os.path.getmtime(source_file_path)

    # Build dictionary of destination files with modification times
    for root, _, files in os.walk(destination_path):
        for file in files:
            destination_file_path = os.path.join(root, file)
            relative_path = os.path.relpath(destination_file_path, destination_path)
            destination_files[relative_path] = os.path.getmtime(destination_file_path)

    # Compare files and modification times
    all_files_match = True
    for relative_path, mod_time in source_files.items():
        if relative_path not in destination_files:
            print(f"Missing file in destination: {relative_path}")
            all_files_match = False
        elif mod_time != destination_files[relative_path]:
            print(f"File modification date mismatch for: {relative_path}")
            all_files_match = False

    for relative_path in destination_files:
        if relative_path not in source_files:
            print(f"Unexpected file in destination: {relative_path}")
            all_files_match = False

    if all_files_match:
        print("Validation successful: All files copied correctly.")
        return True
    else:
        print("Validation failed: Some files were not copied correctly.")
        return False

def copy_files_to_community(mod_source_path, destination_path):
    mod_name = os.path.basename(mod_source_path)
    final_destination = os.path.join(destination_path, mod_name)
    
    print(f"Copying {mod_name} to {destination_path}...")
    try:
        if os.path.exists(final_destination) and os.listdir(final_destination):
            print(f"Directory {final_destination} already exists and is not empty. Overwriting contents...")
        elif os.path.exists(final_destination):
            print(f"Directory {final_destination} exists and is empty. Copying files into it...")

        # Copy the directory, allowing existing directories to be overwritten
        shutil.copytree(mod_source_path, final_destination, dirs_exist_ok=True)

        # Validate the copy after completion
        if validate_copy(mod_source_path, final_destination):
            print("Copy and validation successful.")
            return True
        else:
            print("Validation failed after copying.")
            return False

    except Exception as e:
        print(f"Failed to copy the mod to the destination folder: {e}")
        return False

def ensure_enable_popups_false():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.abspath(os.path.join(script_dir, "../.."))
    
    # Construct the path to the settings.json file
    settings_file_path = os.path.join(root_dir, "Settings", "settings.json")
    
    print("Checking 'enable_popups' setting in settings.json...")
    settings = {}
    
    # Try to load the existing settings file, or initialize if it doesn't exist
    try:
        if os.path.exists(settings_file_path):
            with open(settings_file_path, 'r') as file:
                settings = json.load(file)
                print("Loaded existing settings.json file.")
        else:
            print("settings.json not found. Creating a new file with default settings.")
    
    except json.JSONDecodeError:
        print("Error reading settings.json. File may be corrupt. Recreating file with default settings.")
    
    # Check if 'enable_popups' is set to false; if not, add or update it
    if settings.get("enable_popups", True):  # Default to True if the key is missing
        print("'enable_popups' is not set to False. Updating the setting...")
        settings["enable_popups"] = False
    else:
        print("'enable_popups' is already set to False. No changes needed.")

    # Write the updated settings back to the file
    try:
        with open(settings_file_path, 'w') as file:
            json.dump(settings, file, indent=4)
            print("'enable_popups' has been ensured to be set to False in settings.json.")
    
    except Exception as e:
        print(f"An error occurred while saving settings.json: {e}")

def main():
    print("Starting mod installation process...")
    
    # Initialize tkinter and hide the main window
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    
    # Ask user if they want to proceed with the installation
    proceed = messagebox.askyesno("Install Mod", "Do you want to proceed with the installation of the Virtual Printer MSFS toolbar addon?")
    if not proceed:
        print("Installation aborted by the user.")
        return  # Exit the script if the user does not want to proceed

    # Flag to control whether to use the test directory or actual Community folder
    use_test_directory = False  # Change this flag to False to use the actual Community folder
    test_directory = r"d:\_Community_install_test"

    try:
        # Locate mod directory based on the relative path from the script
        mod_source_path = locate_mod_source_path()
        
        # Proceed with finding the community folder and showing files that would be copied
        usercfg_path = find_usercfg_file()
        installed_packages_path = parse_installed_packages_path(usercfg_path)
        community_path = find_community_path(installed_packages_path)
        
        # Determine the destination directory
        destination_path = test_directory if use_test_directory else community_path
        print(f"Destination path set to: {destination_path}")

        # Show print of files to copy if test dir present         
        if use_test_directory:
            show_files_to_copy(mod_source_path, destination_path)
        
        # Perform the actual copy to the selected directory
        valid_copy = copy_files_to_community(mod_source_path, destination_path)

        # Ensure settings popup set to false
        ensure_enable_popups_false()

        if(validate_copy):
            print("\nCopy of community toolbar was successful!")
            final_message = "Copy of community toolbar was successful!"
            messagebox.showinfo("Installer", final_message)
        else:
            final_message = "Copy of community toolbar failed validation. Please see log for details."
            messagebox.showerror("Installer: failed", final_message)
            raise Exception("Installer", "Unsuccessful validation of copy")
        
    except Exception as e:
        print(f"An error occurred: {e}")
        print("\nManual Copy Instructions:")
        print(f"1. Locate the mod at: {mod_source_path if 'mod_source_path' in locals() else 'Unknown location'}")
        print(f"2. Copy the folder manually to the MSFS Community folder at: {community_path if 'community_path' in locals() else 'Unknown location'}")
        print("Please make sure the mod folder structure is intact after copying.")
        
        final_message = f"Copy of community toolbar failed validation. Please see log for details.\n\n{e}"
        messagebox.showerror("Installer: failed", final_message)
        
if __name__ == "__main__":
    main()
