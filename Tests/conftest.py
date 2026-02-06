"""Shared pytest configuration for the Tests/ directory."""
import sys
from pathlib import Path

# Project root = parent of Tests/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_SCRIPT = PROJECT_ROOT / "Launcher" / "LauncherScript"

# Ensure project root and launcher script dir are importable
for p in [str(PROJECT_ROOT), str(LAUNCHER_SCRIPT)]:
    if p not in sys.path:
        sys.path.insert(0, p)
