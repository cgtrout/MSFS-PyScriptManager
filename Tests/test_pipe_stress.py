"""
Pipe stress test — exercises edge cases in subprocess I/O handling.

Tests: UTF-8 multibyte splits at read boundaries, partial line flushing,
stdout burst flooding, and stderr interleaving.

Can also be run standalone:  python Tests/test_pipe_stress.py
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve()

# =============================================================================
# Configuration
# =============================================================================

MULTIBYTE_UNIT = "\U0001f389\u65e5\u672c\u8a9e\u4e2d\u6587\ud55c\uad6d\uc5b4"
MULTIBYTE_LINES = 3000
BURST_COUNT = 30_000

# =============================================================================
# Phases (used by standalone mode)
# =============================================================================

import time


def phase_partial_line() -> str:
    """Partial-line flush and completion."""
    print("[PHASE 1] Partial line", flush=True)
    sys.stdout.write("  waiting")
    sys.stdout.flush()
    time.sleep(0.5)
    sys.stdout.write(" ... done\n")
    sys.stdout.flush()
    return "partial written and completed"


def phase_multibyte() -> str:
    """Large write forcing multibyte splits at every read boundary."""
    print("[PHASE 2] Multibyte boundary stress", flush=True)
    block = (MULTIBYTE_UNIT + "\n") * MULTIBYTE_LINES
    raw = block.encode("utf-8")
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()
    print(f"  wrote {MULTIBYTE_LINES} lines ({len(raw)} bytes)", flush=True)
    return f"{MULTIBYTE_LINES} lines / {len(raw)} bytes"


def phase_burst() -> str:
    """Flood stdout to stress queue handling."""
    print(f"[PHASE 3] Burst {BURST_COUNT} lines", flush=True)
    for i in range(BURST_COUNT):
        print(f"[BURST] {i}")
    print(f"  last burst index: {BURST_COUNT - 1}", flush=True)
    return f"{BURST_COUNT} lines"


def phase_stderr_interleave() -> str:
    """Hammer both stdout and stderr simultaneously."""
    print("[PHASE 4] Stderr interleave (500 pairs)", flush=True)
    for i in range(500):
        print(f"  [out] {i}", flush=True)
        print(f"  [err] {i}", file=sys.stderr, flush=True)
    return "500 pairs"


# =============================================================================
# Standalone runner
# =============================================================================

def main() -> None:
    phases: list[tuple[str, object]] = [
        ("partial line",      phase_partial_line),
        ("multibyte",         phase_multibyte),
        ("burst",             phase_burst),
        ("stderr interleave", phase_stderr_interleave),
    ]

    results: list[tuple[str, str, str]] = []
    for name, fn in phases:
        try:
            detail = fn()
            results.append((name, "PASS", detail))
        except Exception as e:
            results.append((name, "FAIL", str(e)))

    print("\n" + "=" * 52, flush=True)
    print(" RESULTS", flush=True)
    print("=" * 52, flush=True)
    for name, status, detail in results:
        print(f"  [{status}] {name:25s} {detail}", flush=True)
    print("=" * 52, flush=True)

    all_passed = all(s == "PASS" for _, s, _ in results)
    if all_passed:
        print("  All phases passed.", flush=True)
    else:
        print("  SOME PHASES FAILED — check output above.", flush=True)
        sys.exit(1)


# =============================================================================
# Pytest tests — run this script as a subprocess and verify output
# =============================================================================

import pytest


@pytest.fixture(scope="module")
def stress_result():
    """Run the stress test once and share the result across all tests."""
    return subprocess.run(
        [sys.executable, "-u", str(SCRIPT)],
        capture_output=True, text=True, encoding="utf-8", timeout=60,
        stdin=subprocess.DEVNULL
    )


def test_all_phases_pass(stress_result):
    """All four stress phases should complete with PASS status."""
    assert stress_result.returncode == 0, f"Script failed (code {stress_result.returncode}):\n{stress_result.stderr}"
    assert "[PASS] partial line" in stress_result.stdout
    assert "[PASS] multibyte" in stress_result.stdout
    assert "[PASS] burst" in stress_result.stdout
    assert "[PASS] stderr interleave" in stress_result.stdout


def test_results_table_appears(stress_result):
    """The results table (EOF canary) should appear, proving the script ran to completion."""
    assert "RESULTS" in stress_result.stdout
    assert "All phases passed." in stress_result.stdout


def test_multibyte_output_intact(stress_result):
    """Multibyte characters should survive the subprocess pipe without corruption."""
    assert MULTIBYTE_UNIT in stress_result.stdout, "Multibyte characters corrupted in pipe"


def test_burst_completes(stress_result):
    """The burst phase should emit all lines without crashing."""
    assert f"last burst index: {BURST_COUNT - 1}" in stress_result.stdout


if __name__ == "__main__":
    main()
