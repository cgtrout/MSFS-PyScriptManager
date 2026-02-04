# _lib/__init__.py - Internal launcher utilities

from .parse_ansi import AnsiParser
from .ordered_logger import OrderedLogger
from .dependencies import ensure_dependencies

__all__ = [
    'AnsiParser',
    'OrderedLogger',
    'RingMovingAverage',
    'is_shift_held',
    'ensure_dependencies',
]


def __getattr__(name: str):
    if name == "RingMovingAverage":
        from .utils import RingMovingAverage
        return RingMovingAverage
    if name == "is_shift_held":
        from .utils import is_shift_held
        return is_shift_held
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
