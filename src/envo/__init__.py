"""
Environment variable loading utility.

Loads environment variables with priority (lowest to highest):
1. .env.sample (defaults)
2. .env or --env-file (user overrides)
3. System environment variables (already in os.environ)
4. Command-line arguments (highest priority, handled by argparse)

Note: System environment variables are checked first, so they override file-based values.
Command-line arguments are parsed after env loading, so they have highest priority.

Configuration:
    Most settings can be customized via ENVO_* environment variables.
    For dynamic access, use: import envo.consts as consts
    
    See envo.consts for the complete list of configurable options.
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

# Export the consts module for dynamic access
from . import consts

# Export immutable constants (these cannot be overridden)
from .consts import (
    DEFAULT_ENV_FILE,
    DEFAULT_SPEC_FILES,
    ENVO_EXTENDS,
    ENVO_EXTENDED_BY,
    ENVO_SPECIAL_KEYS,
)

# Export helper functions for configuration introspection
from .consts import (
    get_default,
    get_all_defaults,
    get_parsing_defaults,
    get_display_defaults,
    get_env_key,
    is_immutable,
    clear_cache,
)


if __name__ == "__main__":
    main()
