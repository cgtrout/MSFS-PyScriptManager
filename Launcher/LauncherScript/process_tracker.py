# process_tracker.py - ProcessTracker for managing subprocesses
from __future__ import annotations

import codecs
import logging
import os
import queue
import subprocess
import threading
import time
from multiprocessing.synchronize import Event as MultiprocessingEvent
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable, IO, TypedDict

import psutil

from config import (
    SCRIPT_LOAD_DELAY_MS, FAST_CRASH_THRESHOLD_S,
    MAX_RESTART_ATTEMPTS, RESTART_INITIAL_DELAY_MS, logs_path,
)

if TYPE_CHECKING:
    from tabs.script_tab import ScriptTab

logger: logging.Logger = logging.getLogger(__name__)
logger.propagate = False
PIPE_DEBUG_LOGGING: bool = False  # Set True to write pipe diagnostics to Logs/pipe_debug.log
if PIPE_DEBUG_LOGGING:
    logger.setLevel(logging.DEBUG)
    _pipe_log_handler = logging.FileHandler(str(logs_path / "pipe_debug.log"), mode="w")
    _pipe_log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_pipe_log_handler)


class ProcessMetadata(TypedDict):
    process: subprocess.Popen[str]
    script_name: str
    script_tab: ScriptTab
    stdin_queue: queue.Queue[str | None]
    stop_event: threading.Event


class ProcessInfo(TypedDict):
    process: subprocess.Popen[str]
    script_name: str


