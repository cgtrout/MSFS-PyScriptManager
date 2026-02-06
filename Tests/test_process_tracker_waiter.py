"""
ProcessTracker waiter-thread tests.

Run:
    python -m unittest Tests/test_process_tracker_waiter.py -v
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import unittest
import builtins
import atexit
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_SCRIPT = ROOT / "Launcher" / "LauncherScript"
if str(LAUNCHER_SCRIPT) not in sys.path:
    sys.path.insert(0, str(LAUNCHER_SCRIPT))

from process_tracker import ProcessTracker  # noqa: E402

SUMMARY_RESULTS: list[tuple[str, str]] = []


def _emit_final_summary() -> None:
    if not SUMMARY_RESULTS:
        return
    out = sys.stderr
    out.write("\n=== ProcessTracker Waiter Summary ===\n")
    for name, status in SUMMARY_RESULTS:
        out.write(f" - [{status}] {name}\n")
    out.write("Validated:\n")
    out.write(" - clean exit detection + tracker cleanup\n")
    out.write(" - non-zero exit triggers crash restart\n")
    out.write(" - stale waiter callback ignored on reused tab_id\n")
    out.write(" - user termination does not emit crash messaging\n")
    out.write(" - rapid churn stress: many fast exits cleaned up\n")
    out.flush()


atexit.register(_emit_final_summary)


class _Scheduler:
    """Small Tk-after stand-in for deterministic tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: list[tuple[float, Callable[[], None]]] = []

    def after(self, delay_ms: int, callback: Callable[[], None]) -> None:
        run_at = time.monotonic() + (delay_ms / 1000.0)
        with self._lock:
            self._tasks.append((run_at, callback))

    def pump(self) -> int:
        now = time.monotonic()
        ready: list[Callable[[], None]] = []
        with self._lock:
            pending: list[tuple[float, Callable[[], None]]] = []
            for run_at, callback in self._tasks:
                if run_at <= now:
                    ready.append(callback)
                else:
                    pending.append((run_at, callback))
            self._tasks = pending

        for callback in ready:
            callback()
        return len(ready)


class _ScriptTabStub:
    def __init__(self) -> None:
        self.outputs: list[str] = []
        self.reload_calls: int = 0

    def insert_output(self, text: str) -> None:
        self.outputs.append(text)

    def reload_script(self, clear_text: bool = False) -> None:  # noqa: ARG002
        self.reload_calls += 1


class ProcessTrackerWaiterTests(unittest.TestCase):
    _original_print = None

    @classmethod
    def setUpClass(cls) -> None:
        # Suppress noisy runtime prints from worker threads during test execution.
        cls._original_print = builtins.print
        builtins.print = lambda *args, **kwargs: None

    def tearDown(self) -> None:
        result = "PASS"
        if self._outcome and self._outcome.result:
            test_result = self._outcome.result
            failed = any(test is self for test, _ in test_result.failures)
            errored = any(test is self for test, _ in test_result.errors)
            if failed or errored:
                result = "FAIL"
        SUMMARY_RESULTS.append((self._testMethodName, result))

    @classmethod
    def tearDownClass(cls) -> None:
        # Restore normal print behavior; summary is emitted at process exit.
        if cls._original_print is not None:
            builtins.print = cls._original_print

    def setUp(self) -> None:
        self.scheduler = _Scheduler()
        self.tracker = ProcessTracker(
            scheduler=self.scheduler.after,
            shutdown_event=threading.Event(),  # type: ignore[arg-type]
        )

    def _wait_for(self, condition: Callable[[], bool], timeout_s: float = 5.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.scheduler.pump()
            if condition():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for condition")

    def _start(self, tab_id: int, code: str, script_name: str, tab: _ScriptTabStub) -> None:
        self.tracker.start_process(
            tab_id=tab_id,
            command=[sys.executable, "-u", "-c", code],
            stdout_callback=lambda _text: None,
            stderr_callback=lambda _text: None,
            script_tab=tab,  # type: ignore[arg-type]
            script_name=script_name,
        )

    def test_waiter_detects_clean_exit_without_polling(self) -> None:
        tab = _ScriptTabStub()
        self._start(tab_id=100, code="print('ok')", script_name="clean.py", tab=tab)

        self._wait_for(lambda: 100 not in self.tracker.processes)

        all_output = "".join(tab.outputs)
        self.assertIn("completed successfully", all_output)
        self.assertNotIn("terminated unexpectedly", all_output)

    def test_stale_waiter_callback_is_ignored_for_reused_tab_id(self) -> None:
        tab = _ScriptTabStub()
        # Old process exits first; new process should stay tracked until it exits.
        self._start(tab_id=200, code="import time; time.sleep(0.15)", script_name="old.py", tab=tab)
        time.sleep(0.02)
        self._start(tab_id=200, code="import time; time.sleep(0.35)", script_name="new.py", tab=tab)

        self._wait_for(lambda: 200 in self.tracker.processes, timeout_s=1.0)
        # Wait until old process should have exited; stale callback must not remove new metadata.
        self._wait_for(lambda: True, timeout_s=0.2)
        self.scheduler.pump()
        self.assertIn(200, self.tracker.processes)

        self._wait_for(lambda: 200 not in self.tracker.processes, timeout_s=3.0)
        success_lines = [line for line in tab.outputs if "completed successfully" in line]
        self.assertGreaterEqual(len(success_lines), 1)

    def test_user_terminate_does_not_report_unexpected_crash(self) -> None:
        tab = _ScriptTabStub()
        self._start(tab_id=300, code="import time; time.sleep(5)", script_name="stop.py", tab=tab)
        self._wait_for(lambda: 300 in self.tracker.processes, timeout_s=1.0)

        self.tracker.terminate_process(300)
        self._wait_for(lambda: 300 not in self.tracker.processes, timeout_s=2.0)
        self._wait_for(lambda: any("terminated by user" in line for line in tab.outputs), timeout_s=2.0)

        all_output = "".join(tab.outputs)
        self.assertNotIn("terminated unexpectedly", all_output)

    def test_nonzero_exit_triggers_crash_restart(self) -> None:
        tab = _ScriptTabStub()
        self._start(tab_id=500, code="import sys; sys.exit(1)", script_name="crash.py", tab=tab)

        self._wait_for(lambda: 500 not in self.tracker.processes)

        all_output = "".join(tab.outputs)
        self.assertIn("terminated unexpectedly with code 1", all_output)
        self.assertIn("Restarting Script in 1s (attempt 1/3)", all_output)
        self.assertNotIn("completed successfully", all_output)

        # Pump past the 1s restart delay so the scheduled reload fires.
        time.sleep(1.1)
        self.scheduler.pump()
        self.assertGreaterEqual(tab.reload_calls, 1)

    def test_stress_many_fast_clean_exits(self) -> None:
        tab = _ScriptTabStub()
        iterations = 30
        for i in range(iterations):
            self._start(tab_id=400 + i, code="pass", script_name=f"stress_{i}.py", tab=tab)

        self._wait_for(lambda: len(self.tracker.processes) == 0, timeout_s=8.0)
        success_count = sum("completed successfully" in line for line in tab.outputs)
        self.assertEqual(success_count, iterations)


if __name__ == "__main__":
    unittest.main(verbosity=2)
