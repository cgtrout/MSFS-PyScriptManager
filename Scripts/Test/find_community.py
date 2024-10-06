import os
import platform
import re

def find_usercfg_file():
    # Check if the OS is Windows
    if platform.system() != "Windows":
        raise EnvironmentError("This script is intended for Windows only.")

    # Locate UserCfg.opt file, which contains the path to InstalledPackages
    possible_usercfg_paths = [
        os.path.join("C:\\", "Users", os.environ['USERNAME'], "AppData", "Local", "Packages", "Microsoft.FlightSimulator_8wekyb3d8bbwe", "LocalCache", "UserCfg.opt"),  # MS Store
        os.path.join("C:\\", "Users", os.environ['USERNAME'], "AppData", "Roaming", "Microsoft Flight Simulator", "UserCfg.opt"),  # Steam or custom install
    ]

    found_paths = set()
    for path in possible_usercfg_paths:
        if os.path.exists(path):
            if path not in found_paths:
                found_paths.add(path)
                return path

    raise FileNotFoundError("UserCfg.opt file not found. It may be installed in a custom location.")

def parse_installed_packages_path(usercfg_path):
    # Read the InstalledPackagesPath from UserCfg.opt
    installed_packages_path = None
    try:
        with open(usercfg_path, 'r') as file:
            for line in file:
                match = re.search(r'InstalledPackagesPath\s*"(.+?)"', line)
                if match:
                    installed_packages_path = match.group(1)
                    return installed_packages_path
    except Exception as e:
        raise IOError(f"Error reading UserCfg.opt file: {e}")

    raise ValueError(f"InstalledPackagesPath not found in UserCfg.opt file: {usercfg_path}")

def get_msfs_paths():
    try:
        usercfg_path = find_usercfg_file()
        installed_packages_path = parse_installed_packages_path(usercfg_path)
        return usercfg_path, installed_packages_path
    except (EnvironmentError, FileNotFoundError, IOError, ValueError) as e:
        raise e

if __name__ == "__main__":
    try:
        usercfg_path, installed_packages_path = get_msfs_paths()
        print(f"UserCfg.opt file is located at: {usercfg_path}")
        print(f"InstalledPackagesPath is located at: {installed_packages_path}")
    except Exception as e:
        print(f"An error occurred: {e}")