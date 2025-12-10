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
import argparse

from .env import env, Env, USE_SPEC_DEFAULT
from .load import ENVO_EXTENDS, ENVO_EXTENDED_BY
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


def main():
    """CLI entry point for envo - prints loaded environment variables."""
    parser = argparse.ArgumentParser(
        description="Load and display environment variables from .env files"
    )
    parser.add_argument(
        "key",
        nargs="?",
        default=None,
        help="Optional key to look up. If not provided, prints all variables.",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Print in 'export KEY=VALUE' format for shell sourcing",
    )

    args = parser.parse_args()

    if args.key:
        value = env.get(args.key, "")
        print(value)
    else:
        for key in sorted(env):
            value = env.get(key)
            if args.export:
                print(f"export {key}={value!r}")
            else:
                print(f"{key}={value}")


if __name__ == "__main__":
    main()
