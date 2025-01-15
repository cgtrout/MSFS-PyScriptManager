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
        self.partial_sequence = ""  # Clear partial sequence buffer for now

        #print(f"parse_ansi_colors text={repr(text)}")
        #print(f"[DEBUG] Starting parse with buffer: {repr(buffer)}")
        #print(f"[DEBUG] Initial style: {self.current_style}")

        i = 0  # Current parsing index
        while i < len(buffer):
            # Detect the start of an ANSI escape sequence
            if buffer[i:i + 2] == '\x1b[':
                # Add plain text before the escape sequence
                if i > 0:
                    plain_text = buffer[:i]
                    segments.append((plain_text, self.current_style.copy()))
                    #print(f"[DEBUG] Added plain text: {repr(plain_text)}, Style: {self.current_style}")
                    buffer = buffer[i:]  # Trim processed part
                    i = 0  # Reset index for the new buffer

                # Parse the ANSI escape sequence
                end_idx = buffer.find('m', i)
                if end_idx == -1:
                    # Incomplete sequence; retain it for the next chunk
                    self.partial_sequence = buffer
                    #print(f"[DEBUG] Retaining incomplete sequence: {repr(buffer)}")
                    return segments

                # Extract and process the full escape sequence
                sequence = buffer[2:end_idx].split(';')
                buffer = buffer[end_idx + 1:]  # Remove the processed sequence
                i = 0  # Reset index for the new buffer
                #print(f"[DEBUG] Detected ANSI sequence: {sequence}")

                # Update the current style based on the sequence
                for code in sequence:
                    if code == '0':  # Reset
                        self.current_style = {"color": None, "bold": False}
                        #print(f"[DEBUG] Style reset: {self.current_style}")
                    elif code == '1':  # Bold
                        self.current_style["bold"] = True
                        #print(f"[DEBUG] Bold enabled: {self.current_style}")
                    elif code in self.ANSI_COLOR_MAP:  # Color
                        self.current_style["color"] = self.ANSI_COLOR_MAP[code]
                        #print(f"[DEBUG] Color set: {self.current_style}")

            else:
                # Process remaining plain text
                escape_start = buffer.find('\x1b[')
                if escape_start == -1:
                    # No more escape sequences; process all remaining text
                    segments.append((buffer, self.current_style.copy()))
                    #print(f"[DEBUG] Added remaining plain text: {repr(buffer)}, Style: {self.current_style}")
                    buffer = ""
                    break
                elif escape_start > 0:
                    # Add plain text up to the next escape sequence
                    plain_text = buffer[:escape_start]
                    segments.append((plain_text, self.current_style.copy()))
                    #print(f"[DEBUG] Added plain text before escape: {repr(plain_text)}, Style: {self.current_style}")
                    buffer = buffer[escape_start:]
                    i = 0  # Reset index for the new buffer

        # Add any remaining buffer text
        if buffer:
            segments.append((buffer, self.current_style.copy()))
            #print(f"[DEBUG] Added final buffer text: {repr(buffer)}, Style: {self.current_style}")

        #print(f"[DEBUG] Final segments: {segments}")
        return segments
