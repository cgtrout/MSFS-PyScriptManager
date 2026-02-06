from __future__ import annotations

import os
from pathlib import Path


def prepend_pythonpath(env: dict[str, str], path: str | Path) -> bool:
    """
    Prepend `path` to PYTHONPATH in `env` if not already present.
    Returns True when the environment was modified.
    """
    normalized_path = str(Path(path).resolve())
    sep = os.pathsep
    existing = env.get("PYTHONPATH", "")
    entries = [entry for entry in existing.split(sep) if entry]

    if normalized_path in entries:
        return False

    env["PYTHONPATH"] = sep.join([normalized_path, *entries])
    return True
