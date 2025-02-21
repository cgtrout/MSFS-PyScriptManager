""" gc_tweak.py - tweak GC """


# Based on article
# https://mkennedy.codes/posts/python-gc-settings-change-this-and-make-your-app-go-20pc-faster/
import gc
import time
import psutil

# Get the current process to measure CPU usage
process = psutil.Process()
total_gc_time = 0
gc_start_time = None
app_start_time = time.perf_counter()  # Track when the app starts

def track_gc_time(phase, info):
    global total_gc_time, gc_start_time

    if phase == "start":
        gc_start_time = time.perf_counter()
    elif phase == "stop" and gc_start_time is not None:
        total_gc_time += time.perf_counter() - gc_start_time
        gc_start_time = None  # Reset after use

        # Calculate GC overhead percentage
        elapsed_time = time.perf_counter() - app_start_time
        gc_percentage = (total_gc_time / elapsed_time) * 100 if elapsed_time > 0 else 0

        print(f"Total GC time: {total_gc_time:.6f}s ({gc_percentage:.2f}% of runtime)")

def optimize_gc(allocs: int = 50_000, gen1_factor: int = 2, gen2_factor: int = 2,
                freeze: bool = True, show_data = False):
    """
    Optimize Python's garbage collection settings for performance.

    Parameters:
    - allocs (int): The threshold for generation 0 GC (default: 50,000).
    - gen1_factor (int): Multiplier for generation 1 threshold (default: 2x).
    - gen2_factor (int): Multiplier for generation 2 threshold (default: 2x).
    - freeze (bool): Whether to freeze the current GC state to avoid redundant checks.

    Note: default Python GC values are 700, 10, 10
    """
    # Perform an initial garbage collection
    gc.collect(2)

    # Optionally freeze the current state to prevent unnecessary re-checks
    if freeze:
        gc.freeze()

    # Get the current thresholds
    _current_allocs, gen1, gen2 = gc.get_threshold()

    # Apply new thresholds
    new_gen1 = gen1 * gen1_factor
    new_gen2 = gen2 * gen2_factor
    gc.set_threshold(allocs, new_gen1, new_gen2)

    if show_data:
        gc.callbacks.append(track_gc_time)

