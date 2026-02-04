# update_checker.py - Update checking functionality for MSFSPyScriptManager

import json
import re
import time
from typing import Any, TypedDict

import requests

from config import version_file_path, update_cache_path


class ReleaseInfo(TypedDict):
    tag_name: str
    html_url: str


def read_app_version() -> str:
    """Read application version from Launcher/version.txt."""
    if not version_file_path.exists():
        print(f"[WARNING] Version file not found at {version_file_path}. Using 0.0.0.")
        return "0.0.0"
    try:
        return version_file_path.read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception as e:
        print(f"[WARNING] Failed to read version file: {e}. Using 0.0.0.")
        return "0.0.0"


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Extract numeric components from a version string for comparison."""
    cleaned = version_str.strip()
    numbers = re.findall(r"\d+", cleaned)
    return tuple(int(n) for n in numbers)


def _format_version_numbers(numbers: tuple[int, ...]) -> str:
    """Format numeric version tuple into a dotted string."""
    if not numbers:
        return ""
    return ".".join(str(n) for n in numbers)


def is_newer_version(latest: str, current: str) -> bool:
    """
    Return True if latest > current.
    Prefer numeric comparison when possible, otherwise fall back to string equality.
    """
    latest_clean = latest.strip()
    current_clean = current.strip()

    latest_parsed = _parse_version(latest_clean)
    current_parsed = _parse_version(current_clean)

    if latest_parsed or current_parsed:
        return latest_parsed > current_parsed

    return latest_clean != current_clean


def load_update_cache() -> dict[str, Any]:
    """Load update cache (last_check)."""
    if not update_cache_path.exists():
        return {}
    try:
        return json.loads(update_cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_update_cache(cache: dict[str, Any]) -> None:
    """Save update cache to disk."""
    try:
        update_cache_path.parent.mkdir(parents=True, exist_ok=True)
        update_cache_path.write_text(json.dumps(cache), encoding="utf-8")
    except Exception as e:
        print(f"[WARNING] Failed to write update cache: {e}")


def should_check_updates(cache: dict[str, Any], interval_seconds: float) -> bool:
    """Check if enough time has passed since last update check."""
    last_check = cache.get("last_check", 0)
    return (time.time() - last_check) > interval_seconds


def fetch_latest_release(owner: str, repo: str, timeout: int = 3) -> ReleaseInfo:
    """Fetch latest release info from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return {
        "tag_name": data.get("tag_name", ""),
        "html_url": data.get("html_url", "")
    }
