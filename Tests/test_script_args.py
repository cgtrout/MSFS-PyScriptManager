"""Test that sys.argv and project path setup work correctly."""
import sys
from pathlib import Path


def test_argv_is_populated():
    """sys.argv should always be a non-empty list."""
    assert isinstance(sys.argv, list)
    assert len(sys.argv) >= 1


def test_project_root_on_path():
    """Project root should be on sys.path (set by conftest.py)."""
    project_root = str(Path(__file__).resolve().parent.parent)
    assert project_root in sys.path


def test_lib_importable():
    """Lib.color_print should be importable from the project root."""
    from Lib.color_print import print_info
    assert callable(print_info)
