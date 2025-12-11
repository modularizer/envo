"""
Constants and configuration for envo.

This module centralizes all default values, colors, settings, and configuration
options used throughout the envo package.

Constants are organized into three tiers:

1. IMMUTABLE CONSTANTS - Cannot be changed, needed for file discovery/chaining
   These are defined as regular module-level constants.

2. PARSING CONSTANTS - Affect how values are parsed/coerced
   These are loaded from os.environ (ENVO_*) BEFORE full env parsing.
   Can be set in shell environment to affect all subsequent loading.

3. DISPLAY CONSTANTS - Affect UI/display only
   These are loaded from os.environ after parsing is complete.
   Can be set in .env files and picked up dynamically.

Usage:
    # Access constants (dynamic lookup at call time)
    import envo.consts as consts
    print(consts.DEFAULT_GROUP)  # Checks os.environ for ENVO_DEFAULT_GROUP
"""

import os
from typing import Any

# =============================================================================
# IMMUTABLE CONSTANTS
# =============================================================================
# These CANNOT be overridden - they are needed for file discovery and chaining.
# Changing these would create a chicken-and-egg problem.

# Default environment file name
DEFAULT_ENV_FILE = os.environ.get("ENVO_DEFAULT_ENV_FILE", ".env")

# Default spec file names (searched in order)
# Parse from comma-separated env var, or use default tuple
_default_spec_files_str = os.environ.get("ENVO_DEFAULT_SPEC_FILES", "")
if _default_spec_files_str:
    # Parse comma-separated values, strip whitespace and quotes
    DEFAULT_SPEC_FILES = tuple(
        f.strip().strip('"').strip("'").strip()
        for f in _default_spec_files_str.replace("(", "").replace(")", "").split(",")
        if f.strip()
    )
else:
    DEFAULT_SPEC_FILES = ("sample.env", ".env.sample")

# Special key: Load another file with LOWER priority (current file overrides it)
ENVO_EXTENDS = "ENVO_EXTENDS"

# Special key: Load another file with HIGHER priority (it overrides current file)
ENVO_EXTENDED_BY = "ENVO_EXTENDED_BY"

# Set of all special ENVO keys (excluded from normal env vars)
ENVO_SPECIAL_KEYS = frozenset({ENVO_EXTENDS, ENVO_EXTENDED_BY})


# =============================================================================
# PARSING DEFAULTS
# =============================================================================
# These affect HOW values are parsed/coerced. They are loaded from os.environ
# during bootstrap, BEFORE any .env file is fully parsed.
# Set these in your shell environment to affect parsing behavior.

_PARSING_DEFAULTS: dict[str, Any] = {
    # Default group name for variables without an explicit group
    "DEFAULT_GROUP": "unknown",
    
    # Default documentation string when none is provided
    "DEFAULT_DOCS": "No help available",
    
    # Special value that indicates "use the default from spec"
    "USE_SPEC_DEFAULT": "<default>",
    
    # Values that coerce to True (case-insensitive)
    "BOOL_TRUE_VALUES": frozenset({
        "true", "1", "yes", "on", "y", "enable", "enabled"
    }),
    
    # Values that coerce to False (case-insensitive)
    "BOOL_FALSE_VALUES": frozenset({
        "false", "0", "no", "off", "n", "disable", "disabled"
    }),
    
    # Values that coerce to None (case-insensitive)
    "NULL_VALUES": frozenset({"null", "none"}),
    
    # Project root substitution character
    "PROJECT_ROOT_CHAR": "%",
    
    # Maximum iterations for resolving $VAR_NAME references
    "VAR_REFERENCE_MAX_ITERATIONS": 20,
}


# =============================================================================
# DISPLAY DEFAULTS
# =============================================================================
# These only affect display/UI. They can be set in .env files and will be
# picked up dynamically after parsing completes.

