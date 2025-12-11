"""
CLI tools for envo.

Commands:
    envo show      - Load and display environment variables
    envo validate  - Validate an .env file against a spec
"""

import argparse
import os
import re
import sys

from termite import subprint

from envo.env import Env, find_default_spec, find_default_env
from envo.load import load_env_raw
from envo.parse_spec import env_file_to_spec
import envo.consts as consts


def _escape_brackets(text: str) -> str:
    """Escape brackets in text to prevent termite from interpreting them as style codes."""
    return str(text).replace("[", "[[").replace("]", "]]")


def _get_value_style(value) -> str:
    """Get the appropriate style name for a value based on its type."""
    if value is None:
        return f"rgb[{consts.VALUE_COLOR_DIM}]"
    if isinstance(value, bool):
        color = consts.VALUE_COLOR_GREEN if value else consts.VALUE_COLOR_RED
        return f"rgb[{color}]"
    if isinstance(value, (int, float)):
        return f"rgb[{consts.VALUE_COLOR_YELLOW}]"
    if isinstance(value, str):
        if '/' in value or value.startswith('~'):
            return f"rgb[{consts.VALUE_COLOR_BLUE}]"
    # For white/default, use termite's WHITE style
    return "WHITE"


def _get_key_style(status: str) -> str:
    """Get the style for a key based on its status."""
    if status == consts.KEY_STATUS_DEFAULT:
        return f"rgb[{consts.KEY_COLOR_DEFAULT}]"
    elif status == consts.KEY_STATUS_VALID:
        return f"BOLD+rgb[{consts.KEY_COLOR_VALID}]"
    elif status == consts.KEY_STATUS_INVALID:
        return f"BOLD+rgb[{consts.KEY_COLOR_INVALID}]"
    elif status == consts.KEY_STATUS_EXTRA:
        return f"rgb[{consts.KEY_COLOR_EXTRA}]"
    else:
        return f"BOLD+rgb[{consts.KEY_COLOR_DEFAULT_VALUE}]"


def print_key_value(key: str, value, export: bool = False, value_only: bool = False, 
                    docs: str = None, key_status: str = None, no_color: bool = False):
    """Print a key-value pair with optional colors."""
    if key_status is None:
        key_status = consts.KEY_STATUS_VALID
    
    # Build docs suffix
    docs_text = ""
    if docs and docs != consts.DEFAULT_DOCS:
        docs_text = f"  # {docs}"
    
    if no_color:
        # Plain text output
        if value_only:
            print(value if value is not None else "")
        elif export:
            if value is None:
                print(f"export {key}={docs_text}")
            elif isinstance(value, str):
                escaped = value.replace("'", "'\"'\"'")
                print(f"export {key}='{escaped}'{docs_text}")
            else:
                print(f"export {key}={value}{docs_text}")
        else:
            if value is None:
                print(f"{key}={docs_text}")
            else:
                print(f"{key}={value}{docs_text}")
        return
    
    escaped_value = _escape_brackets(value) if value is not None else ""
    value_style = _get_value_style(value)
    key_style = _get_key_style(key_status)
    
    # Build colored docs suffix
    docs_suffix = ""
    if docs and docs != consts.DEFAULT_DOCS:
        escaped_docs = _escape_brackets(docs)
        docs_suffix = f" DIM[# {escaped_docs}]"
    
    if value_only:
        if value is None:
            print("")
        else:
            subprint(f"{value_style}[{escaped_value}]{docs_suffix}")
        return
    
    escaped_key = _escape_brackets(key)
    
    if export:
        # Shell export format
        if value is None:
            subprint(f"DIM[export ]{key_style}[{escaped_key}]DIM[=]{docs_suffix}")
        elif isinstance(value, str):
            escaped = value.replace("'", "'\"'\"'")
            escaped_val = _escape_brackets(escaped)
            subprint(f"DIM[export ]{key_style}[{escaped_key}]DIM[=]{value_style}['{escaped_val}']{docs_suffix}")
        else:
            subprint(f"DIM[export ]{key_style}[{escaped_key}]DIM[=]{value_style}[{escaped_value}]{docs_suffix}")
    else:
        # Default KEY=value format
        if value is None:
            subprint(f"{key_style}[{escaped_key}]DIM[=]{docs_suffix}")
        else:
            subprint(f"{key_style}[{escaped_key}]DIM[=]{value_style}[{escaped_value}]{docs_suffix}")


