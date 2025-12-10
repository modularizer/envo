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
from .cli import main


if __name__ == "__main__":
    main()