_DISPLAY_DEFAULTS: dict[str, Any] = {
    # =========================================================================
    # Key Status Constants (for display/styling)
    # =========================================================================
    
    "KEY_STATUS_DEFAULT": "default",      # No value specified, using spec default
    "KEY_STATUS_VALID": "valid",          # Value specified and valid
    "KEY_STATUS_INVALID": "invalid",      # Invalid value
    "KEY_STATUS_EXTRA": "extra",          # Extra key not in spec
    
    # =========================================================================
    # Color Scheme - Key Colors
    # =========================================================================
    # Hex values chosen to work on both black and white terminal backgrounds
    
    "KEY_COLOR_DEFAULT": "#5f9ea0",       # Blue-gray for default/fallback values
    "KEY_COLOR_VALID": "#0087d7",         # Medium blue-cyan for valid specified values
    "KEY_COLOR_INVALID": "#d70000",       # Darker red for invalid values
    "KEY_COLOR_EXTRA": "#875faf",         # Muted purple for extra keys not in spec
    "KEY_COLOR_DEFAULT_VALUE": "#0087d7", # Default fallback (medium blue-cyan)
    
    # =========================================================================
    # Color Scheme - Value Colors
    # =========================================================================
    
    "VALUE_COLOR_DIM": "#808080",         # Gray for None/unset values
    "VALUE_COLOR_GREEN": "#00af00",       # Medium green for true booleans
    "VALUE_COLOR_RED": "#d70000",         # Darker red for false booleans
    "VALUE_COLOR_YELLOW": "#ff8700",      # Gold/orange for numbers
    "VALUE_COLOR_BLUE": "#005fd7",        # Medium blue for paths
    "VALUE_COLOR_WHITE": "",              # Default text color for strings
    
    # =========================================================================
    # Color Scheme - UI Colors
    # =========================================================================
    
    "HIGHLIGHT_BG_COLOR": "#f5c842",      # Warm golden yellow for selected items
    "UI_TEXT_DIM": "#666666",             # Dim gray for UI text
    
    # =========================================================================
    # Color Scheme - Highlighted State (on yellow background)
    # =========================================================================
    
    "KEY_COLOR_DEFAULT_HIGHLIGHT": "#1a3a4f",
    "KEY_COLOR_VALID_HIGHLIGHT": "#003070",
    "KEY_COLOR_INVALID_HIGHLIGHT": "#700000",
    "KEY_COLOR_EXTRA_HIGHLIGHT": "#4f1f6f",
    "KEY_COLOR_DEFAULT_VALUE_HIGHLIGHT": "#003070",
    
    "VALUE_COLOR_DIM_HIGHLIGHT": "#2a2a2a",
    "VALUE_COLOR_GREEN_HIGHLIGHT": "#004d00",
    "VALUE_COLOR_RED_HIGHLIGHT": "#700000",
    "VALUE_COLOR_YELLOW_HIGHLIGHT": "#704f00",
    "VALUE_COLOR_BLUE_HIGHLIGHT": "#003070",
    "VALUE_COLOR_WHITE_HIGHLIGHT": "#000000",
    "HIGHLIGHT_TEXT_COLOR_DIM": "#2a2a2a",
    
    # =========================================================================
    # UI Text and Formatting
    # =========================================================================
    
    "UI_SEPARATOR_CHAR": "─",
    "UI_SEPARATOR_WIDTH": 80,
    "UI_HELP_BROWSE": "↑↓ Navigate  Type to Search  Esc Clear  Enter Edit  ^S Save  ^Q Quit",
    "UI_HELP_EDIT": "Press Enter to save, Ctrl+C to cancel",
    "UI_NOT_SET": "(not set)",
    "UI_VALID_PREFIX": "✓ Valid",
    "UI_INVALID_PREFIX": "✗ Invalid",
    "UI_CHANGE_ARROW": " → ",
    
    # =========================================================================
    # Navigation Behavior
    # =========================================================================
    
    # If true, navigating up from first item wraps to last, and vice versa
    "CYCLE_ENDLESSLY": False,
}


# Combined defaults for __getattr__ lookup
_DEFAULTS: dict[str, Any] = {**_PARSING_DEFAULTS, **_DISPLAY_DEFAULTS}

# Track if bootstrap has been done
_bootstrap_done = False


