# Launcher.py - main launcher app script for MSFSPyScriptManager
from __future__ import annotations

print("---Launcher.py STARTING---")

import ctypes
import faulthandler
import logging
import os
import sys
import threading
import time
from multiprocessing import Process, Event, current_process
from multiprocessing.synchronize import Event as MultiprocessingEvent
from pathlib import Path
from typing import IO

# Add parent directory so Lib path can be found
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
from Lib.dark_mode import DarkmodeUtils

from config import logs_path
from _lib import ensure_dependencies, OrderedLogger

# Ensure third-party dependencies are installed
ensure_dependencies()

import keyboard
from ttkthemes import ThemedTk
from app import ScriptLauncherApp

# Configure logging globally
shutdown_log_path: Path = logs_path / "shutdown_log.txt"
if current_process().name == "MainProcess":
    try:
        shutdown_log_path.unlink()
    except FileNotFoundError:
        pass

logger: OrderedLogger = OrderedLogger(
    filename=str(shutdown_log_path),
    level=logging.DEBUG,
    log_format="%(asctime)s [%(levelname)s] %(message)s"
)


def monitor_shutdown_pipe(pipe_name: str, shutdown_event: MultiprocessingEvent) -> None:
    """Monitor the named pipe for shutdown signals and heartbeats."""
    logger.info("Monitoring shutdown pipe in subprocess. Pipe: %s", pipe_name)

    HEARTBEAT_TIMEOUT: int = 5  # Timeout in seconds to detect missed heartbeats
    last_heartbeat_time: float = time.time()  # Track the last heartbeat time

    def pipe_reader() -> None:
            """Threaded pipe reader."""
            nonlocal last_heartbeat_time
            try:
                with open(pipe_name, "r", encoding="utf-8") as pipe:
                    logger.info("Successfully connected to the shutdown pipe.")
                    while not shutdown_event.is_set():
                        try:
                            # Read line from pipe (blocking)
                            line: str = pipe.readline().strip()
                            if line:
                                if line == "shutdown":
                                    logger.info("Shutdown signal received in subprocess.")
                                    shutdown_event.set()
                                    break
                                elif line == "HEARTBEAT":
                                    last_heartbeat_time = time.time()  # Update last heartbeat time
                        except Exception as e:
                            logger.error("Exception while reading pipe: %s", e)
                            break

                        # Sleep briefly to prevent tight loop
                        time.sleep(0.1)
            except Exception as e:
                logger.error("Failed to monitor shutdown pipe: %s", e)
            finally:
                logger.info("Exiting pipe_reader thread.")

    # Start the reader thread
    reader_thread: threading.Thread = threading.Thread(target=pipe_reader, daemon=True)
    reader_thread.start()

    # Wait for shutdown event while pipe read runs in thread
    while not shutdown_event.is_set():
        # Check for heartbeat timeout
        if time.time() - last_heartbeat_time > HEARTBEAT_TIMEOUT:
            logger.info("!=================== Heartbeat timeout detected ===================!")
            shutdown_event.set()
            break
        time.sleep(0.5)

    logger.debug("join reader_thread")
    reader_thread.join(timeout=1)  # Allow the thread to exit


def main() -> None:
    """Main entry point for the script."""
    args: list[str] = sys.argv
    logger.debug("args=%s", args)

    # Prime keyboard module
    # This seems necessary or first hold of shift will not be registered
    # Used for shift-click of "Restart All"
    _ = keyboard.is_pressed("shift")

    # Parse the --shutdown-pipe argument
    shutdown_pipe: str | None = None
    if "--shutdown-pipe" in args:
        shutdown_pipe = args[args.index("--shutdown-pipe") + 1]
        logger.debug("shutdown_pipe=%s", shutdown_pipe)
    else:
        logger.info("No --shutdown-pipe argument provided. Skipping pipe-based shutdown logic.")

    # Add lib_path to PYTHONPATH
    lib_path: str = str((Path(__file__).resolve().parents[1] / "Lib").resolve())
    if lib_path not in os.environ.get("PYTHONPATH", "").split(";"):
        os.environ["PYTHONPATH"] = f"{lib_path};{os.environ.get('PYTHONPATH', '')}"
        logger.info(f"Added '{lib_path}' to PYTHONPATH.")

    logger.info("Starting the application.")

    print("Starting Launcher.py -- main()")

    # Set AppUserModelID before creating the root window (affects taskbar icon)
    if sys.platform.startswith("win"):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "MSFS.PyScriptManager"
            )
        except Exception:
            pass

    # Create shutdown event BEFORE GUI initialization
    shutdown_event: MultiprocessingEvent = Event()

    # Start the shutdown monitoring subprocess IMMEDIATELY if a pipe is provided
    # This allows the C launcher to proceed without waiting for GUI initialization
    monitor_process: Process | None = None
    if shutdown_pipe:
        monitor_process = Process(target=monitor_shutdown_pipe,
                                  args=(shutdown_pipe, shutdown_event))
        monitor_process.start()
        logger.info("Started shutdown monitoring process.")

    # Start app
    root: ThemedTk = ThemedTk(theme="black")
    app: ScriptLauncherApp = ScriptLauncherApp(root, shutdown_event=shutdown_event)

    # Add fault handler
    faulthandler.enable()
    traceback_log_file: IO[str] = open(logs_path / "Launcher.log", "w")
    def reset_traceback_timer() -> None:
        """Reset the faulthandler timer to prevent a dump."""
        faulthandler.dump_traceback_later(15, file=traceback_log_file, exit=True)
        root.after(5000, reset_traceback_timer)

    #reset_traceback_timer()

    try:
        # Periodically check for the shutdown_event
        def check_shutdown() -> None:
            if app.shutdown_event.is_set():
                logger.info("Shutdown event detected in main application.")
                app.on_close()
                return
            root.after(100, check_shutdown)  # Recheck every 100ms

        # Start monitoring shutdown_event
        root.after(100, check_shutdown)
        DarkmodeUtils.apply_dark_mode(root)

        app.start()
        root.mainloop()

        logger.info("Tkinter main loop has exited.")
    finally:
        logger.info("Finalizing application shutdown...")

        # Ensure subprocess cleanup
        if monitor_process:
            app.shutdown_event.set()  # Ensure the subprocess knows to exit
            logger.debug("Waiting for shutdown monitoring process to exit...")
            monitor_process.join(timeout=5)
            logger.debug("Past monitor_process join")
            if monitor_process.is_alive():
                logger.warning("Forcibly terminating the shutdown monitoring process.")
                monitor_process.terminate()

        logger.info("Application closed successfully.")
        logger.stop()

if __name__ == "__main__":
    main()
