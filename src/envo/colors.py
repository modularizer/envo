"""
Color definitions for envo CLI output.

This module provides consistent color styling for both `envo show` and `envo config`
commands, ensuring they use the same color scheme. All colors are defined as hex values
that work with both termite (using rgb[#hex] syntax) and prompt_toolkit (using #hex).
"""

# Key status constants
KEY_STATUS_DEFAULT = "default"      # No value specified, using spec default
KEY_STATUS_VALID = "valid"          # Value specified and valid
KEY_STATUS_INVALID = "invalid"      # Invalid value
KEY_STATUS_EXTRA = "extra"          # Extra key not in spec

# Key colors (hex values) - chosen to work on both black and white backgrounds
KEY_COLOR_DEFAULT = "#5f9ea0"       # Blue-gray for default/fallback values (cadet blue)
KEY_COLOR_VALID = "#0087d7"         # Medium blue-cyan for valid specified values (works on both)
KEY_COLOR_INVALID = "#d70000"       # Darker red for invalid values (better on white)
KEY_COLOR_EXTRA = "#875faf"         # Muted purple for extra keys not in spec (works on both)
KEY_COLOR_DEFAULT_VALUE = "#0087d7" # Default fallback (medium blue-cyan)

# Value colors (hex values) - chosen to work on both black and white backgrounds
VALUE_COLOR_DIM = "#808080"         # Gray for None/unset values
VALUE_COLOR_GREEN = "#00af00"       # Medium green for true booleans (works on both)
VALUE_COLOR_RED = "#d70000"         # Darker red for false booleans (better on white)
VALUE_COLOR_YELLOW = "#ff8700"      # Gold/orange for numbers (works on both backgrounds)
VALUE_COLOR_BLUE = "#005fd7"        # Medium blue for paths (works on both)
VALUE_COLOR_WHITE = ""              # Default text color for strings (no special color)

# UI colors (hex values) - for interactive config and other UI elements
HIGHLIGHT_BG_COLOR = "#f5c842"      # Warm golden yellow for selected items (pleasant, works on both)
UI_TEXT_DIM = "#666666"             # Dim gray for UI text (labels, separators, help text)

# Text colors when on highlight background (adjusted for better contrast on yellow background)
# These are darker versions optimized for readability on the golden yellow background
KEY_COLOR_DEFAULT_HIGHLIGHT = "#1a3a4f"    # Very dark blue-gray for default keys on highlight
KEY_COLOR_VALID_HIGHLIGHT = "#003070"      # Very dark blue for valid keys on highlight
KEY_COLOR_INVALID_HIGHLIGHT = "#700000"    # Very dark red for invalid keys on highlight
KEY_COLOR_EXTRA_HIGHLIGHT = "#4f1f6f"      # Very dark purple for extra keys on highlight
KEY_COLOR_DEFAULT_VALUE_HIGHLIGHT = "#003070"  # Very dark blue for default on highlight

VALUE_COLOR_DIM_HIGHLIGHT = "#2a2a2a"      # Very dark gray for None/unset on highlight
VALUE_COLOR_GREEN_HIGHLIGHT = "#004d00"    # Very dark green for true booleans on highlight
VALUE_COLOR_RED_HIGHLIGHT = "#700000"      # Very dark red for false booleans on highlight
VALUE_COLOR_YELLOW_HIGHLIGHT = "#704f00"   # Very dark brown for numbers on highlight
VALUE_COLOR_BLUE_HIGHLIGHT = "#003070"     # Very dark blue for paths on highlight
VALUE_COLOR_WHITE_HIGHLIGHT = "#000000"    # Black for strings on highlight (best contrast)
HIGHLIGHT_TEXT_COLOR_DIM = "#2a2a2a"       # Very dark gray for dim text on highlight background

