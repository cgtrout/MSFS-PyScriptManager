# tabs/perf_tab.py - Performance monitoring tab
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Any, ClassVar

import psutil

from .base import Tab
from config import TEXT_WIDGET_BG_COLOR, TEXT_WIDGET_FG_COLOR, TEXT_WIDGET_INSERT_COLOR
from _lib import RingMovingAverage

if TYPE_CHECKING:
    from process_tracker import ProcessTracker


class PerfTab(Tab):
    """PerfTab - represents performance tab for monitoring performance of scripts"""

    REFRESH_RATE_MS: ClassVar[int] = 50
    MA_WINDOW_SEC: ClassVar[int] = 2
    CALCULATED_MA_WINDOW: ClassVar[int] = int((MA_WINDOW_SEC * 1000) / REFRESH_RATE_MS)

    def __init__(self, title: str, process_tracker: ProcessTracker) -> None:
        super().__init__(title)
        self.process_tracker: ProcessTracker = process_tracker
        self.performance_metrics_open: bool = True
        self.text_widget: tk.Text | None = None
        self.cpu_stats: dict[int, dict[str, Any]] = {}
        self.process_objects: dict[int, psutil.Process] = {}

    def build_content(self) -> None:
        """Add widgets to the performance tab."""
        self.text_widget = tk.Text(
            self.frame, wrap="word",
            bg=TEXT_WIDGET_BG_COLOR, fg=TEXT_WIDGET_FG_COLOR,
            insertbackground=TEXT_WIDGET_INSERT_COLOR
        )
        self.text_widget.pack(expand=True, fill="both")
        self.start_monitoring()

    def start_monitoring(self) -> None:
        """Start monitoring performance metrics"""
        if not self.performance_metrics_open:
            return

        # Update metrics
        metrics_text: str = self.generate_metrics_text()
        self.refresh_performance_metrics(metrics_text)

        # Schedule the next update
        assert self.frame is not None
        self.frame.after(self.REFRESH_RATE_MS, self.start_monitoring)

    def refresh_performance_metrics(self, text: str) -> None:
        """Refresh the performance metrics text widget."""
        if self.text_widget and self.text_widget.winfo_exists():
            current_yview: tuple[float, float] = self.text_widget.yview()  # Store current scroll position

            # Replace all text but keep scroll position
            self.text_widget.delete("1.0", tk.END)  # Clear old content
            self.text_widget.insert("1.0", text)  # Insert new content at top

            # Restore previous scroll position
            self.text_widget.yview_moveto(current_yview[0])

    def generate_metrics_text(self) -> str:
        """Generate a text representation of performance metrics."""
        metrics: list[str] = []
        processes = self.process_tracker.list_processes()

        if not processes:
            return "No scripts are currently running."

        # Ensure cpu_stats exists for tracking cumulative CPU stats
        if not hasattr(self, 'cpu_stats'):
            self.cpu_stats = {}

        for tab_id, process_info in processes.items():
            process = process_info.get("process")
            script_name: str = process_info.get("script_name", "Unknown")

            if process and process.pid:
                try:
                    # Reuse existing process object if available, else create a new one
                    if tab_id not in self.process_objects:
                        self.process_objects[tab_id] = psutil.Process(process.pid)

                    proc: psutil.Process = self.process_objects[tab_id]

                    if proc.is_running():
                        # Initialize stats for new processes
                        if tab_id not in self.cpu_stats:
                            self.cpu_stats[tab_id] = {
                                "cumulative_cpu": 0.0,
                                "count": 0,
                                "short_ma": RingMovingAverage(self.CALCULATED_MA_WINDOW)
                            }

                        # Calculate current CPU usage (non-blocking, reusing process object)
                        cpu_usage: float = proc.cpu_percent(interval=None)
                        memory_usage: float = proc.memory_info().rss / (1024 ** 2)  # Convert to MB

                        # Update cumulative stats
                        self.cpu_stats[tab_id]["cumulative_cpu"] += cpu_usage
                        self.cpu_stats[tab_id]["count"] += 1
                        self.cpu_stats[tab_id]["short_ma"].add(cpu_usage)

                        # Calculate average CPU usage
                        avg_cpu_usage: float = (
                            self.cpu_stats[tab_id]["cumulative_cpu"]
                            / self.cpu_stats[tab_id]["count"]
                        )

                        short_ma: float = self.cpu_stats[tab_id]["short_ma"].get_average()

                        # Add metrics to the output
                        metrics.append(
                            f"Script: {script_name}\n"
                            f"  PID: {process.pid}\n"
                            f"  Current CPU Usage: {short_ma:.2f}%\n"
                            f"  Average CPU Usage: {avg_cpu_usage:.2f}%\n"
                            f"  Memory Usage: {memory_usage:.2f} MB\n"
                        )
                    else:
                        metrics.append(f"Script: {script_name}\n  Status: Not Running\n")
                        if tab_id in self.process_objects:
                            del self.process_objects[tab_id]
                except psutil.NoSuchProcess:
                    metrics.append(f"Script: {script_name}\n  Status: Terminated\n")
                    if tab_id in self.process_objects:
                        del self.process_objects[tab_id]
            else:
                metrics.append(f"Script: {script_name}\n  Status: Not Running\n")

        return "\n".join(metrics)

    def stop_performance_monitoring(self) -> None:
        """Stop monitoring performance metrics."""
        self.performance_metrics_open = False

    def create_metrics_widget(self) -> tk.Text:
        """Create and add a text widget for displaying performance metrics."""
        text_widget: tk.Text = tk.Text(self.frame, wrap="word")
        text_widget.pack(expand=True, fill="both")
        return text_widget
