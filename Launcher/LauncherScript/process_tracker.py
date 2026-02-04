# process_tracker.py - ProcessTracker for managing subprocesses

import logging
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from threading import Lock
from typing import Dict

import psutil

from config import SCRIPT_LOAD_DELAY_MS

logger = logging.getLogger(__name__)


class ProcessTracker:
    """Manages runtime of collection of processes"""
    def __init__(self, scheduler, shutdown_event):
        self.processes = {}  # Maps tab_id to process metadata
        self.scheduler = scheduler  # Store the scheduler
        self.script_name = None
        self.queuefull_warning_issued = False
        self.lock = Lock()
        self.shutdown_event = shutdown_event  # Store the shutdown event

    def start_process(self, tab_id, command, stdout_callback, stderr_callback, script_tab, script_name=None):
        """Start a subprocess and manage its I/O."""

        # Add Lib path
        lib_path = str((Path(__file__).resolve().parents[1] / "Lib").resolve())
        custom_env = os.environ.copy()  # Create a local environment copy
        custom_env["PYTHONPATH"] = f"{lib_path};{custom_env.get('PYTHONPATH', '')}"

        try:
            process = subprocess.Popen(
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

            # Create individual queues and stop event
            stdout_queue = queue.Queue(maxsize=1000)
            stderr_queue = queue.Queue(maxsize=1000)
            stdin_queue = queue.Queue(maxsize=1000)
            stop_event = threading.Event()

            with self.lock:
                self.processes[tab_id] = {
                    "process": process,
                    "script_name": script_name or "Unknown",
                    "script_tab": script_tab,
                    "stdout_queue": stdout_queue,
                    "stderr_queue": stderr_queue,
                    "stdin_queue": stdin_queue,
                    "stop_event": stop_event,
                }

            # Start threads for stdout and stderr reading
            threading.Thread(
                target=self._read_output,
                args=(process.stdout, stdout_queue, stop_event, tab_id, "stdout"),
                daemon=True,
                name=f"StdoutThread-{tab_id}"
            ).start()

            threading.Thread(
                target=self._read_output,
                args=(process.stderr, stderr_queue, stop_event, tab_id, "stderr"),
                daemon=True,
                name=f"StderrThread-{tab_id}"
            ).start()

            # Start a thread for writing to stdin
            threading.Thread(
                target=self._write_input,
                args=(process.stdin, stdin_queue, stop_event, tab_id),
                daemon=True,
                name=f"StdinWriter-{tab_id}"
            ).start()

            # Start dispatcher threads to process queues and invoke callbacks
            threading.Thread(
                target=self._dispatch_queue,
                args=(stdout_queue, stdout_callback, stop_event),
                daemon=True,
                name=f"DispatcherStdout-{tab_id}"
            ).start()

            # Warning redirect for pkg_resource warning (pygame)
            # This is a issue present in current version of pygame that hasn't yet been fixed
            warn_followup = {"pending": False}

            def _forward_pkg_resources_warning(line):
                # Emit to launcher.c (stdout) and log, but do not show in script tab.
                print(line, end="")
                logger.warning(line.rstrip("\n"))

            def _stderr_wrapper(text):
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

            threading.Thread(
                target=self._dispatch_queue,
                args=(stderr_queue, _stderr_wrapper, stop_event),
                daemon=True,
                name=f"DispatcherStderr-{tab_id}"
            ).start()

            # Start process monitoring
            self.schedule_process_check(tab_id)

        except Exception as e:
            print(f"[ERROR] Failed to start process for Tab ID {tab_id}: {e}")

    def _read_output(self, stream, output_queue, stop_event, tab_id, stream_name):
        """
        Read subprocess output with proper handling of lines and partial data.
        """
        print(f"[INFO] Starting output reader for {stream_name}, Tab ID: {tab_id}")

        fd = stream.fileno()  # Get the file descriptor for low-level reads
        buffer = ""  # Accumulate partial lines
        last_flushed_partial = None  # Track the last flushed partial line

        try:
            while not stop_event.is_set():
                try:
                    # Attempt to read a chunk of data
                    chunk = os.read(fd, 4096).decode("utf-8")
                    if not chunk:  # EOF or no data available
                        time.sleep(0.01)
                        continue

                    buffer += chunk

                    # Process complete lines in the buffer
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        output_queue.put_nowait(line + "\n")
                        last_flushed_partial = None  # Reset partial tracking

                    # Handle partial line (e.g., prompts or incomplete output)
                    if buffer and buffer != last_flushed_partial:
                        output_queue.put_nowait(buffer)
                        last_flushed_partial = buffer

                        # Clear the buffer after enqueueing partial data
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
            # Handle cleanup: flush remaining buffer and signal end of stream
            if buffer and buffer != last_flushed_partial:
                output_queue.put_nowait(buffer)
            output_queue.put(None)  # Signal end of stream to the queue

            try:
                stream.close()  # Close the stream gracefully
            except Exception as close_error:
                print(f"[WARNING] Error closing {stream_name}: {close_error}")

            print(f"[INFO] Output reader for {stream_name} finished, Tab ID: {tab_id}")

    def _write_input(self, stdin, input_queue, stop_event, tab_id):
        """Write input from the queue to the subprocess's stdin."""
        try:
            while not stop_event.is_set():
                try:
                    input_data = input_queue.get(timeout=1)  # Block until input is available
                    if input_data is None:  # Sentinel for EOF
                        break
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

    def _dispatch_queue(self, q, callback, stop_event):
        """Consume items from the queue and invoke the callback."""
        print("[INFO] Starting dispatcher thread.")
        while True:
            try:
                line = q.get(timeout=1)  # Avoid indefinite blocking
            except queue.Empty:
                # Check if this process's stop_event is set
                if stop_event.is_set():
                    print("[INFO] Dispatcher stopping due to its own stop_event.")
                    logger.debug("Dispatcher stopping due to its own stop_event.")
                    break
                continue

            if line is None:  # Sentinel for end-of-stream
                print("[INFO] Dispatcher received EOF sentinel. Exiting.")
                break

            # Use the provided scheduler to safely invoke the callback
            self.scheduler(0, lambda l=line: callback(l))

    def schedule_process_check(self, tabid):
        """Schedule a periodic check for process termination."""
        self.scheduler(2000, lambda: self.check_termination(tabid))

    def check_termination(self, tab_id):
        """Check if the process has terminated and notify the associated ScriptTab."""
        with self.lock:
            metadata = self.processes.get(tab_id)
            if not metadata:
                return  # Process already cleaned up or not found

        process = metadata["process"]
        script_tab = metadata.get("script_tab")
        script_name = metadata.get("script_name", "Unknown")

        if process.poll() is not None:  # Process has stopped
            exit_code = process.poll()

            # Notify the ScriptTab directly
            try:
                if script_tab:
                    if exit_code == 0:
                        script_tab.insert_output(f"[INFO] Script '{script_name}' completed successfully.\n")
                    else:
                        script_tab.insert_output(f"[ERROR] Script '{script_name}' terminated unexpectedly with code {exit_code}.\n")
                        script_tab.insert_output("\n\n\n\n\n")

                        # AutoRestart on delay in case this is in a crash loop as this will limit
                        # performance impact
                        script_tab.insert_output("Restarting Script..\n")

                        self.scheduler(SCRIPT_LOAD_DELAY_MS,
                                       lambda: script_tab.reload_script(clear_text=False))

                # Clean up process metadata
                with self.lock:
                    self.processes.pop(tab_id, None)
            except Exception as e:
                print(f"[ERROR] Error notifying ScriptTab for Tab ID {tab_id}: {e}")
            return

        # Reschedule the next check
        self.schedule_process_check(tab_id)

    def terminate_process(self, tab_id):
        """Terminate the process for a given tab ID."""
        print(f"[INFO] Attempting to terminate process for Tab ID: {tab_id}")
        logger.info("[INFO] Attempting to terminate process for Tab ID: %s", tab_id)

        # Remove metadata for this tab
        with self.lock:
            metadata = self.processes.pop(tab_id, None)
            if not metadata:
                print(f"[INFO] No process found for Tab ID {tab_id}.")
                return
            process = metadata["process"]

        # Terminate the process if it is still running
        if process.poll() is None:  # Still running
            print(f"[INFO] Terminating process for Tab ID {tab_id} (PID {process.pid}).")
            self.terminate_process_tree(process.pid)

        # Signal threads to stop
        metadata["stop_event"].set()
        metadata["stdout_queue"].put("[INFO] Process terminated by user.\n")
        metadata["stdout_queue"].put(None)  # Final EOF sentinel

        # Close the process's I/O streams
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

        print(f"[INFO] Process for Tab ID {tab_id} terminated.")
        logger.info("[INFO] Process for Tab ID %s terminated.", tab_id)

    @staticmethod
    def terminate_process_tree(pid, timeout=5, force=True):
        """Terminate a process tree."""
        print(f"[INFO] Terminating process tree for PID: {pid}")
        logger.info("[INFO] Terminating process tree for PID: %s", pid)
        try:
            parent = psutil.Process(pid)
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
            children = parent.children(recursive=True)
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
                        logger.warning(f"NoSuchProcess")
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
                        logger.warning(f"NoSuchProcess")
                        continue
                    except psutil.AccessDenied:
                        logger.warning(f"Access denied to kill PID {proc.pid}.")

        except psutil.NoSuchProcess:
            print(f"[INFO] Parent process PID {pid} already terminated during cleanup.")
        except Exception as e:
            print(f"[ERROR] Unexpected error terminating process tree for PID {pid}: {e}")

    @staticmethod
    def terminate_orphaned_children(parent_pid):
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

    def list_processes(self) -> Dict[int, Dict]:
        """List all tracked processes and their metadata."""
        return {
            tab_id: {
                "process": metadata["process"],
                "script_name": metadata.get("script_name", "Unknown"),
            }
            for tab_id, metadata in self.processes.items()
        }
