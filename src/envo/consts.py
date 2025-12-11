"""
Constants and configuration for envo.

This module centralizes all default values, colors, settings, and configuration
options used throughout the envo package. By keeping these in one place, users
can easily customize behavior and maintainers can ensure consistency.
"""

# =============================================================================
# File Names and Paths
# =============================================================================

# Default environment file name
DEFAULT_ENV_FILE = ".env"

# Default spec file names (searched in order)
DEFAULT_SPEC_FILES = ("sample.env", ".env.sample")

# Special value that indicates "use the default from spec"
USE_SPEC_DEFAULT = "<default>"

# =============================================================================
# Special ENVO Keys (for file chaining)
# =============================================================================

# Load another file with LOWER priority (current file overrides it)
ENVO_EXTENDS = "ENVO_EXTENDS"

# Load another file with HIGHER priority (it overrides current file)
ENVO_EXTENDED_BY = "ENVO_EXTENDED_BY"

# Set of all special ENVO keys (excluded from normal env vars)
ENVO_SPECIAL_KEYS = frozenset({ENVO_EXTENDS, ENVO_EXTENDED_BY})

# =============================================================================
# Default Values for Specs
# =============================================================================

# Default group name for variables without an explicit group
DEFAULT_GROUP = "unknown"

# Default documentation string when none is provided
DEFAULT_DOCS = "No help available"

# =============================================================================
# Boolean Coercion Values
# =============================================================================

# Values that coerce to True (case-insensitive)
BOOL_TRUE_VALUES = frozenset({
    "true", "1", "yes", "on", "y", "enable", "enabled"
})

# Values that coerce to False (case-insensitive)
BOOL_FALSE_VALUES = frozenset({
    "false", "0", "no", "off", "n", "disable", "disabled"
})

# Values that coerce to None (case-insensitive)
NULL_VALUES = frozenset({"null", "none"})

# =============================================================================
# Key Status Constants (for display/styling)
# =============================================================================

KEY_STATUS_DEFAULT = "default"      # No value specified, using spec default
KEY_STATUS_VALID = "valid"          # Value specified and valid
KEY_STATUS_INVALID = "invalid"      # Invalid value
KEY_STATUS_EXTRA = "extra"          # Extra key not in spec

# =============================================================================
# Color Scheme - Key Colors
# =============================================================================
# Hex values chosen to work on both black and white terminal backgrounds

KEY_COLOR_DEFAULT = "#5f9ea0"       # Blue-gray for default/fallback values (cadet blue)
KEY_COLOR_VALID = "#0087d7"         # Medium blue-cyan for valid specified values
KEY_COLOR_INVALID = "#d70000"       # Darker red for invalid values
KEY_COLOR_EXTRA = "#875faf"         # Muted purple for extra keys not in spec
KEY_COLOR_DEFAULT_VALUE = "#0087d7" # Default fallback (medium blue-cyan)

# =============================================================================
# Color Scheme - Value Colors
# =============================================================================

VALUE_COLOR_DIM = "#808080"         # Gray for None/unset values
VALUE_COLOR_GREEN = "#00af00"       # Medium green for true booleans
VALUE_COLOR_RED = "#d70000"         # Darker red for false booleans
VALUE_COLOR_YELLOW = "#ff8700"      # Gold/orange for numbers
VALUE_COLOR_BLUE = "#005fd7"        # Medium blue for paths
VALUE_COLOR_WHITE = ""              # Default text color for strings (no special color)

# =============================================================================
# Color Scheme - UI Colors
# =============================================================================

HIGHLIGHT_BG_COLOR = "#f5c842"      # Warm golden yellow for selected items
UI_TEXT_DIM = "#666666"             # Dim gray for UI text (labels, separators, help text)

# =============================================================================
# Color Scheme - Highlighted State (on yellow background)
# =============================================================================
# Darker versions optimized for readability on the golden yellow background

KEY_COLOR_DEFAULT_HIGHLIGHT = "#1a3a4f"    # Very dark blue-gray for default keys
KEY_COLOR_VALID_HIGHLIGHT = "#003070"      # Very dark blue for valid keys
KEY_COLOR_INVALID_HIGHLIGHT = "#700000"    # Very dark red for invalid keys
KEY_COLOR_EXTRA_HIGHLIGHT = "#4f1f6f"      # Very dark purple for extra keys
KEY_COLOR_DEFAULT_VALUE_HIGHLIGHT = "#003070"  # Very dark blue for default

VALUE_COLOR_DIM_HIGHLIGHT = "#2a2a2a"      # Very dark gray for None/unset
VALUE_COLOR_GREEN_HIGHLIGHT = "#004d00"    # Very dark green for true booleans
VALUE_COLOR_RED_HIGHLIGHT = "#700000"      # Very dark red for false booleans
VALUE_COLOR_YELLOW_HIGHLIGHT = "#704f00"   # Very dark brown for numbers
VALUE_COLOR_BLUE_HIGHLIGHT = "#003070"     # Very dark blue for paths
VALUE_COLOR_WHITE_HIGHLIGHT = "#000000"    # Black for strings (best contrast)
HIGHLIGHT_TEXT_COLOR_DIM = "#2a2a2a"       # Very dark gray for dim text on highlight

# =============================================================================
# UI Text and Formatting
# =============================================================================

# Separator line character and default width
UI_SEPARATOR_CHAR = "─"
UI_SEPARATOR_WIDTH = 80

# Help text for interactive config navigation
UI_HELP_BROWSE = "↑↓ Navigate  Enter Edit  ^S Save  ^Q Quit"
UI_HELP_EDIT = "Press Enter to save, Ctrl+C to cancel"

# Placeholder text
UI_NOT_SET = "(not set)"

# Validation status indicators
UI_VALID_PREFIX = "✓ Valid"
UI_INVALID_PREFIX = "✗ Invalid"

# Arrow for showing value changes
UI_CHANGE_ARROW = " → "

# =============================================================================
# Variable Reference Resolution
# =============================================================================

# Maximum iterations for resolving $VAR_NAME references (prevents infinite loops)
VAR_REFERENCE_MAX_ITERATIONS = 20

# Project root substitution character
PROJECT_ROOT_CHAR = "%"
