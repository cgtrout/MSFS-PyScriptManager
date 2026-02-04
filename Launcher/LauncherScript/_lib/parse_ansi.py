# parse_ansi.py - used to parse ANSI escape sequences in text and apply colors and styles to the text.
#   This is for displaying colored text in ScriptTab.
class AnsiParser:
    ANSI_COLOR_MAP = {
        '30': '#000000', '31': '#FF0000', '32': '#00FF00', '33': '#FFFF00',
        '34': '#0000FF', '35': '#FF00FF', '36': '#00FFFF', '37': '#FFFFFF'
    }

    def __init__(self):
        self.current_style = {"color": None, "bold": False}
        self.partial_sequence = ""  # Buffer to store incomplete ANSI sequences

    def parse_ansi_colors(self, text):
        """
        Parse ANSI sequences and return text segments with associated styles.
        This version includes detailed debugging and partial sequence handling.

        Args:
            text (str): The input text containing ANSI escape sequences.

        Returns:
            list of tuples: Each tuple contains:
                - Text segment (str)
                - Style (dict): {'color': str, 'bold': bool}
        """
        segments = []  # Parsed text segments
        buffer = self.partial_sequence + text  # Combine retained partial sequence with new text
        self.partial_sequence = ""  # Clear the buffer for now

        while buffer:
            escape_start = buffer.find('\x1b')

            if escape_start == -1:
                # No escape sequences found, treat the entire buffer as plain text
                segments.append((buffer, self.current_style.copy()))
                buffer = ""
            else:
                # Process text before the escape sequence
                if escape_start > 0:
                    plain_text = buffer[:escape_start]
                    segments.append((plain_text, self.current_style.copy()))
                    buffer = buffer[escape_start:]

                # Check for the start of an escape sequence
                if buffer.startswith('\x1b['):
                    # Look for the end of the ANSI sequence
                    escape_end = buffer.find('m', 2)  # Start looking after '\x1b['
                    if escape_end == -1:
                        # Incomplete sequence, retain it for the next call
                        self.partial_sequence = buffer
                        buffer = ""
                    else:
                        # Extract and process the complete escape sequence
                        sequence = buffer[2:escape_end].split(';')  # Extract codes after '\x1b['
                        buffer = buffer[escape_end + 1:]  # Trim the processed sequence

                        # Update the current style based on the sequence
                        for code in sequence:
                            if code == '0':  # Reset
                                self.current_style = {"color": None, "bold": False}
                            elif code == '1':  # Bold
                                self.current_style["bold"] = True
                            elif code in self.ANSI_COLOR_MAP:  # Color
                                self.current_style["color"] = self.ANSI_COLOR_MAP[code]
                else:
                    # Handle an incomplete escape sequence like '\x1b' or invalid sequences
                    if buffer == '\x1b':
                        self.partial_sequence = buffer
                        buffer = ""
                    else:
                        # If it's not valid but starts with '\x1b', discard or handle appropriately
                        segments.append((buffer, self.current_style.copy()))
                        buffer = ""

        return segments

def test_partial_matches():
    # Test cases: input chunks and expected partial matches
     # Additional test cases
    test_cases = [
        # Test max length for escape sequences
        ("\x1b[" + "1;" * 15 + "31mText", ""),  # Valid sequence right at the max length
        ("\x1b[" + "1;" * 16 + "31mText", ""),  # Exceeds max length, should discard
        ("\x1b[31;" + "1;" * 14 + "mText", ""),  # Borderline valid with trailing plain text
        ("\x1b[31;" + "1;" * 15, "\x1b[31;" + "1;" * 15),  # Too long, partial retained

        # Malformed escape sequences
        ("\x1b[foo;bar", "\x1b[foo;bar"),  # Completely invalid codes
        ("\x1b[123;456z", "\x1b[123;456z"),  # Ends with unknown terminator
        ("\x1b[;;mText", ""),  # Valid escape but unusual empty codes
        ("\x1b[mText", ""),  # Reset escape sequence
        ("\x1b[1;mText", ""),  # Bold and reset

        # Partial escape with plain text after it
        ("\x1b[31", "\x1b[31"),  # Incomplete color escape
        ("Hello", ""),  # Text after incomplete escape

        # Rapid succession of escape sequences
        ("\x1b[31m\x1b[32m\x1b[33m", ""),  # Multiple valid sequences in one chunk
        ("\x1b[31;\x1b[32m", "\x1b[31;"),  # Partially nested sequences, retain invalid partial

        # Plain text mixed with escape sequences
        ("Text\x1b[31mColor\x1b[0m", ""),  # Reset style works correctly
        ("\x1b[31mRed\x1b[32mGreen\x1b[33mYellow", ""),  # Chained colored segments

        # Escape sequences split across multiple calls
        ("\x1b[31", "\x1b[31"),  # First call starts incomplete
        (";1mHello", ""),        # Second call completes and outputs text

        # Edge cases
        ("\x1b[", "\x1b["),                  # Incomplete start
        ("m\x1b[31;1", "\x1b[31;1"),        # New sequence starts after finishing the first
        ("Hello\x1b[31", "\x1b[31"),        # Text followed by incomplete escape
        ("\x1b[;;", "\x1b[;;"),             # Unusual empty code parts
        ("\x1b[;;31m", ""),                 # Empty parts but valid terminator

        # Very large chunks
        ("\x1b[31m" + "A" * 1000, ""),      # Valid escape with lots of text
        ("\x1b[31;" + "1;" * 15 + "32mB", ""),  # Near-limit escape followed by text
        ("aaaaaaaaaaaaa\x1b", "\x1b"),
    ]

    # Run test cases
    for i, (chunk, expected_partial) in enumerate(test_cases):
        # Reinitialize the parser for each test case
        parser = AnsiParser()

        print(f"Test Case {i + 1}: Input: {repr(chunk)}")
        parser.parse_ansi_colors(chunk)  # Feed chunk to the parser
        actual_partial = parser.partial_sequence

        # Compare the actual partial sequence to the expected one
        if actual_partial == expected_partial:
            print(f"  PASSED: Retained partial match is {repr(actual_partial)}")
        else:
            print(f"  FAILED: Expected {repr(expected_partial)}, but got {repr(actual_partial)}")
        print("-" * 50)


if __name__ == "__main__":
    print("Testing Partial Matches...")
    test_partial_matches()