"""
Pipe Reader Stress Test — run through the Launcher.

Exercises the failure modes fixed in process_tracker._read_output:
    EOF loop        — reader threads spun forever after child exit
    queue.Full      — reader thread died silently under high output
    UTF-8 splits    — UnicodeDecodeError when multibyte char crossed a
                      4096-byte os.read() boundary
    stop_event      — stdin_writer thread leaked on normal exit

What to check in the Launcher tab:
    - Each [PHASE] header appears in order
    - The [DONE] line at the end appears
    - Tab footer shows "Script '...' completed successfully"
    - If queue overflow triggered, the launcher's own console (not the
      script tab) will show a [WARNING] Output queue full line — that is
      the fix working, not a failure.

Standalone:
    python Tests/test_pipe_stress.py
"""

import sys
import time

# =============================================================================
# Configuration
# =============================================================================

# Each unit is 28 bytes of UTF-8 multibyte chars.  With the newline appended
# the repeating block is exactly 29 bytes.  29 is prime and 4096 = 2^12, so
# gcd(29, 4096) = 1.  That means across a large enough contiguous write every
# possible byte offset within the unit will appear at a 4096-byte read
# boundary, *guaranteeing* that multibyte chars are split mid-sequence — not
# a probabilistic flake, a deterministic trigger.
#
# Byte breakdown:  🎉(4) 日(3) 本(3) 語(3) 中(3) 文(3) 한(3) 국(3) 어(3) = 28
MULTIBYTE_UNIT  = "\U0001f389\u65e5\u672c\u8a9e\u4e2d\u6587\ud55c\uad6d\uc5b4"
MULTIBYTE_LINES = 3000          # 3000 * 29 = 87 000 bytes -> ~21 reads

BURST_COUNT     = 30_000        # stdout flood; queue maxsize = 1000

# =============================================================================
# Phases
# =============================================================================

def phase_partial_line() -> str:
    """Write a prompt with no trailing newline, pause, then complete it.
    Exercises the partial-line flush and the last_flushed_partial guard."""
    print("[PHASE 1] Partial line", flush=True)
    sys.stdout.write("  waiting")
    sys.stdout.flush()
    time.sleep(0.5)
    sys.stdout.write(" ... done\n")
    sys.stdout.flush()
    return "partial written and completed"


def phase_multibyte() -> str:
    """Single large write forcing multibyte splits at every read boundary.

    Written to sys.stdout.buffer so the OS sees one contiguous block.  The
    reader's os.read(fd, 4096) will slice it into chunks that land inside
    multibyte sequences.  An incremental decoder handles this silently; a
    per-chunk .decode("utf-8") would raise UnicodeDecodeError on the reader
    thread.
    """
    print("[PHASE 2] Multibyte boundary stress", flush=True)
    block = (MULTIBYTE_UNIT + "\n") * MULTIBYTE_LINES
    raw = block.encode("utf-8")
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    print(f"  wrote {MULTIBYTE_LINES} lines ({len(raw)} bytes)", flush=True)
    return f"{MULTIBYTE_LINES} lines / {len(raw)} bytes"


def phase_burst() -> str:
    """Flood stdout as fast as possible.

    The output queue is maxsize=1000.  If the dispatcher falls behind
    (slow UI, busy machine) put_nowait would overflow.  The fix drops and
    warns once instead of crashing the reader thread.  Look for the warning
    in the launcher's own console, not in this tab.
    """
    print(f"[PHASE 3] Burst {BURST_COUNT} lines", flush=True)
    for i in range(BURST_COUNT):
        print(f"[BURST] {i}")
    # This line arrives after the flood.  If you see it, the reader survived.
    print(f"  last burst index: {BURST_COUNT - 1}", flush=True)
    return f"{BURST_COUNT} lines"


def phase_stderr_interleave() -> str:
    """Hammer both stdout and stderr reader threads at the same time."""
    print("[PHASE 4] Stderr interleave (500 pairs)", flush=True)
    for i in range(500):
        print(f"  [out] {i}", flush=True)
        print(f"  [err] {i}", file=sys.stderr, flush=True)
    return "500 pairs"


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    phases: list[tuple[str, object]] = [
        ("partial line",      phase_partial_line),
        ("multibyte",         phase_multibyte),
        ("burst",             phase_burst),
        ("stderr interleave", phase_stderr_interleave),
    ]

    results: list[tuple[str, str, str]] = []   # (name, status, detail)
    for name, fn in phases:
        try:
            detail = fn()
            results.append((name, "PASS", detail))
        except Exception as e:
            results.append((name, "FAIL", str(e)))

    # ---------------------------------------------------------------------
    # Results table — this is also the EOF canary.  If it appears, the
    # reader flushed its buffer and the None sentinel reached the dispatcher.
    # ---------------------------------------------------------------------
    print("\n" + "=" * 52, flush=True)
    print(" RESULTS", flush=True)
    print("=" * 52, flush=True)
    for name, status, detail in results:
        print(f"  [{status}] {name:25s} {detail}", flush=True)
    print("=" * 52, flush=True)

    all_passed = all(s == "PASS" for _, s, _ in results)
    if all_passed:
        print("  All phases passed.", flush=True)
        print("  Tab footer 'completed successfully' = EOF + stop_event OK.", flush=True)
    else:
        print("  SOME PHASES FAILED — check output above.", flush=True)


if __name__ == "__main__":
    main()