def _parse_collection_value(value: str) -> list[str]:
    """
    Parse a collection value from env file format.
    
    Handles formats like:
        - {"true", "1", "yes"}  (Python set literal)
        - ("sample.env", ".env.sample")  (Python tuple literal)
        - true, 1, yes  (simple comma-separated)
        - true,1,yes  (no spaces)
    
    Returns a list of individual string values with quotes/braces stripped.
    """
    # Strip outer whitespace
    value = value.strip()
    
    # Remove outer braces/parentheses if present
    if (value.startswith("{") and value.endswith("}")) or \
       (value.startswith("(") and value.endswith(")")):
        value = value[1:-1]
    
    # Split on comma
    parts = value.split(",")
    
    # Clean each part: strip whitespace and quotes
    result = []
    for part in parts:
        part = part.strip()
        # Remove surrounding quotes (single or double)
        if (part.startswith('"') and part.endswith('"')) or \
           (part.startswith("'") and part.endswith("'")):
            part = part[1:-1]
        if part:  # Only add non-empty values
            result.append(part)
    
    return result


def _coerce_config_value(name: str, value: str) -> Any:
    """
    Coerce a string environment value to the appropriate type based on the default.
    """
    default = _DEFAULTS.get(name)
    
    if default is None:
        return value
    
    # Handle tuple types
    if isinstance(default, tuple):
        return tuple(_parse_collection_value(value))
    
    # Handle frozenset types
    if isinstance(default, frozenset):
        return frozenset(_parse_collection_value(value))
    
    # Handle set types
    if isinstance(default, set):
        return set(_parse_collection_value(value))
    
    # Handle bool types FIRST (bool is subclass of int, so must check before int)
    if isinstance(default, bool):
        return value.lower() in _PARSING_DEFAULTS["BOOL_TRUE_VALUES"]
    
    # Handle int types
    if isinstance(default, int):
        try:
            return int(value)
        except ValueError:
            return default
    
    # Handle float types
    if isinstance(default, float):
        try:
            return float(value)
        except ValueError:
            return default
    
    # Default: return as string
    return value




def __getattr__(name: str) -> Any:
    """
    Dynamic attribute access for module-level constants.
    
    On first access, performs bootstrap to load parsing settings from os.environ.
    Then checks os.environ for ENVO_* overrides before returning defaults.
    """
    if name.startswith("_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    # Check if it's a known configurable constant
    if name in _DEFAULTS:
        env_key = f"ENVO_{name}"
        if env_key in os.environ:
            value = _coerce_config_value(name, os.environ[env_key])
            return value
        return _DEFAULTS[name]
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List all available constants for tab completion and introspection."""
    immutable = ["DEFAULT_ENV_FILE", "DEFAULT_SPEC_FILES", "ENVO_EXTENDS", 
                 "ENVO_EXTENDED_BY", "ENVO_SPECIAL_KEYS"]
    return immutable + list(_DEFAULTS.keys())


def get_default(name: str) -> Any:
    """
    Get the hardcoded default value for a constant, ignoring any env overrides.
    """
    if name in _DEFAULTS:
        return _DEFAULTS[name]
    raise KeyError(f"Unknown constant: {name}")


def get_all_defaults() -> dict[str, Any]:
    """Get a copy of all default values (parsing + display)."""
    return _DEFAULTS.copy()


def get_parsing_defaults() -> dict[str, Any]:
    """Get a copy of parsing-related default values."""
    return _PARSING_DEFAULTS.copy()


def get_display_defaults() -> dict[str, Any]:
    """Get a copy of display-related default values."""
    return _DISPLAY_DEFAULTS.copy()


def get_env_key(name: str) -> str:
    """Get the environment variable key for a constant (e.g., "DEFAULT_GROUP" -> "ENVO_DEFAULT_GROUP")."""
    return f"ENVO_{name}"


def is_immutable(name: str) -> bool:
    """Check if a constant is immutable (cannot be overridden)."""
    return name in ("DEFAULT_ENV_FILE", "DEFAULT_SPEC_FILES", "ENVO_EXTENDS", 
                    "ENVO_EXTENDED_BY", "ENVO_SPECIAL_KEYS")


