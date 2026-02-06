"""CPU load calibration test — targets ~25% total CPU usage (as shown in Task Manager).

Spawns worker *processes* (not threads — the GIL blocks parallel CPU-bound threads)
to reach the target system load.
"""
import math
import multiprocessing
import os
import time

TARGET_SYSTEM_PCT = 25.0
CYCLE_PERIOD_S = 0.05  # 50 ms cycle for smooth load


def burn_loop(duty: float) -> None:
    """Busy-wait loop with the given duty cycle (0.0-1.0)."""
    busy = CYCLE_PERIOD_S * duty
    sleep = CYCLE_PERIOD_S * (1.0 - duty)
    while True:
        end = time.perf_counter() + busy
        while time.perf_counter() < end:
            pass
        if sleep > 0:
            time.sleep(sleep)


if __name__ == "__main__":
    core_count = os.cpu_count() or 1

    # How many full cores worth of load do we need?
    cores_needed = TARGET_SYSTEM_PCT / 100.0 * core_count
    full_workers = int(math.floor(cores_needed))
    fractional = cores_needed - full_workers

    print(f"Cores (logical):  {core_count}")
    print(f"Cores to load:    {cores_needed:.2f}")
    if fractional > 0.01:
        print(f"Workers:          {full_workers} at 100%  +  1 at {fractional * 100:.0f}% duty")
    else:
        print(f"Workers:          {full_workers} at 100%")
    print(f"Expected system:  ~{TARGET_SYSTEM_PCT:.0f}%  (Task Manager)")
    print()
    print("Running... (Ctrl+C to stop)")

    workers: list[multiprocessing.Process] = []
    for _ in range(full_workers):
        p = multiprocessing.Process(target=burn_loop, args=(1.0,), daemon=True)
        p.start()
        workers.append(p)

    if fractional > 0.01:
        p = multiprocessing.Process(target=burn_loop, args=(fractional,), daemon=True)
        p.start()
        workers.append(p)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping workers...")
        for w in workers:
            w.terminate()
        print("Stopped.")
