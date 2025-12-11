"""
Environment variable loading utility.

Loads environment variables with priority (lowest to highest):
1. .env.sample (defaults)
2. .env or --env-file (user overrides)
3. System environment variables (already in os.environ)
4. Command-line arguments (highest priority, handled by argparse)

Note: System environment variables are checked first, so they override file-based values.
Command-line arguments are parsed after env loading, so they have highest priority.
"""

from .env import env, Env, find_default_spec, find_default_env
from .coerce import *
from .parse_spec import (
    env_file_to_spec,
    env_file_to_defaults,
    env_file_to_docs,
    parse_env_file,
    ParsedVariable,
    ParsedGroup,
    print_spec_summary,
)
from .cli import main

# Export all constants for customization
from .consts import (
    # File names and paths
    DEFAULT_ENV_FILE,
    DEFAULT_SPEC_FILES,
    USE_SPEC_DEFAULT,
    # Special ENVO keys
    ENVO_EXTENDS,
    ENVO_EXTENDED_BY,
    ENVO_SPECIAL_KEYS,
    # Default values for specs
    DEFAULT_GROUP,
    DEFAULT_DOCS,
    # Boolean coercion values
    BOOL_TRUE_VALUES,
    BOOL_FALSE_VALUES,
    NULL_VALUES,
    # Key status constants
    KEY_STATUS_DEFAULT,
    KEY_STATUS_VALID,
    KEY_STATUS_INVALID,
    KEY_STATUS_EXTRA,
    # Color scheme - key colors
    KEY_COLOR_DEFAULT,
    KEY_COLOR_VALID,
    KEY_COLOR_INVALID,
    KEY_COLOR_EXTRA,
    KEY_COLOR_DEFAULT_VALUE,
    # Color scheme - value colors
    VALUE_COLOR_DIM,
    VALUE_COLOR_GREEN,
    VALUE_COLOR_RED,
    VALUE_COLOR_YELLOW,
    VALUE_COLOR_BLUE,
    VALUE_COLOR_WHITE,
    # Color scheme - UI colors
    HIGHLIGHT_BG_COLOR,
    UI_TEXT_DIM,
    # Color scheme - highlighted state
    KEY_COLOR_DEFAULT_HIGHLIGHT,
    KEY_COLOR_VALID_HIGHLIGHT,
    KEY_COLOR_INVALID_HIGHLIGHT,
    KEY_COLOR_EXTRA_HIGHLIGHT,
    KEY_COLOR_DEFAULT_VALUE_HIGHLIGHT,
    VALUE_COLOR_DIM_HIGHLIGHT,
    VALUE_COLOR_GREEN_HIGHLIGHT,
    VALUE_COLOR_RED_HIGHLIGHT,
    VALUE_COLOR_YELLOW_HIGHLIGHT,
    VALUE_COLOR_BLUE_HIGHLIGHT,
    VALUE_COLOR_WHITE_HIGHLIGHT,
    HIGHLIGHT_TEXT_COLOR_DIM,
    # UI text and formatting
    UI_SEPARATOR_CHAR,
    UI_SEPARATOR_WIDTH,
    UI_HELP_BROWSE,
    UI_HELP_EDIT,
    UI_NOT_SET,
    UI_VALID_PREFIX,
    UI_INVALID_PREFIX,
    UI_CHANGE_ARROW,
    # Variable reference resolution
    VAR_REFERENCE_MAX_ITERATIONS,
    PROJECT_ROOT_CHAR,
)


if __name__ == "__main__":
    main()
