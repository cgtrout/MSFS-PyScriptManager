__all__ = [
    "print_warning",
    "print_info",
    "print_debug",
    "print_error",
    "print_color"
]

import re
import threading

_print_lock = threading.Lock()

# Debug level mapping
DEBUG_LEVELS = {
    "ERROR": 1,
    "WARNING": 2,
    "INFO": 3,
    "DEBUG": 4
}
# Global debug level (default: don't show DEBUG messages)
_current_debug_level = DEBUG_LEVELS["INFO"]

def set_debug_level(level):
    """
    Sets the global debug level.

    Args:
        level (str): One of ["ERROR", "WARNING", "INFO", "DEBUG"] (case insensitive).
    """
    global _current_debug_level
    level = level.upper()
    if level in DEBUG_LEVELS:
        _current_debug_level = DEBUG_LEVELS[level]
    else:
        raise ValueError(f"Invalid debug level: {level}. Choose from {list(DEBUG_LEVELS.keys())}")

def print_color(text, color=None, bold=False):
    """
    Parses and prints text with optional ANSI color codes and custom tags.

    Args:
        text (str): The text to print, which may include custom tags like [red(]... or [green(]...
        color (str): The default color for the text (if no tags are present).
        bold (bool): Whether the text should be bold by default (if no tags are present).
    """
    TAG_PATTERN = re.compile(r'\[([a-z]+)\(\](.*?)\[+\)\]', re.IGNORECASE)  # Tag pattern: [tag(]text[)]
    parsed_segments = []
    last_pos = 0

    # Match all tags in the text
    for match in TAG_PATTERN.finditer(text):
        start, end = match.span()
        tag, content = match.groups()

        # Add plain text before this tag
        if start > last_pos:
            parsed_segments.append((text[last_pos:start], {"color": color, "bold": bold}))

        # Handle recognized tags
        if tag in ("red", "green", "blue", "yellow", "magenta", "cyan", "white"):
            parsed_segments.append((content, {"color": tag, "bold": bold}))
        else:
            # If the tag is unrecognized, treat it as plain text
            parsed_segments.append((f"[{tag}({content})]", {"color": None, "bold": False}))

        last_pos = end

    # Add any remaining text after the last tag
    if last_pos < len(text):
        parsed_segments.append((text[last_pos:], {"color": color, "bold": bold}))

    # If no tags were found, apply the default color and bold settings to the entire text
    if not parsed_segments:
        parsed_segments.append((text, {"color": color, "bold": bold}))

    # Build the entire formatted output as a single string
    output = []
    for segment, style in parsed_segments:
        color_code = style["color"]
        bold_code = '1' if style["bold"] else '0'
        ansi_start = f"\033[{bold_code};{30 + {'red': 1, 'green': 2, 'yellow': 3, 'blue': 4, 'magenta': 5, 'cyan': 6, 'white': 7}.get(color_code, 0)}m" if color_code else f"\033[{bold_code}m"
        ansi_reset = "\033[0m"
        output.append(f"{ansi_start}{segment}{ansi_reset}")

    with _print_lock:
        print("".join(output))

def print_debug(message):
    """
    Prints a debug message with a cyan `[DEBUG]` prefix.

    Args:
        message (str): The message to print.
    """
    if _current_debug_level >= DEBUG_LEVELS["DEBUG"]:
        print_color(f"[cyan(][DEBUG][)] {message}", bold=False)

def print_info(message):
    """
    Prints an info message with a green `[INFO]` prefix.

    Args:
        message (str): The message to print.
    """
    if _current_debug_level >= DEBUG_LEVELS["INFO"]:
        print_color(f"[green(][INFO][)] {message}", bold=False)

def print_warning(message):
    """
    Prints a warning message with a yellow `[WARNING]` prefix.

    Args:
        message (str): The message to print.
    """
    if _current_debug_level >= DEBUG_LEVELS["WARNING"]:
        print_color(f"[WARNING] {message}", color="yellow", bold=True)

def print_error(message):
    """
    Prints an error message with a red `[ERROR]` prefix.

    Args:
        message (str): The message to print.
    """
    print_color(f"[red(][ERROR][)] {message}", bold=True)
