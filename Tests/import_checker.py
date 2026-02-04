"""
Import Checker - Tests that all project dependencies can be imported.

Usage:
    python import_checker.py              # Test with current Python
    python import_checker.py --discover   # Test all WinPython versions found
    python import_checker.py --list       # List discovered WinPython versions
"""

import sys
import argparse
import subprocess
import importlib
from pathlib import Path
from typing import NamedTuple


# =============================================================================
# Configuration
# =============================================================================

SKIP_PACKAGES = {
    "tkinter",  # Built-in, tested separately
}

# =============================================================================
# Import Testing
# =============================================================================

class ImportResult(NamedTuple):
    name: str
    success: bool
    error: str | None
    source: str


def try_import(module_name: str) -> tuple[bool, str | None]:
    """Attempt to import a module."""
    try:
        importlib.import_module(module_name)
        return True, None
    except ImportError as e:
        return False, f"ImportError: {e}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def get_import_names_for_package(package_name: str) -> list[str]:
    """Auto-discover import name(s) for a pip package."""
    candidates = []
    package_lower = package_name.lower()

    try:
        from importlib.metadata import packages_distributions
        pkg_to_dist = packages_distributions()
        import_names = [
            name for name, dists in pkg_to_dist.items()
            if package_lower in [d.lower() for d in dists]
        ]
        for name in sorted(import_names, key=lambda x: (x.startswith("_"), len(x))):
            if not name.startswith("_") and name not in candidates:
                candidates.append(name)
    except Exception:
        pass

    # Fallback naming conventions
    for fb in [package_lower.replace("-", "_"), package_name, package_name.replace("-", "_")]:
        if fb not in candidates:
            candidates.append(fb)

    return candidates if candidates else [package_lower]


def try_import_any(import_names: list[str]) -> tuple[bool, str | None]:
    """Try importing from a list of candidates. First success wins."""
    errors = []
    for name in import_names:
        success, error = try_import(name)
        if success:
            return True, None
        errors.append(f"{name}: {error}")
    return False, "; ".join(errors)


def parse_requirements(requirements_path: Path) -> list[str]:
    """Parse requirements.txt and extract package names, respecting environment markers."""
    if not requirements_path.exists():
        return []

    # Import packaging for marker evaluation
    try:
        from packaging.markers import Marker, InvalidMarker
    except ImportError:
        Marker = None
        InvalidMarker = Exception

    packages = []
    with open(requirements_path, "r") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines, comments, and pip flags
            if not line or line.startswith("#") or line.startswith("-"):
                continue

            # Check for environment marker (PEP 508)
            marker_str = None
            if ";" in line:
                line, marker_str = line.split(";", 1)
                marker_str = marker_str.strip()

            # Extract package name (strip version specifiers and extras)
            package = line.split("==")[0].split(">=")[0].split("<=")[0].split("<")[0].split(">")[0].split("[")[0].strip()
            if not package:
                continue

            # Evaluate environment marker if present
            if marker_str and Marker is not None:
                try:
                    marker = Marker(marker_str)
                    if not marker.evaluate():
                        continue  # Skip package - marker doesn't match current environment
                except InvalidMarker:
                    pass  # Invalid marker syntax, include package anyway

            packages.append(package)
    return packages


def discover_lib_modules(lib_path: Path) -> list[str]:
    """Discover all importable modules in Lib directory."""
    if not lib_path.exists():
        return []

    modules = []
    for item in lib_path.iterdir():
        if item.is_file() and item.suffix == ".py" and not item.name.startswith("_"):
            modules.append(item.stem)
        elif item.is_dir() and not item.name.startswith("_"):
            if (item / "__init__.py").exists() or any(item.glob("*.py")):
                modules.append(item.name)
    return modules


def run_import_tests(project_root: Path) -> int:
    """Run all import tests. Returns number of failures."""
    requirements_path = project_root / "Launcher" / "requirements.txt"
    lib_path = project_root / "Lib"

    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"Project: {project_root}")

    results = []

    # Test built-ins
    for module in ["tkinter", "sqlite3", "ssl", "ctypes", "multiprocessing"]:
        success, error = try_import(module)
        results.append(ImportResult(module, success, error, "builtin"))

    # Test requirements.txt
    for package in parse_requirements(requirements_path):
        if package.lower() in SKIP_PACKAGES:
            continue
        success, error = try_import_any(get_import_names_for_package(package))
        results.append(ImportResult(package, success, error, "requirements"))

    # Test Lib/ modules
    lib_str = str(lib_path)
    if lib_str not in sys.path:
        sys.path.insert(0, lib_str)

    for module in discover_lib_modules(lib_path):
        success, error = try_import(module)
        if not success and error and "No module named 'Lib." in error:
            error += " [BUG: Use relative imports, not 'from Lib.X']"
        results.append(ImportResult(module, success, error, "lib"))

    # Print results
    passed = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    print(f"\n[PASS] ({len(passed)}): ", end="")
    print(", ".join(r.name for r in passed))

    if failed:
        print(f"\n[FAIL] ({len(failed)}):")
        for r in failed:
            print(f"  - {r.name}: {r.error}")
        print(f"\n>>> RESULT: {len(failed)} MISSING - not ready <<<")
    else:
        print(f"\n>>> RESULT: ALL {len(results)} IMPORTS OK <<<")

    return len(failed)


