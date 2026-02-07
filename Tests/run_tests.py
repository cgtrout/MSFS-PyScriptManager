"""Run all pytest tests. Launched by the 'test' command in the Launcher console."""
import sys
from pathlib import Path

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

# Pass through any extra args (e.g. -k, --tb, etc.)
args = ["Tests/", "-v"] + sys.argv[1:]
sys.exit(pytest.main(args))
