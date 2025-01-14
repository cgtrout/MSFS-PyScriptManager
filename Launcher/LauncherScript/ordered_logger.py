import logging
import threading
import time
from queue import PriorityQueue, Empty


class OrderedLogger:
    """Ensures logs are written in chronological order and writes only to a file."""
    def __init__(self, filename, level=logging.DEBUG, log_format=None):
        self.log_queue = PriorityQueue()
        self.logger = logging.getLogger("OrderedLogger")
        self.logger.setLevel(level)

        # Sequence number for tie-breaking
        self.sequence_number = 0
        self.sequence_lock = threading.Lock()

        # Set up a file handler
        handler = logging.FileHandler(filename, mode="w")
        log_format = log_format or "%(asctime)s - %(levelname)s - %(message)s"
        formatter = logging.Formatter(log_format)
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        # Event for stopping the processing thread
        self._stop_event = threading.Event()

        # Thread for processing log messages in order
        self.processor_thread = threading.Thread(target=self._process_logs, daemon=True)
        self.processor_thread.start()

    def _get_sequence_number(self):
        """Generate a unique sequence number for tie-breaking."""
        with self.sequence_lock:
            self.sequence_number += 1
            return self.sequence_number

    def _process_logs(self):
        """Process logs in order by timestamp."""
        while not self._stop_event.is_set() or not self.log_queue.empty():
            try:
                # Unpack all six elements
                _, _, level, message, args, kwargs = self.log_queue.get(timeout=0.5)
                # Emit the log using the encapsulated logger
                self._emit_log(level, message, args, kwargs)
                self.log_queue.task_done()
            except Empty:
                continue
            except Exception as e:
                self.logger.exception("Unexpected error in log processor")

    def _emit_log(self, level, message, args, kwargs):
        """Emit a log message through the encapsulated logger."""
        if level.lower() not in ["debug", "info", "warning", "error", "critical"]:
            raise ValueError(f"Invalid log level: {level}")

        log_method = getattr(self.logger, level.lower())
        log_method(message, *args, **kwargs)

    def log(self, level, message, *args, **kwargs):
        """Add a log message to the queue with optional formatting."""
        timestamp = time.monotonic()
        sequence_number = self._get_sequence_number()
        # Pass the message and arguments into the queue
        self.log_queue.put((timestamp, sequence_number, level, message, args, kwargs))

    def info(self, message, *args, **kwargs):
        """High-level method for info logs."""
        self.log("info", message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """High-level method for debug logs."""
        self.log("debug", message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """High-level method for warning logs."""
        self.log("warning", message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """High-level method for error logs."""
        self.log("error", message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        """High-level method for critical logs."""
        self.log("critical", message, *args, **kwargs)

    def stop(self, drain=True):
        """Stop the processor thread. Optionally drain the queue before stopping."""
        if drain:
            self.log_queue.join()  # Wait until all tasks are processed
        self._stop_event.set()
        self.processor_thread.join()


# Test
if __name__ == "__main__":
    logger = OrderedLogger("ordered_logs.log")
    logger.info("This is an info message.")
    logger.error("This is an error message.")
    logger.debug("Debugging: {}", 123)
    time.sleep(1)  # Allow logs to process
    logger.stop()
