""" gc_tweak.py - tweak GC """


# Based on article
# https://mkennedy.codes/posts/python-gc-settings-change-this-and-make-your-app-go-20pc-faster/
import gc
import psutil

# Get the current process to measure CPU usage
process = psutil.Process()

def optimize_gc(allocs: int = 50_000, gen1_factor: int = 2, gen2_factor: int = 2, freeze: bool = True):
    """
    Optimize Python's garbage collection settings for performance.

    Parameters:
    - allocs (int): The threshold for generation 0 GC (default: 50,000).
    - gen1_factor (int): Multiplier for generation 1 threshold (default: 2x).
    - gen2_factor (int): Multiplier for generation 2 threshold (default: 2x).
    - freeze (bool): Whether to freeze the current GC state to avoid redundant checks.
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