class ProcessTracker:
    """Manages runtime of collection of processes"""
    def __init__(self, scheduler: Callable[..., Any], shutdown_event: MultiprocessingEvent) -> None:
        self.processes: dict[int | None, ProcessMetadata] = {}  # Maps tab_id to process metadata
        self.scheduler: Callable[..., Any] = scheduler  # Store the scheduler
        self.script_name: str | None = None
        self.lock: Lock = Lock()
        self.shutdown_event: MultiprocessingEvent = shutdown_event  # Store the shutdown event
        self._restart_state: dict[int | None, dict[str, int | float]] = {}  # Per-tab crash tracking

    def start_process(
        self,
        tab_id: int | None,
        command: list[str],
        stdout_callback: Callable[[str], None],
        stderr_callback: Callable[[str], None],
        script_tab: ScriptTab,
        script_name: str | None = None
    ) -> None:
        """Start a subprocess and manage its I/O."""

        # Add Lib path
        lib_path: str = str((Path(__file__).resolve().parents[1] / "Lib").resolve())
        custom_env: dict[str, str] = os.environ.copy()  # Create a local environment copy
        custom_env["PYTHONPATH"] = f"{lib_path};{custom_env.get('PYTHONPATH', '')}"

        try:
            process: subprocess.Popen[str] = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=custom_env,
            )
            print(f"[INFO] Started process: {script_name}, PID: {process.pid}, Tab ID: {tab_id}")

            self.script_name = script_name
            self._restart_state.setdefault(tab_id, {"crash_count": 0, "start_time": 0.0})
            self._restart_state[tab_id]["start_time"] = time.monotonic()

            # Create stdin queue and stop event
            stdin_queue: queue.Queue[str | None] = queue.Queue(maxsize=1000)
            stop_event: threading.Event = threading.Event()

            with self.lock:
                self.processes[tab_id] = {
                    "process": process,
                    "script_name": script_name or "Unknown",
                    "script_tab": script_tab,
                    "stdin_queue": stdin_queue,
                    "stop_event": stop_event,
                }

            # Warning redirect for pkg_resource warning (pygame)
            # This is a issue present in current version of pygame that hasn't yet been fixed
            warn_followup: dict[str, bool] = {"pending": False}

            def _forward_pkg_resources_warning(line: str) -> None:
                # Emit to launcher.c (stdout) and log, but do not show in script tab.
                print(line, end="")
                logger.warning(line.rstrip("\n"))

            def _stderr_wrapper(text: str) -> None:
                if "pkg_resources is deprecated as an API" in text:
                    warn_followup["pending"] = True
                    _forward_pkg_resources_warning(text)
                    return
                if warn_followup["pending"]:
                    if "from pkg_resources import" in text:
                        _forward_pkg_resources_warning(text)
                        warn_followup["pending"] = False
                        return
                    warn_followup["pending"] = False
                stderr_callback(text)

            # Start threads for stdout and stderr reading.
            # Reader threads schedule callbacks directly via self.scheduler
            # (root.after), eliminating the need for separate dispatcher threads.
            assert process.stdout is not None
            threading.Thread(
                target=self._read_output,
                args=(process.stdout, stdout_callback, stop_event, tab_id, "stdout"),
                daemon=True,
                name=f"StdoutThread-{tab_id}"
            ).start()

            assert process.stderr is not None
            threading.Thread(
                target=self._read_output,
                args=(process.stderr, _stderr_wrapper, stop_event, tab_id, "stderr"),
                daemon=True,
                name=f"StderrThread-{tab_id}"
            ).start()

            # Start a thread for writing to stdin
            assert process.stdin is not None
            threading.Thread(
                target=self._write_input,
                args=(process.stdin, stdin_queue, stop_event, tab_id),
                daemon=True,
                name=f"StdinWriter-{tab_id}"
            ).start()

            # Start process monitoring
            self.schedule_process_check(tab_id)

        except Exception as e:
            print(f"[ERROR] Failed to start process for Tab ID {tab_id}: {e}")


    def _read_output(
        self,
        stream: IO[str],
        callback: Callable[[str], None],
        stop_event: threading.Event,
        tab_id: int | None,
        stream_name: str
    ) -> None:
        """
        Read subprocess output and schedule callbacks directly via self.scheduler.
        Handles lines and partial data (e.g. prompts without trailing newline).
        """
        print(f"[INFO] Starting output reader for {stream_name}, Tab ID: {tab_id}")

        fd: int = stream.fileno()  # Get the file descriptor for low-level reads
        buffer: str = ""  # Accumulate partial lines
        last_flushed_partial: str | None = None  # Track the last flushed partial line
        decoder = codecs.getincrementaldecoder("utf-8")()
        dispatched: int = 0
        logger.debug("reader START  stream=%s tab=%s", stream_name, tab_id)

        try:
            while True:
                try:
                    raw: bytes = os.read(fd, 4096)
                    if not raw:  # EOF
                        # Flush any incomplete multibyte sequence
                        remaining: str = decoder.decode(b"", final=True)
                        if remaining:
                            buffer += remaining
                        logger.debug("reader EOF   stream=%s tab=%s dispatched=%d",
                                     stream_name, tab_id, dispatched)
                        break

                    chunk: str = decoder.decode(raw)
                    buffer += chunk

                    # Process complete lines in the buffer
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        self.scheduler(0, lambda l=line + "\n": callback(l))
                        dispatched += 1
                        last_flushed_partial = None  # Reset partial tracking

                    # Handle partial line (e.g., prompts or incomplete output)
                    if buffer and buffer != last_flushed_partial:
                        self.scheduler(0, lambda l=buffer: callback(l))
                        dispatched += 1
                        last_flushed_partial = buffer
                        buffer = ""

                except BlockingIOError:
                    # No data available yet; pause briefly to avoid busy-waiting
                    time.sleep(0.01)
                except Exception as read_error:
                    # Catch unexpected read errors and log them
                    print(f"[ERROR] Exception while reading {stream_name}: {read_error}")
                    break

        except Exception as loop_error:
            # Log any unexpected errors that terminate the loop
            print(f"[ERROR] Unexpected error in output reader for {stream_name}: {loop_error}")

        finally:
            # Handle cleanup: flush remaining buffer
            if buffer and buffer != last_flushed_partial:
                self.scheduler(0, lambda l=buffer: callback(l))
            logger.debug("reader DONE  stream=%s tab=%s", stream_name, tab_id)

            try:
                stream.close()  # Close the stream gracefully
            except Exception as close_error:
                print(f"[WARNING] Error closing {stream_name}: {close_error}")

            print(f"[INFO] Output reader for {stream_name} finished, Tab ID: {tab_id}")

    def _write_input(
        self,
        stdin: IO[str],
        input_queue: queue.Queue[str | None],
        stop_event: threading.Event,
        tab_id: int | None
    ) -> None:
        """Write input from the queue to the subprocess's stdin."""
        try:
            while not stop_event.is_set():
                try:
                    input_data: str | None = input_queue.get(timeout=1)  # Block until input is available
                    if input_data is None:  # Sentinel for EOF
                        break
                    logger.debug("stdin write: %r", input_data)
                    stdin.write(input_data)
                    stdin.flush()  # Ensure immediate delivery to the subprocess
                except queue.Empty:
                    continue  # Check for stop_event periodically
        except Exception as e:
            print(f"[ERROR] Failed to write to stdin for Tab ID {tab_id}: {e}")
        finally:
            try:
                stdin.close()
            except Exception as e:
                print(f"[WARNING] Failed to close stdin for Tab ID {tab_id}: {e}")

    def schedule_process_check(self, tabid: int | None) -> None:
        """Schedule a periodic check for process termination."""
        self.scheduler(2000, lambda: self.check_termination(tabid))

    def check_termination(self, tab_id: int | None) -> None:
        """Check if the process has terminated and notify the associated ScriptTab."""
        with self.lock:
            metadata = self.processes.get(tab_id)
            if not metadata:
                return  # Process already cleaned up or not found

        process: subprocess.Popen[str] = metadata["process"]
        script_tab: ScriptTab = metadata.get("script_tab")
        script_name: str = metadata.get("script_name", "Unknown")

        if process.poll() is not None:  # Process has stopped
            exit_code: int | None = process.poll()
            logger.debug("check_termination DETECTED tab=%s exit_code=%s",
                         tab_id, exit_code)

            # Notify the ScriptTab directly
            try:
                if script_tab:
                    if exit_code == 0:
                        script_tab.insert_output(f"[INFO] Script '{script_name}' completed successfully.\n")
                        self._restart_state.pop(tab_id, None)
                    else:
                        script_tab.insert_output(f"[ERROR] Script '{script_name}' terminated unexpectedly with code {exit_code}.\n")
                        script_tab.insert_output("\n\n\n\n\n")
                        self._handle_crash_restart(tab_id, script_tab)

                # Signal threads to stop and clean up process metadata
                logger.debug("check_termination SET stop_event tab=%s", tab_id)
                metadata["stop_event"].set()
                with self.lock:
                    self.processes.pop(tab_id, None)
            except Exception as e:
                print(f"[ERROR] Error notifying ScriptTab for Tab ID {tab_id}: {e}")
            return

        # Reschedule the next check
        self.schedule_process_check(tab_id)

    def _handle_crash_restart(self, tab_id: int | None, script_tab: ScriptTab) -> None:
            """Handle auto-restart logic with exponential backoff for fast crashes."""
            state = self._restart_state.get(tab_id, {"crash_count": 0, "start_time": 0.0})
            runtime = time.monotonic() - state.get("start_time", 0.0)

            if runtime >= FAST_CRASH_THRESHOLD_S:
                # Script ran long enough — not a crash loop, restart normally
                state["crash_count"] = 0
                self._restart_state[tab_id] = state
                script_tab.insert_output("Restarting Script..\n")
                self.scheduler(SCRIPT_LOAD_DELAY_MS,
                               lambda: script_tab.reload_script(clear_text=False))
                return

            # Fast crash — apply backoff and retry limit
            state["crash_count"] = state.get("crash_count", 0) + 1
            self._restart_state[tab_id] = state
            crash_count: int = int(state["crash_count"])

            if crash_count > MAX_RESTART_ATTEMPTS:
                script_tab.insert_output(
                    f"[ERROR] Script crashed {MAX_RESTART_ATTEMPTS} times in a row. "
                    f"Auto-restart disabled. Press F5 to retry.\n"
                )
            else:
                delay = RESTART_INITIAL_DELAY_MS * (2 ** (crash_count - 1))
                script_tab.insert_output(
                    f"Restarting Script in {delay / 1000:.0f}s "
                    f"(attempt {crash_count}/{MAX_RESTART_ATTEMPTS})..\n"
                )
                self.scheduler(delay,
                               lambda: script_tab.reload_script(clear_text=False))

    def reset_restart_state(self, tab_id: int | None) -> None:
        """Reset the crash counter for a tab (e.g., on user-initiated reload)."""
        self._restart_state.pop(tab_id, None)

    def terminate_process(self, tab_id: int | None) -> None:
        """Terminate the process for a given tab ID."""
        print(f"[INFO] Attempting to terminate process for Tab ID: {tab_id}")
        logger.info("[INFO] Attempting to terminate process for Tab ID: %s", tab_id)

        # Remove metadata for this tab
        with self.lock:
            metadata = self.processes.pop(tab_id, None)
            if not metadata:
                print(f"[INFO] No process found for Tab ID {tab_id}.")
                return
            process: subprocess.Popen[str] = metadata["process"]

        # Terminate the process if it is still running
        if process.poll() is None:  # Still running
            print(f"[INFO] Terminating process for Tab ID {tab_id} (PID {process.pid}).")
            self.terminate_process_tree(process.pid)

        # Signal threads to stop
        metadata["stop_event"].set()

        # Notify the user via the script tab
        script_tab: ScriptTab = metadata.get("script_tab")
        if script_tab:
            self.scheduler(0, lambda: script_tab.insert_output("[INFO] Process terminated by user.\n"))

        # Close the process's I/O streams
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

        print(f"[INFO] Process for Tab ID {tab_id} terminated.")
        logger.info("[INFO] Process for Tab ID %s terminated.", tab_id)

    @staticmethod
    def terminate_process_tree(pid: int | None, timeout: int = 5, force: bool = True) -> None:
        """Terminate a process tree."""
        print(f"[INFO] Terminating process tree for PID: {pid}")
        logger.info("[INFO] Terminating process tree for PID: %s", pid)
        try:
            parent: psutil.Process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            logger.info(f"Process with PID {pid} already terminated. "
                  "Checking for orphaned children.")
            # Attempt to clean up orphaned child processes
            ProcessTracker.terminate_orphaned_children(pid)
            return
        except Exception as e:
            print(f"[ERROR] Failed to initialize process PID {pid}: {e}")
            return

        try:
            children: list[psutil.Process] = parent.children(recursive=True)
            logger.info(f"Found {len(children)} child processes for PID {pid}."
                  f"Terminating children first.")

            for child in children:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    logger.warning(f"NoSuchProcess {child.pid}.")
                    continue
                except psutil.AccessDenied:
                    logger.warning(f"Access denied to terminate child PID {child.pid}.")

            # Wait for all children to terminate
            _, alive = psutil.wait_procs(children, timeout=timeout)

            if alive and force:
                logger.info(f"[WARNING] {len(alive)} child processes did not terminate. "
                      "Forcing termination.")
                for proc in alive:
                    try:
                        logger.info("proc.kill()")
                        proc.kill()
                    except psutil.NoSuchProcess:
                        logger.warning("NoSuchProcess")
                        continue
                    except psutil.AccessDenied:
                        logger.info(f"[WARNING] Access denied to kill child PID {proc.pid}.")

            # Terminate the parent process
            parent.terminate()
            _, alive = psutil.wait_procs([parent], timeout=timeout)

            if alive and force:
                print(f"[WARNING] Parent process PID {parent.pid} did not terminate. Forcing kill.")
                for proc in alive:
                    try:
                        proc.kill()
                        logger.info("proc.kill()")
                    except psutil.NoSuchProcess:
                        logger.warning("NoSuchProcess")
                        continue
                    except psutil.AccessDenied:
                        logger.warning(f"Access denied to kill PID {proc.pid}.")

        except psutil.NoSuchProcess:
            print(f"[INFO] Parent process PID {pid} already terminated during cleanup.")
        except Exception as e:
            print(f"[ERROR] Unexpected error terminating process tree for PID {pid}: {e}")

    @staticmethod
    def terminate_orphaned_children(parent_pid: int | None) -> None:
        """Terminate orphaned children of a non-existent parent process."""
        try:
            for proc in psutil.process_iter(attrs=["pid", "ppid"]):
                if proc.info["ppid"] == parent_pid:
                    try:
                        proc.terminate()
                        proc.wait(timeout=5)
                    except psutil.NoSuchProcess:
                        continue
                    except Exception as e:
                        print(f"[ERROR] Failed to terminate orphaned child PID"
                              f"{proc.info['pid']}: {e}")
        except Exception as e:
            print(f"[ERROR] Error scanning for orphaned children of PID {parent_pid}: {e}")

    def list_processes(self) -> dict[int, ProcessInfo]:
        """List all tracked processes and their metadata."""
        return {
            tab_id: {
                "process": metadata["process"],
                "script_name": metadata.get("script_name", "Unknown"),
            }
            for tab_id, metadata in self.processes.items()
            if tab_id is not None
        }
