"""
connection_helpers.py: reusable connection helpers for simulator libraries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional
import time

from SimConnect import SimConnect, AircraftRequests

from Lib.color_print import print_debug, print_error, print_info
from Lib.sim_process import is_sim_running, wait_for_sim_running


class BaseConnectionHelper(ABC):
    """Common interface for simulator connection helpers."""

    @abstractmethod
    def connect(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """Attempt to connect. Returns True if connected."""

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect and release resources."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if connected and healthy."""

    @abstractmethod
    def get_requests(self):
        """Return the request handler if connected."""


class SimConnectConnectionHelper(BaseConnectionHelper):
    """Basic SimConnect connection with retry support."""

    def __init__(
        self,
        retry_delay: float = 5.0,
        min_runtime: int = 120,
        request_time: int = 1,
        request_attempts: int = 2,
        prime_callback: Optional[Callable[[AircraftRequests], None]] = None,
    ):
        self.retry_delay = retry_delay
        self.min_runtime = min_runtime
        self.request_time = request_time
        self.request_attempts = request_attempts
        self.prime_callback = prime_callback

        self.sm: Optional[SimConnect] = None
        self.aq: Optional[AircraftRequests] = None

    def connect(self, blocking: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Attempt to connect. If blocking, retry until connected or timeout.
        """
        if not blocking:
            if not is_sim_running(min_runtime=self.min_runtime):
                print_info("Sim not running; skipping non-blocking SimConnect attempt.")
                return False
            return self._try_connect_once()

        start = time.monotonic()
        while True:
            if timeout is not None and (time.monotonic() - start) >= timeout:
                return False

            if not wait_for_sim_running(
                min_runtime=self.min_runtime,
                timeout=self.retry_delay,
                interval=self.retry_delay,
            ):
                print_info(
                    f"Flight Simulator not detected yet. Retrying in {self.retry_delay} seconds..."
                )
                continue

            if self._try_connect_once():
                return True

            print_info(f"SimConnect connect failed. Retrying in {self.retry_delay} seconds...")
            time.sleep(self.retry_delay)

    def _try_connect_once(self) -> bool:
        try:
            print_info("Attempting to connect to SimConnect...")
            self.sm = SimConnect()
            self.aq = AircraftRequests(self.sm, _time=self.request_time, _attemps=self.request_attempts)

            if self.prime_callback is not None:
                self.prime_callback(self.aq)

            print_info("SimConnect connection established.")
            return True
        except Exception as exc:  # pylint: disable=broad-except
            print_error(f"SimConnect initialization failed: {exc}")
            self.sm = None
            self.aq = None
            return False

    def disconnect(self) -> None:
        if self.sm is not None:
            try:
                if hasattr(self.sm, "close"):
                    self.sm.close()
            except Exception as exc:  # pylint: disable=broad-except
                print_debug(f"SimConnect close failed: {exc}")
        self.sm = None
        self.aq = None

    def is_connected(self) -> bool:
        if self.sm is None or self.aq is None:
            return False
        if hasattr(self.sm, "ok"):
            return bool(self.sm.ok)
        return True

    def get_requests(self):
        if self.aq is None:
            raise RuntimeError("SimConnect not connected")
        return self.aq