def cmd_show(args):
    """Load and display environment variables."""
    from envo.load import load_single_env_raw
    from envo.spec_type import parse_spec
    
    # FIRST: Load raw env values and sync ENVO_* settings to os.environ
    # This MUST happen before anything else accesses consts
    raw_from_file = {}
    if args.env_file:
        for ef in args.env_file:
            raw_from_file.update(load_single_env_raw(ef) or {})
    else:
        default_env = find_default_env()
        if default_env:
            raw_from_file = load_single_env_raw(str(default_env)) or {}
    
    # Sync ENVO_* display settings to os.environ so consts picks them up
    for env_key, value in raw_from_file.items():
        if env_key.startswith("ENVO_") and value is not None:
            os.environ[env_key] = str(value)
    
    # Load spec first (for validation checking)
    spec = None
    spec_path = args.spec
    if not spec_path:
        default_spec = find_default_spec()
        if default_spec:
            spec_path = str(default_spec)
    
    if spec_path:
        try:
            spec = env_file_to_spec(spec_path)
        except FileNotFoundError:
            subprint(f"BOLD+RED[Error:] Spec file not found: {_escape_brackets(spec_path)}", file=sys.stderr)
            return 1
    
    # Handle --list-groups
    if args.list_groups:
        if not spec:
            subprint("BOLD+RED[Error:] No spec file found. Provide --spec or create sample.env/.env.sample", file=sys.stderr)
            return 1
        
        # Collect all groups from the spec
        groups = set()
        for var_spec in spec.values():
            if var_spec.groups:
                groups.update(var_spec.groups)
        
        if not groups:
            subprint("DIM[No groups defined in spec]", file=sys.stderr)
            return 0
        
        for group in sorted(groups):
            if args.no_color:
                print(group)
            else:
                subprint(f"MAGENTA[{_escape_brackets(group)}]")
        return 0
    
    # Build Env with validation disabled (we'll check validity ourselves for display)
    # Create a spec without validators for loading
    loading_spec = None
    if spec:
        # Create a copy of spec without validators
        loading_spec = {}
        from envo.spec_type import VariableSpec, parse_spec_key
        for k, v in spec.items():
            new_spec = VariableSpec(
                groups=v.groups,
                docs=v.docs,
                type=v.type,
                default=v.default,
                required=v.required,
                # Omit validator to prevent load-time errors
            )
            loading_spec[k] = new_spec
        # Add catch-all for extra keys
        loading_spec[parse_spec_key("*")] = VariableSpec()
    
    try:
        env = Env(
            *(args.env_file or []),  # Empty = auto-discover
            spec=loading_spec if loading_spec else ("auto" if not args.spec else args.spec),
            existing_env_priority="none" if args.no_system else "highest",
            export_to_environ=False,  # Don't export since we're just showing
        )
    except FileNotFoundError as e:
        subprint(f"BOLD+RED[Error:] {_escape_brackets(str(e))}", file=sys.stderr)
        return 1
    
    # Filter by group if specified
    if args.group:
        env = env.get_group(args.group)
        if not env:
            subprint(f"YELLOW[No variables found in group:] MAGENTA[{_escape_brackets(args.group)}]", file=sys.stderr)
            return 0
    
    # Get keys to print
    if args.key:
        # Check if key contains wildcards
        if '*' in args.key or '?' in args.key:
            # Convert glob pattern to regex
            import fnmatch
            pattern = fnmatch.translate(args.key)
            regex = re.compile(pattern)
            keys = [k for k in sorted(env.keys()) if regex.match(k)]
            if not keys:
                subprint(f"YELLOW[No variables matching pattern:] DIM[{_escape_brackets(args.key)}]", file=sys.stderr)
                return 0
        else:
            # Single key lookup
            keys = [args.key]
    elif args.grep:
        # Filter keys by pattern
        pattern = re.compile(args.grep, re.IGNORECASE if args.ignore_case else 0)
        keys = [k for k in sorted(env.keys()) if pattern.search(k)]
        if not keys:
            subprint(f"YELLOW[No variables matching:] DIM[{_escape_brackets(args.grep)}]", file=sys.stderr)
            return 0
    else:
        # All keys
        keys = sorted(env.keys())
    
    # Filter to only explicitly specified keys (not fallback matches) unless --all
    if spec and not getattr(args, 'all', False) and not args.key:
        explicit_keys = env.spec.filter_explicit(keys)
        if not explicit_keys and keys:
            # No explicit keys but we have keys - show message
            subprint(f"DIM[No explicitly specified variables. Use --all to see all {len(keys)} variables.]", file=sys.stderr)
            return 0
        keys = explicit_keys
    
    # Print output
    is_glob_pattern = args.key and ('*' in args.key or '?' in args.key)
    for key in keys:
        if key not in env:
            if args.key and not is_glob_pattern:
                subprint(f"BOLD+RED[Error:] {_escape_brackets(key)} not found", file=sys.stderr)
                return 1
            continue
        
        value = env.get(key)
        
        # Determine key status
        key_status = consts.KEY_STATUS_VALID
        
        # Check if key has explicit spec (use original spec with validators)
        has_explicit = spec and spec.has_explicit_spec(key) if spec else False
        
        if not has_explicit:
            # Extra key not in spec
            key_status = consts.KEY_STATUS_EXTRA
        elif key not in raw_from_file or raw_from_file.get(key) is None:
            # Value came from spec default (not in file or was empty)
            key_status = consts.KEY_STATUS_DEFAULT
        else:
            # Value was specified - check if it's valid using original spec
            try:
                if spec:
                    var_spec = spec[key]
                    if var_spec.validator:
                        var_spec.validator(value)
                key_status = consts.KEY_STATUS_VALID
            except Exception:
                key_status = consts.KEY_STATUS_INVALID
        
        # Get docs if requested
        docs_text = None
        if args.docs and spec:
            try:
                var_spec = env.spec[key]
                docs_text = var_spec.docs
            except KeyError:
                pass
        
        if args.json:
            # JSON format (no colors)
            import json
            if args.docs and docs_text:
                print(json.dumps({key: value, "_docs": docs_text, "_status": key_status}))
            else:
                print(json.dumps({key: value, "_status": key_status}))
        else:
            print_key_value(key, value, export=args.export, value_only=args.value_only, 
                          docs=docs_text, key_status=key_status, no_color=args.no_color)
    
    return 0


