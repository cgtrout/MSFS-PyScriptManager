import time
import psutil
import cProfile
import pstats
import tkinter as tk
from io import StringIO

class TkProfiler:
    def __init__(self, root, interval=200, start_thresh=0.25, end_thresh=0.1,
                 min_profiling_time=6.0, sort_option='cumulative'):
        """
        Initializes the CPUProfiler class.

        :param root: Tkinter root window
        :param interval: Interval (in milliseconds) for checking CPU usage
        :param start_thresh: CPU usage threshold to start profiling
        :param end_thresh: CPU usage threshold to stop profiling
        """
        self.root = root
        self.interval = interval  # Check CPU usage every X ms
        self.start_thresh = start_thresh
        self.end_thresh = end_thresh
        self.min_profiling_time = min_profiling_time
        self.sort_option = sort_option
        self.profiling_active = False
        self.profiler = None
        self.start_time = None  # Tracks when profiling started

        self.process = psutil.Process()  # Get current process
        self.process.cpu_percent(interval=None)  # Warm-up to avoid first-time 0% reading

        print("INIT")

        self.schedule_check()

    def check_cpu(self):
        """Checks the CPU usage of the current process and manages profiling."""
        cpu_usage = self.process.cpu_percent(interval=0.0)

        if cpu_usage > self.start_thresh and not self.profiling_active:
            self.start_profiling(cpu_usage)
        elif self.profiling_active:
            elapsed_time = time.time() - self.start_time  # Time since profiling started
            if cpu_usage < self.end_thresh and elapsed_time >= self.min_profiling_time:
                self.stop_profiling(cpu_usage)

        # Schedule the next check
        self.schedule_check()

    def start_profiling(self, cpu_usage):
        """Starts the profiler."""
        print("CPU spike detected in this process, starting profiler...")
        print(f"CPU Use is {cpu_usage}")
        self.profiler = cProfile.Profile()
        self.profiler.enable()
        self.profiling_active = True
        self.start_time = time.time()  # Record start time

    def stop_profiling(self, cpu_usage):
        """Stops the profiler and prints the first 20 lines of results."""
        if self.profiler:
            self.profiler.disable()
            print("CPU usage normalized in this process, stopping profiler...")
            print(f"cpu_usage={cpu_usage}")

            # Capture stats in a string buffer
            output = StringIO()
            stats = pstats.Stats(self.profiler, stream=output)
            stats.strip_dirs().sort_stats(self.sort_option).print_stats(20)

            print(output.getvalue())  # Print results
            output.close()

        self.profiling_active = False

    def schedule_check(self):
        """Schedules the next CPU check."""
        self.root.after(self.interval, self.check_cpu)