# =============================================================================
# Multi-Python Testing
# =============================================================================

def discover_winpython_installations(project_root: Path) -> list[Path]:
    """Find all WinPython installations."""
    winpython_dir = project_root / "WinPython"
    if not winpython_dir.exists():
        return []

    pythons = []
    for python_exe in winpython_dir.glob("**/python.exe"):
        if "Scripts" not in str(python_exe):
            pythons.append(python_exe)
    return sorted(set(pythons))


def get_python_version(python_exe: Path) -> str:
    """Get Python version string."""
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    try:
        result = subprocess.run(
            [str(python_exe), "--version"],
            capture_output=True, text=True, timeout=10,
            startupinfo=startupinfo
        )
        return result.stdout.strip() or result.stderr.strip()
    except Exception as e:
        return f"Error: {e}"


def run_multi_python_tests(project_root: Path, pythons: list[Path]) -> int:
    """Run import tests with multiple Python versions."""
    this_script = Path(__file__).resolve()
    results = []  # (version, returncode, missing_modules)

    # Hide console window on Windows
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    print("=" * 60)
    print(" MULTI-PYTHON IMPORT TEST")
    print("=" * 60)

    for python_exe in pythons:
        version = get_python_version(python_exe)
        print(f"\n{'-' * 60}")
        print(f"{version} ({python_exe.parent.name})")
        print("-" * 60)

        try:
            result = subprocess.run(
                [str(python_exe), str(this_script), "--quick"],
                capture_output=True, text=True, timeout=120,
                startupinfo=startupinfo
            )
            print(result.stdout)
            if result.stderr:
                print(f"STDERR: {result.stderr}")

            # Extract missing modules from output
            missing = []
            for line in result.stdout.split("\n"):
                if line.strip().startswith("- ") and ":" in line:
                    module = line.strip()[2:].split(":")[0]
                    missing.append(module)

            results.append((version, result.returncode, missing))
        except Exception as e:
            print(f"Error: {e}")
            results.append((version, -1, ["(test failed)"]))

    # Summary
    print(f"\n{'=' * 60}")
    print(" SUMMARY")
    print("=" * 60)
    for version, code, missing in results:
        if code == 0:
            print(f"  [PASS] {version}")
        else:
            print(f"  [FAIL] {version} - missing: {', '.join(missing)}")

    passed = sum(1 for _, code, _ in results if code == 0)
    total = len(results)
    print(f"\n{passed}/{total} Python versions ready")

    # Return 0 so launcher doesn't show error (we've already reported issues above)
    return 0


# =============================================================================
# Main
# =============================================================================

def main():
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent

    # Check for command-line args
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(description="Test that all project dependencies can be imported")
        parser.add_argument("--discover", action="store_true", help="Test all WinPython versions")
        parser.add_argument("--list", action="store_true", help="List discovered WinPython versions")
        parser.add_argument("--quick", action="store_true", help="Run test immediately (no menu)")
        args = parser.parse_args()

        if args.quick:
            return run_import_tests(project_root)

        if args.list:
            pythons = discover_winpython_installations(project_root)
            print("Discovered Python installations:")
            for p in pythons:
                print(f"  {get_python_version(p)} - {p}")
            return 0

        if args.discover:
            pythons = discover_winpython_installations(project_root)
            if not pythons:
                print("No WinPython installations found")
                return 1
            return run_multi_python_tests(project_root, pythons)

    # Interactive menu when run without args
    while True:
        print("=" * 50)
        print(" Import Checker")
        print("=" * 50)
        print("\n1. Test current Python (quick check)")
        print("2. Test all WinPython versions")
        print("3. List available WinPython versions")
        print()

        raw = input("Select option [1]: ")
        # Filter to only digits (launcher may send control characters)
        choice = ''.join(c for c in raw if c.isdigit()) or "1"
        choice = choice[0]

        if choice == "3":
            # List pythons and loop back to menu
            pythons = discover_winpython_installations(project_root)
            print("\nDiscovered Python installations:")
            for p in pythons:
                print(f"  {get_python_version(p)} - {p}")
            print()
            continue

        # Options 1 and 2 run and exit
        print(f"\nRunning option {choice}...\n")

        if choice == "2":
            pythons = discover_winpython_installations(project_root)
            if not pythons:
                print("No WinPython installations found")
                return 1
            return run_multi_python_tests(project_root, pythons)
        else:
            return run_import_tests(project_root)


if __name__ == "__main__":
    sys.exit(main())
