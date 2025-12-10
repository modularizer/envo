"""
Load environment variables from files.
"""
import os
from pathlib import Path
from typing import Literal



def load_env_raw(*env_paths: str | Literal["os.environ"] | Path,
                 existing_env_priority: Literal["none", "highest", "lowest"] | None = None,
                 cwd = None) -> dict[str, str]:
    """
    Load environment variables from one or more locations, lowest priority to highest priority.

    paths can be pathnames (~ gets resolved), "os.environ", or empty

    e.g.
    >>> load_env_raw(".env.sample", ".env", "os.environ")
    """
    if not env_paths:
        env_paths = (".env",)
    if existing_env_priority == "highest":
        env_paths = (*env_paths, "os.environ")
    if existing_env_priority == "lowest":
        env_paths = ("os.environ", *env_paths)
    env = {}
    for p in env_paths:
        env.update(load_single_env_raw(p, cwd=cwd))
    return resolve_var_references(env)




def load_single_env_raw(env_path: str | Path | None, cwd = None) -> dict[str, str]:
    if not env_path:
        return {}
    if env_path == "os.environ":
        return os.environ
    env_path = resolve_relative(env_path, cwd=cwd)
    if not env_path.exists():
        return {}

    result = {}
    
    for line in env_path.read_text().splitlines():
        line = line.strip()
        # Skip empty lines and lines that start with # (full-line comments)
        if not line or line.startswith("#"):
            continue
        
        # Parse KEY=VALUE
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            
            # Remove inline comments
            value = remove_inline_comments(value)
            
            # Remove quotes if present
            value = remove_quotes(value)
            
            # Normalize None/null values
            value = normalize_none_value(value)
            
            # Store as raw string - NO substitutions yet
            # All substitutions happen in resolve module
            
            if key:
                result[key] = value
    
    return result


def resolve_relative(x: str | Path, cwd: str | Path | None = None) -> Path:
    x = Path(x).expanduser()

    if cwd is not None:
        cwd = Path(cwd).expanduser()
    else:
        cwd = Path.cwd()

    # absolute path → resolve normally
    if x.is_absolute():
        return x.resolve()

    # relative path → resolve relative to cwd
    return (cwd / x).resolve()


def resolve_var_references(env_dict: dict[str, str]) -> dict[str, str]:
    """
    Resolve $VAR_NAME references in environment variables.

    Performs multiple passes until no more substitutions are made,
    with a maximum iteration limit to prevent infinite loops.

    Args:
        env_dict: Dictionary of environment variables

    Returns:
        Dictionary with variable references resolved
    """
    import re
    pattern = r'\$([A-Za-z_][A-Za-z0-9_]*)'
    result = env_dict.copy()

    max_iterations = 20
    for iteration in range(max_iterations):
        changed = False
        for key, value in result.items():
            if '$' in value:
                def replace_var(match):
                    var_name = match.group(1)
                    # Don't reference self to avoid infinite loops
                    if var_name == key:
                        return match.group(0)
                    return result.get(var_name, match.group(0))

                new_value = re.sub(pattern, replace_var, value)
                if new_value != value:
                    result[key] = new_value
                    changed = True

        if not changed:
            # No more substitutions needed
            break

    return result




def normalize_none_value(value: str) -> str:
    """
    Normalize various representations of None/null to empty string.

    Args:
        value: String value to normalize

    Returns:
        Empty string if value represents None/null, otherwise original value
    """
    normalized = value.strip().lower()
    if normalized in ("none", "null", "none", ""):
        return ""
    return value


def remove_inline_comments(value: str) -> str:
    """
    Remove inline comments from a value (everything after #, but preserve # in quoted strings).

    Args:
        value: String value that may contain inline comments

    Returns:
        Value with inline comments removed
    """
    if "#" not in value:
        return value

    # Check if # is inside quotes
    in_quotes = False
    quote_char = None
    comment_start = -1
    for i, char in enumerate(value):
        if char in ('"', "'") and (i == 0 or value[i-1] != '\\'):
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                quote_char = None
        elif char == '#' and not in_quotes:
            comment_start = i
            break

    if comment_start >= 0:
        return value[:comment_start].strip()

    return value


def remove_quotes(value: str) -> str:
    """
    Remove surrounding quotes from a value if present.

    Args:
        value: String value that may be quoted

    Returns:
        Value with quotes removed
    """
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    elif value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value
