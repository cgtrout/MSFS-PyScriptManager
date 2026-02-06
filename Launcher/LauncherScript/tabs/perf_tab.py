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
        self._child_proc_cache: dict[int, list[psutil.Process]] = {}  # tab_id -> child procs
        self._cpu_count: int = psutil.cpu_count() or 1

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
        import time

        metrics: list[str] = []
        processes = self.process_tracker.list_processes()

        if not processes:
            # If nothing is running, clear state so we don't leak stats across runs.
            self.cpu_stats.clear()
            self.process_objects.clear()
            self._child_proc_cache.clear()
            return "No scripts are currently running."

        active_tab_ids = set(processes.keys())

        # Cleanup tabs that disappeared from the tracker
        for tab_id in list(self.process_objects.keys()):
            if tab_id not in active_tab_ids:
                self.process_objects.pop(tab_id, None)
                self.cpu_stats.pop(tab_id, None)
                self._child_proc_cache.pop(tab_id, None)

        for tab_id, process_info in processes.items():
            process = process_info.get("process")
            script_name: str = process_info.get("script_name", "Unknown")

            if not process or not process.pid:
                metrics.append(f"Script: {script_name}\n  Status: Not Running\n")
                # Ensure stale state doesn't linger
                self.process_objects.pop(tab_id, None)
                self.cpu_stats.pop(tab_id, None)
                self._child_proc_cache.pop(tab_id, None)
                continue

            pid = process.pid

            try:
                # (Re)create process object if needed or if PID changed under same tab_id
                proc = self.process_objects.get(tab_id)
                if proc is None or proc.pid != pid:
                    proc = psutil.Process(pid)
                    self.process_objects[tab_id] = proc

                    # Prime cpu_percent so the next sample is meaningful
                    proc.cpu_percent(interval=None)
                    self._prime_children(tab_id, proc)

                    self.cpu_stats[tab_id] = {
                        "pid": pid,
                        "cpu_sum_weighted": 0.0,   # sum(cpu% * dt)
                        "dt_sum": 0.0,             # sum(dt)
                        "last_ts": time.monotonic(),
                        "short_ma": RingMovingAverage(self.CALCULATED_MA_WINDOW),
                    }

                if not proc.is_running():
                    metrics.append(f"Script: {script_name}\n  Status: Not Running\n")
                    self.process_objects.pop(tab_id, None)
                    self.cpu_stats.pop(tab_id, None)
                    self._child_proc_cache.pop(tab_id, None)
                    continue

                # Sample
                now = time.monotonic()
                stats = self.cpu_stats.get(tab_id)
                if stats is None:
                    # Shouldn't happen, but keep it consistent if state got out of sync.
                    proc.cpu_percent(interval=None)
                    self.cpu_stats[tab_id] = {
                        "pid": pid,
                        "cpu_sum_weighted": 0.0,
                        "dt_sum": 0.0,
                        "last_ts": now,
                        "short_ma": RingMovingAverage(self.CALCULATED_MA_WINDOW),
                    }
                    stats = self.cpu_stats[tab_id]

                dt = max(0.0, now - float(stats["last_ts"]))
                stats["last_ts"] = now

                cpu_raw, memory_bytes = self._sample_process_tree(tab_id, proc)
                cpu_usage: float = cpu_raw / self._cpu_count
                memory_usage: float = memory_bytes / (1024 ** 2)  # MB

                # Update moving average (smoothed "recent" CPU)
                stats["short_ma"].add(cpu_usage)
                short_ma: float = stats["short_ma"].get_average()

                # Time-weighted average CPU (handles timer drift)
                if dt > 0.0:
                    stats["cpu_sum_weighted"] += cpu_usage * dt
                    stats["dt_sum"] += dt

                avg_cpu_usage: float = (
                    (stats["cpu_sum_weighted"] / stats["dt_sum"]) if stats["dt_sum"] > 0.0 else 0.0
                )

                metrics.append(
                    f"Script: {script_name}\n"
                    f"  PID: {pid}\n"
                    f"  Recent CPU Usage (smoothed): {short_ma:.2f}%\n"
                    f"  Average CPU Usage: {avg_cpu_usage:.2f}%\n"
                    f"  Memory Usage: {memory_usage:.2f} MB\n"
                )

            except psutil.NoSuchProcess:
                metrics.append(f"Script: {script_name}\n  Status: Terminated\n")
                self.process_objects.pop(tab_id, None)
                self.cpu_stats.pop(tab_id, None)
                self._child_proc_cache.pop(tab_id, None)

        return "\n".join(metrics)


    def _prime_children(self, tab_id: int, proc: psutil.Process) -> None:
        """Prime cpu_percent on all current child processes."""
        children: list[psutil.Process] = []
        try:
            for child in proc.children(recursive=True):
                try:
                    child.cpu_percent(interval=None)
                    children.append(child)
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
        self._child_proc_cache[tab_id] = children

    def _sample_process_tree(self, tab_id: int, proc: psutil.Process) -> tuple[float, int]:
        """Sample CPU and memory for a process and all its children.

        Returns (total_cpu_percent_raw, total_memory_bytes).
        """
        cpu_total: float = proc.cpu_percent(interval=None)
        mem_total: int = proc.memory_info().rss

        # Refresh the child PID list (children can spawn/exit)
        try:
            current_child_pids = {c.pid for c in proc.children(recursive=True)}
        except psutil.NoSuchProcess:
            current_child_pids = set()

        # Build PID -> cached Process object map (these have primed cpu_percent state)
        cached = self._child_proc_cache.get(tab_id, [])
        cached_by_pid: dict[int, psutil.Process] = {c.pid: c for c in cached}

        live_children: list[psutil.Process] = []
        for child_pid in current_child_pids:
            try:
                if child_pid in cached_by_pid:
                    # Reuse the cached object so cpu_percent has prior state
                    child = cached_by_pid[child_pid]
                    cpu_total += child.cpu_percent(interval=None)
                else:
                    # New child — prime it, CPU will count from next tick
                    child = psutil.Process(child_pid)
                    child.cpu_percent(interval=None)
                mem_total += child.memory_info().rss
                live_children.append(child)
            except psutil.NoSuchProcess:
                pass

        self._child_proc_cache[tab_id] = live_children
        return cpu_total, mem_total

    def stop_performance_monitoring(self) -> None:
        """Stop monitoring performance metrics."""
        self.performance_metrics_open = False

    def create_metrics_widget(self) -> tk.Text:
        """Create and add a text widget for displaying performance metrics."""
        text_widget: tk.Text = tk.Text(self.frame, wrap="word")
        text_widget.pack(expand=True, fill="both")
        return text_widget
