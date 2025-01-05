# parse_ansi.py - used to parse ANSI escape sequences in text and apply colors and styles to the text.
#   This is for displaying colored text in ScriptTab.
ANSI_COLOR_MAP = {
    '31': '#FF0000',  # Red
    '32': '#00FF00',  # Green
    '33': '#FFFF00',  # Yellow
    '34': '#0000FF',  # Blue
    '35': '#FF00FF',  # Magenta
    '36': '#00FFFF',  # Cyan
    '37': '#FFFFFF',  # White
    '0': None,        # Reset
}

def parse_ansi_colors(text):
    """
    Parse ANSI sequences in the text and return segments with associated colors and bold styles.
    This version verbalizes every step for debugging.

    Args:
        text (str): The input text with ANSI escape sequences.

    Returns:
        list of tuples: Each tuple contains:
            - Text segment (str)
            - Style (dict): {'color': str, 'bold': bool}
    """
    segments = []                  # List to store parsed text segments
    current_style = {"color": None, "bold": False}  # Initial style
    buffer = ""                    # Buffer to hold plain text
    i = 0                          # Pointer for text traversal

    while i < len(text):
        if text[i:i+2] == '\033[':  # Start of an ANSI escape sequence

            # Add the current buffer as a plain text segment
            if buffer:
                segments.append((buffer, current_style.copy()))
                buffer = ""  # Clear the buffer

            # Move past the escape sequence introducer
            i += 2
            code = ""  # Temporary variable to hold the escape code

            # Read until we find the 'm' character (end of the ANSI sequence)
            while i < len(text) and text[i] != 'm':
                code += text[i]
                i += 1

            # Skip past the 'm' character
            i += 1

            # Split the code into parts (e.g., '1;31' -> ['1', '31'])
            codes = code.split(';')

            # Process each part of the ANSI code
            for part in codes:
                if part == '0':  # Reset
                    current_style = {"color": None, "bold": False}
                elif part == '1':  # Bold
                    current_style["bold"] = True
                elif part in ANSI_COLOR_MAP:  # Color
                    current_style["color"] = ANSI_COLOR_MAP[part]

        else:
            # If not an escape sequence, add to the buffer
            buffer += text[i]
            i += 1

    # Add any remaining buffer as the last plain text segment
    if buffer:
        segments.append((buffer, current_style.copy()))

    return segments