def cmd_config(args):
    """Run the interactive configuration editor."""
    from envo.interactive_config import run_interactive_config
    
    return run_interactive_config(
        key=args.key,
        group=args.group,
        grep=args.grep,
        ignore_case=args.ignore_case,
        all_vars=args.all_vars,
        env_file=args.env_file,
        spec=args.spec,
        no_system=args.no_system,
        dst=args.dst,
    )


def cmd_validate(args):
    """Validate an .env file against a spec."""
    # Determine paths - use defaults if not specified
    env_path = args.env_file
    if not env_path:
        default_env = find_default_env()
        if default_env:
            env_path = str(default_env)
        else:
            subprint("BOLD+RED[Error:] No .env file found in project root", file=sys.stderr)
            return 1
    
    spec_path = args.spec
    if not spec_path:
        default_spec = find_default_spec()
        if default_spec:
            spec_path = str(default_spec)
        else:
            subprint("BOLD+RED[Error:] No spec file found. Provide --spec or create sample.env/.env.sample", file=sys.stderr)
            return 1
    
    # Load spec
    try:
        spec = env_file_to_spec(spec_path)
    except FileNotFoundError:
        subprint(f"BOLD+RED[Error:] Spec file not found: {_escape_brackets(spec_path)}", file=sys.stderr)
        return 1
    except Exception as e:
        subprint(f"BOLD+RED[Error loading spec:] {_escape_brackets(str(e))}", file=sys.stderr)
        return 1
    
    # Load raw env values (without resolving references, so we can detect them)
    from envo.load import load_single_env_raw
    try:
        # Load without reference resolution to detect which vars are used as references
        raw_values_unresolved = load_single_env_raw(env_path)
        raw_values = load_env_raw(env_path, existing_env_priority="none")
    except FileNotFoundError:
        subprint(f"BOLD+RED[Error:] Env file not found: {_escape_brackets(env_path)}", file=sys.stderr)
        return 1
    except Exception as e:
        subprint(f"BOLD+RED[Error loading env file:] {_escape_brackets(str(e))}", file=sys.stderr)
        return 1
    
    errors = []
    warnings = []
    
    # Find all referenced variables (used as $VAR in values) - check BEFORE resolution
    referenced_vars = set()
    ref_char = re.escape(consts.REF_CHAR)
    ref_pattern = rf'{ref_char}([A-Za-z_][A-Za-z0-9_]*)'
    for value in raw_values_unresolved.values():
        if value and consts.REF_CHAR in value:
            referenced_vars.update(re.findall(ref_pattern, value))
    
    # Check for missing required keys
    for key in spec.list_required():
        if key not in raw_values:
            errors.append(("missing_required", key, "Missing required variable"))
        elif raw_values[key] is None or raw_values[key] == "":
            errors.append(("empty_required", key, "Required variable is empty"))
    
    # Check each value in the env file
    for key, raw_value in raw_values.items():
        # Skip special ENVO keys
        if key in consts.ENVO_SPECIAL_KEYS:
            continue
        
        # Check if key is in spec
        try:
            var_spec = spec[key]
        except KeyError:
            # Key not in spec - check if it's used as a reference
            if key in referenced_vars:
                # It's used as a reference, just warn
                warnings.append(("extra_ref", key, "Extra variable (used as reference)"))
            elif args.strict:
                errors.append(("extra_strict", key, "Extra variable not in spec"))
            else:
                warnings.append(("extra", key, "Extra variable not in spec"))
            continue
        
        # Skip <default> values - they'll use spec defaults
        if raw_value == consts.USE_SPEC_DEFAULT:
            continue
        
        # Skip None/empty values for non-required vars
        if raw_value is None or raw_value == "":
            continue
        
        # Try to validate the value
        try:
            # Create a temporary Env to validate this single value
            temp_env = Env(raw={key: raw_value}, spec=spec, existing_env_priority="none")
            _ = temp_env[key]  # This triggers validation
        except Exception as e:
            errors.append(("invalid", key, f"Invalid value: {e}"))
    
    # Check for missing keys that have no default
    for key, var_spec in spec.items():
        if isinstance(key, str) and key not in raw_values:
            if var_spec.required:
                # Already handled above
                pass
            elif var_spec.default is None and not args.ignore_missing:
                warnings.append(("no_default", key, "Variable not set (no default)"))
    
    # Print results
    print()
    
    if errors:
        subprint(f"BOLD+RED[✗ ERRORS] DIM[({len(errors)})]", file=sys.stderr)
        for err_type, key, msg in errors:
            escaped_key = _escape_brackets(key)
            escaped_msg = _escape_brackets(msg)
            subprint(f"  RED[•] BOLD+CYAN[{escaped_key}] DIM[-] RED[{escaped_msg}]", file=sys.stderr)
    
    if warnings and args.show_warnings:
        if errors:
            print(file=sys.stderr)
        subprint(f"BOLD+YELLOW[⚠ WARNINGS] DIM[({len(warnings)})]", file=sys.stderr)
        for warn_type, key, msg in warnings:
            escaped_key = _escape_brackets(key)
            escaped_msg = _escape_brackets(msg)
            subprint(f"  YELLOW[•] BOLD+CYAN[{escaped_key}] DIM[-] YELLOW[{escaped_msg}]", file=sys.stderr)
    
    print(file=sys.stderr)
    
    if not errors:
        subprint("BOLD+GREEN[✓ Validation passed!]", file=sys.stderr)
        if warnings and not args.show_warnings:
            subprint(f"  DIM[({len(warnings)} warnings, use --warnings to see)]", file=sys.stderr)
        return 0
    else:
        subprint(f"BOLD+RED[✗ Validation failed] DIM[({len(errors)} error(s))]", file=sys.stderr)
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="envo",
        description="Environment variable loading and validation utility",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # === show command ===
    show_parser = subparsers.add_parser(
        "show",
        help="Load and display environment variables",
    )
    show_parser.add_argument(
        "key",
        nargs="?",
        help="Variable name or glob pattern (e.g., 'DB_*', 'API_???_KEY')",
    )
    show_parser.add_argument(
        "-e", "--env-file",
        action="append",
        help="Env file(s) to load (default: .env)",
    )
    show_parser.add_argument(
        "-s", "--spec",
        help="Spec file for type coercion (default: sample.env or .env.sample)",
    )
    show_parser.add_argument(
        "-g", "--group",
        help="Filter by group name",
    )
    show_parser.add_argument(
        "--grep",
        help="Filter keys by regex pattern",
    )
    show_parser.add_argument(
        "-i", "--ignore-case",
        action="store_true",
        help="Case-insensitive grep",
    )
    show_parser.add_argument(
        "--export",
        action="store_true",
        help="Print in 'export KEY=VALUE' format for shell sourcing",
    )
    show_parser.add_argument(
        "-v", "--value-only",
        action="store_true",
        help="Print only the value (useful with single key)",
    )
    show_parser.add_argument(
        "--json",
        action="store_true",
        help="Print in JSON format",
    )
    show_parser.add_argument(
        "--no-system",
        action="store_true",
        help="Don't include system environment variables",
    )
    show_parser.add_argument(
        "-a", "--all",
        action="store_true",
        help="Show all variables (including those only matching fallback patterns)",
    )
    show_parser.add_argument(
        "-d", "--docs",
        action="store_true",
        help="Show documentation for each variable as inline comment",
    )
    show_parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    show_parser.add_argument(
        "--list-groups",
        action="store_true",
        help="List all available groups defined in the spec",
    )
    show_parser.set_defaults(func=cmd_show)
    
    # === validate command ===
    validate_parser = subparsers.add_parser(
        "validate",
        aliases=["v", "check"],
        help="Validate an .env file against a spec",
    )
    validate_parser.add_argument(
        "env_file",
        nargs="?",
        help="Env file to validate (default: .env)",
    )
    validate_parser.add_argument(
        "-s", "--spec",
        help="Spec file to validate against (default: sample.env or .env.sample)",
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat extra variables as errors (not warnings)",
    )
    validate_parser.add_argument(
        "-w", "--warnings", "--show-warnings",
        dest="show_warnings",
        action="store_true",
        help="Show warnings in output",
    )
    validate_parser.add_argument(
        "--ignore-missing",
        action="store_true",
        help="Don't warn about missing optional variables",
    )
    validate_parser.set_defaults(func=cmd_validate)
    
    # === config command ===
    config_parser = subparsers.add_parser(
        "config",
        help="Interactive configuration editor for environment variables",
    )
    config_parser.add_argument(
        "key",
        nargs="?",
        help="Variable name or glob pattern to filter (e.g., 'DB_*', 'API_???_KEY')",
    )
    config_parser.add_argument(
        "-e", "--env-file",
        action="append",
        help="Env file(s) to load (default: .env)",
    )
    config_parser.add_argument(
        "-s", "--spec",
        help="Spec file for type coercion (default: sample.env or .env.sample)",
    )
    config_parser.add_argument(
        "-g", "--group",
        help="Filter by group name",
    )
    config_parser.add_argument(
        "--grep",
        help="Filter keys by regex pattern",
    )
    config_parser.add_argument(
        "-i", "--ignore-case",
        action="store_true",
        help="Case-insensitive grep",
    )
    config_parser.add_argument(
        "--no-system",
        action="store_true",
        help="Don't include system environment variables",
    )
    config_parser.add_argument(
        "-a", "--all",
        action="store_true",
        dest="all_vars",
        help="Show all variables (including those only matching fallback patterns)",
    )
    config_parser.add_argument(
        "--dst",
        help="Destination file to save changes to (default: .env in project root)",
    )
    config_parser.set_defaults(func=cmd_config)
    
    # Parse args
    args = parser.parse_args()
    
    if not args.command:
        # Default to print command behavior for backwards compatibility
        # Re-parse with print as default
        args = parser.parse_args(["print"] + sys.argv[1:])
    
    # Run the command
    if hasattr(args, 'func'):
        sys.exit(args.func(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

