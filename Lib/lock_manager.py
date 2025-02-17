"""lock_manager.py - library for managing file locks with a timeout"""

import tempfile
import time
import threading
import multiprocessing
import os
import unittest
import psutil
from filelock import FileLock, Timeout

class LockAcquisitionError(Exception):
    """Raised when acquiring the initialization lock fails."""

class LockManager:
    """File-based lock manager with a watchdog to prevent deadlocks."""

    def __init__(self, lock_name="library_init.lock", timeout=20, max_runtime=10):
        """
        :param lock_name: Name of the lock file (stored in temp directory).
        :param timeout: Max time (seconds) to wait for acquiring the lock.
        :param max_runtime: Max allowed runtime before watchdog force-releases the lock.
        """
        self.lockfile_path = os.path.join(tempfile.gettempdir(), lock_name)
        self.lock = FileLock(self.lockfile_path, timeout=timeout)
        self.max_runtime = max_runtime
        self.watchdog_thread = None
        self.watchdog_stop_event = threading.Event()
        self.lock_acquired = False

    def _watchdog(self):
        """Monitor execution and force release the lock if it exceeds max_runtime."""
        if not self.watchdog_stop_event.wait(self.max_runtime):
            if self.lock_acquired:
                print(f"[Watchdog] Process {os.getpid()} exceeded {self.max_runtime}s!"
                      "Releasing lock.")
                self.release_lock(watchdog_triggered=True)
                os._exit(1)

    def acquire_lock(self, retried=False):
        """Manually acquire the lock and start watchdog."""
        try:
            self.lock.acquire()
            self.lock_acquired = True
            print(f"Process {os.getpid()} acquired the lock.")

            # Start watchdog thread
            self.watchdog_thread = threading.Thread(target=self._watchdog, daemon=True)
            self.watchdog_thread.start()
        except Timeout:
            print(f"Process {os.getpid()}: acquire_lock timeout.")

            if retried:
                print("Lock still in use or unable to remove")
                raise

            print("Now attempt to remove old lock")

            # Attempt to remove old lock (handles crash case)
            if self.remove_stale_lock(self.lockfile_path):
                print("Timed out lock was removed")
                return self.acquire_lock(retried=True)

            print("acquire_lock: Lock still active. Giving up.")
            raise LockAcquisitionError("Failed to acquire initialization lock after retry.")

    def release_lock(self, watchdog_triggered=False):
        """Manually release the lock and stop watchdog."""
        if self.lock_acquired:
            self.lock.release()
            self.lock_acquired = False
            print(f"Process {os.getpid()} released the lock.")

        # Stop watchdog
        self.watchdog_stop_event.set()
        if self.watchdog_thread and not watchdog_triggered:
            self.watchdog_thread.join()

    @staticmethod
    def remove_stale_lock(lock_path):
        """
        Check if a lock file exists and whether its process is still running- will remove it if it
        is not found to be running
        """
        if not os.path.exists(lock_path):
            return False

        with open(lock_path, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        if not psutil.pid_exists(pid):
            print(f"Removing stale lock (PID {pid} not running).")
            os.remove(lock_path)
            return True

        return False

# Multiprocessing Worker Function (Standalone)
# Used for testing
def worker(process_id, runtime, results_queue):
    """Standalone function for subprocesses."""
    lock = LockManager(timeout=20, max_runtime=10)

    try:
        lock.acquire_lock()
        print(f"[Process {process_id}] Acquired lock.")
        time.sleep(runtime)
        print(f"[Process {process_id}] Released lock.")
        results_queue.put(process_id)  # Store results
    finally:
        lock.release_lock()

# Unit Tests
class TestLockManager(unittest.TestCase):
    """Unit tests for LockManager."""

    def run_multiprocessing_test(self, process_runtimes):
        """Runs a test with multiple independent processes."""
        print(f"\n[TEST] Running: {self._testMethodName}")

        processes = []
        results_queue = multiprocessing.Queue()

        # Start each process
        for i, runtime in enumerate(process_runtimes):
            p = multiprocessing.Process(target=worker, args=(i, runtime, results_queue))
            processes.append(p)
            p.start()

        # Wait for all processes to finish
        for p in processes:
            p.join()

        # Collect results
        results = set()
        while not results_queue.empty():
            results.add(results_queue.get())

        print("Execution Order:", results)
        return results

    def test_ordered_execution(self):
        """Test that non-hanging processes complete execution successfully."""
        expected_processes = {0, 1, 3, 4}  # These should always complete
        process_runtimes = [2, 2, 15, 2, 2]  # Process 2 hangs

        actual_order = self.run_multiprocessing_test(process_runtimes)
        self.assertTrue(
            expected_processes.issubset(actual_order),
            f"Test failed: Missing processes {expected_processes - actual_order}"
        )

    def test_watchdog_kills_hanging_process(self):
        """Test that a hanging process is killed by the watchdog."""
        process_runtimes = [2, 2, 15, 2, 2]
        actual_order = self.run_multiprocessing_test(process_runtimes)

        self.assertNotIn(2, actual_order, "Test failed: Hanging process was not killed.")

    def test_all_processes_run_successfully(self):
        """Test that all processes complete when none hang."""
        process_runtimes = [2, 2, 2, 2, 2]
        actual_order = self.run_multiprocessing_test(process_runtimes)

        self.assertEqual(
            actual_order, {0, 1, 2, 3, 4},
            f"Test failed: Not all processes ran successfully (got {actual_order})"
        )

if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    unittest.main()