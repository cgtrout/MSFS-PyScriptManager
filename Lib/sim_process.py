"""
sim_process.py: utilities for detecting MSFS process runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from io import StringIO
import csv
import subprocess
import time

from Lib.color_print import print_debug, print_error, print_info


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        # Expect ISO 8601 from PowerShell (e.g., 2026-02-05T12:34:56.7890000Z)
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _is_sim_running_cim(min_runtime: int) -> bool | None:
    """
    Try using PowerShell CIM query for FlightSimulator*.exe processes.
    Returns True/False if query succeeds, or None if the query fails.
    """
    cmd = (
        'powershell -NoProfile -Command "'
        '$ErrorActionPreference = ''Stop''; '
        'Get-CimInstance Win32_Process -Filter \\"Name like ''FlightSimulator%.exe''\\" | '
        'Select-Object Name,ProcessId,@{n=''CreationDate'';e={$_.CreationDate.ToUniversalTime().ToString(''o'')}} | '
        'ConvertTo-Csv -NoTypeInformation"'
    )
    try:
        raw_output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        print_debug(f"PowerShell CIM query failed: {exc}")
        return None

    output = raw_output.decode(errors="ignore").strip()
    print_debug("\nRaw CIM Output:\n" + output + "\n")
    if not output:
        return False

    now = time.time()
    reader = csv.DictReader(StringIO(output))
    for row in reader:
        name = row.get("Name", "").strip()
        pid = row.get("ProcessId", "").strip()
        creation = row.get("CreationDate", "").strip()

        print_debug(f"Process Found: Name={name}, PID={pid}, CreationDate={creation}")

        if not (name.startswith("FlightSimulator") and pid.isdigit()):
            continue

        start_dt = _parse_iso_datetime(creation)
        if start_dt is None:
            print_error(f"[ERROR] Could not parse creation time: {creation}")
            continue

        start_time = start_dt.timestamp()
        runtime = now - start_time
        print_debug(f"Parsed start time (UTC epoch): {start_time}")
        print_debug(f"Calculated runtime: {runtime:.1f} seconds")

        if runtime >= min_runtime:
            print_info(f"Found MSFS process: {name} (PID: {pid}, Running for {runtime:.1f} sec)")
            return True
        print_info(f"Found {name} (PID: {pid}), but only running for {runtime:.1f} sec (Waiting...)")
        return False

    return False


def _is_sim_running_wmic(min_runtime: int) -> bool:
    """Fallback WMIC implementation (deprecated on newer Windows)."""
    try:
        cmd = (
            'wmic process where "name like \'FlightSimulator%%.exe\'" '
            'get Name,CreationDate,ProcessId /format:csv'
        )
        raw_output = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT)
        output = raw_output.decode(errors="ignore").strip()

        print_debug("\nRaw WMIC Output:\n" + output + "\n")

        if "No Instance(s) Available" in output:
            output = ""

        if output:
            print_debug("MSFS is running")

    except subprocess.CalledProcessError:
        return False

    now = time.time()
    reader = csv.DictReader(StringIO(output))

    for row in reader:
        name = row.get("Name", "").strip()
        creation = row.get("CreationDate", "").strip()
        pid = row.get("ProcessId", "").strip()

        print_debug(f"Process Found: Name={name}, PID={pid}, CreationDate={creation}")

        if not (name.startswith("FlightSimulator") and creation and pid.isdigit()):
            continue

        creation_parts = creation.split(".")
        creation_time_str = creation_parts[0].strip()
        timezone_offset_str = creation_parts[-1].strip()[-4:]

        try:
            print_debug(f"Parsing creation time: {creation_time_str}")
            start_dt = datetime.strptime(creation_time_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)

            if timezone_offset_str.lstrip("+-").isdigit():
                offset_minutes = int(timezone_offset_str)
                offset_seconds = offset_minutes * 60
                start_dt -= timedelta(seconds=offset_seconds)
                print_debug(
                    f"Applying timezone offset: {offset_minutes} minutes ({-offset_seconds} seconds)"
                )

            start_time = start_dt.timestamp()
            print_debug(f"Parsed start time (UTC epoch): {start_time}")
        except ValueError:
            print_error(f"[ERROR] Could not parse creation time: {creation}")
            continue

        runtime = now - start_time
        print_debug(f"Calculated runtime: {runtime:.1f} seconds")

        if runtime >= min_runtime:
            print_info(f"Found MSFS process: {name} (PID: {pid}, Running for {runtime:.1f} sec)")
            return True
        print_info(
            f"Found {name} (PID: {pid}), but only running for {runtime:.1f} sec (Waiting...)"
        )
        return False

    return False


def is_sim_running(min_runtime: int = 120) -> bool:
    """Return True if an MSFS process has been running for at least min_runtime seconds."""
    result = _is_sim_running_cim(min_runtime)
    if result is not None:
        return result
    return _is_sim_running_wmic(min_runtime)


def wait_for_sim_running(
    min_runtime: int = 120,
    timeout: float | None = None,
    interval: float = 5.0,
) -> bool:
    """
    Block until MSFS has been running for min_runtime seconds.
    Returns True when running; False if timeout is reached.
    """
    if timeout is not None and timeout < 0:
        raise ValueError("timeout must be >= 0 or None")
    if interval <= 0:
        raise ValueError("interval must be > 0")

    start = time.monotonic()
    while True:
        if is_sim_running(min_runtime=min_runtime):
            return True

        if timeout is not None and (time.monotonic() - start) >= timeout:
            return False

        time.sleep(interval)
