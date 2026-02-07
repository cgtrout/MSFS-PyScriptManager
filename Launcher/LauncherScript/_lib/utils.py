# utils.py - Utility classes and functions for MSFSPyScriptManager

import keyboard
import numpy as np
import numpy.typing as npt


class RingMovingAverage:
    """Used to calculate moving average with ring buffer"""
    def __init__(self, window_size: int) -> None:
        self.window_size: int = window_size
        self.buffer: npt.NDArray[np.float64] = np.zeros(window_size, dtype=float)
        self.index: int = 0
        self.count: int = 0

    def add(self, value: float) -> None:
        """Add to moving average array"""
        self.buffer[self.index] = value
        self.index = (self.index + 1) % self.window_size
        self.count = min(self.count + 1, self.window_size)

    def get_average(self) -> float:
        """Get calculated average"""
        return float(np.mean(self.buffer[:self.count])) if self.count > 0 else 0.0


def is_shift_held() -> bool:
    """Check if Shift key is currently held globally."""
    return keyboard.is_pressed("shift")
