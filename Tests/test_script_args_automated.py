"""Test that command-line arguments are correctly passed through subprocess execution."""
import subprocess
import sys


def test_arguments_passed_to_subprocess():
    """Arguments passed to a subprocess script should appear in its output."""
    test_args = ["hello", "world", "--debug", "--mode=test"]

    command = [
        sys.executable, "-u", "-c",
        "import sys; [print(f'arg[{i}]: {a!r}') for i, a in enumerate(sys.argv[1:], 1)]",
    ] + test_args

    result = subprocess.run(
        command, capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL
    )
    assert result.returncode == 0, f"Script exited with code {result.returncode}: {result.stderr}"

    for i, arg in enumerate(test_args, start=1):
        expected = f"arg[{i}]: '{arg}'"
        assert expected in result.stdout, f"Missing expected argument in output: {expected}"


def test_argument_count():
    """Subprocess should receive the exact number of arguments passed."""
    test_args = ["a", "b", "c"]

    command = [
        sys.executable, "-u", "-c",
        "import sys; print(len(sys.argv) - 1)",
    ] + test_args

    result = subprocess.run(
        command, capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL
    )
    assert result.returncode == 0
    assert result.stdout.strip() == str(len(test_args))


def test_no_arguments_produces_zero_count():
    """Running a script with no extra args should produce an empty argument list."""
    command = [
        sys.executable, "-u", "-c",
        "import sys; print(len(sys.argv) - 1)",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=10, stdin=subprocess.DEVNULL
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "0"
