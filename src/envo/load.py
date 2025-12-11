"""
Load environment variables from files.

Supports multiple file formats:
- .env files (KEY=VALUE format)
- .json files
- .yaml/.yml files (requires PyYAML)
- .toml files (requires tomli for Python < 3.11)

Special ENVO keys for file chaining:
- ENVO_EXTENDS: Load another file with LOWER priority (current file overrides it)
- ENVO_EXTENDED_BY: Load another file with HIGHER priority (it overrides current file)
"""
import json
import os
from pathlib import Path
from typing import Literal

import envo.consts as consts


def _load_yaml(path: Path) -> dict:
    """Load a YAML file. Requires PyYAML."""
    import yaml
    return yaml.safe_load(path.read_text()) or {}


def _load_toml(path: Path) -> dict:
    """Load a TOML file. Uses tomllib (3.11+) or tomli."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        import tomli as tomllib  # Python < 3.11
    return tomllib.loads(path.read_text()) or {}


def _flatten_dict(d: dict, parent_key: str = '', sep: str = '_') -> dict[str, str | None]:
    """
    Flatten a nested dictionary into a flat dict with joined keys.
    
    Example:
        {"database": {"host": "localhost", "port": 5432}}
        -> {"DATABASE_HOST": "localhost", "DATABASE_PORT": "5432"}
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}".upper() if parent_key else k.upper()
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep).items())
        elif v is None:
            items.append((new_key, None))
        elif isinstance(v, bool):
            items.append((new_key, str(v).lower()))
        elif isinstance(v, (list, tuple)):
            items.append((new_key, json.dumps(v)))
        else:
            items.append((new_key, str(v)))
    return dict(items)


def _get_file_type(path: Path) -> str:
    """Determine file type from extension."""
    suffix = path.suffix.lower()
    if suffix in ('.yaml', '.yml'):
        return 'yaml'
    elif suffix == '.json':
        return 'json'
    elif suffix == '.toml':
        return 'toml'
    else:
        return 'env'



def load_env_raw(*env_paths: str | Literal["os.environ"] | Path,
                 existing_env_priority: Literal["none", "highest", "lowest"] | None = "highest",
                 cwd = None) -> dict[str, str | None]:
    """
    Load environment variables from one or more locations, lowest priority to highest priority.

    paths can be pathnames (~ gets resolved), "os.environ", or empty
    
    Values are:
        - None: variable is defined but empty (VAR=)
        - "": variable is explicitly empty string (VAR="")
        - str: variable has a value

    e.g.
    >>> load_env_raw(".env.sample", ".env", "os.environ")
    """
    if not env_paths:
        env_paths = (".env",)
    if "os.environ" not in env_paths:
        if existing_env_priority == "highest":
            env_paths = (*env_paths, "os.environ")
        if existing_env_priority == "lowest":
            env_paths = ("os.environ", *env_paths)
    env = {}
    for p in env_paths:
        env.update(load_single_env_raw(p, cwd=cwd))
    return resolve_var_references(env)




def load_single_env_raw(
    env_path: str | Path | None, 
    cwd=None, 
    flatten: bool = True,
    _loaded_files: set[Path] | None = None,
) -> dict[str, str | None]:
    """
    Load environment variables from a single file.
    
    Supports:
        - .env files (KEY=VALUE format)
        - .json files
        - .yaml/.yml files
        - .toml files
    
    Special ENVO keys:
        - ENVO_EXTENDS: Load another file with lower priority
        - ENVO_EXTENDED_BY: Load another file with higher priority
    
    Args:
        env_path: Path to the file, or "os.environ"
        cwd: Working directory for relative paths
        flatten: If True, flatten nested dicts (JSON/YAML/TOML) into KEY_SUBKEY format
        _loaded_files: Internal set to track loaded files and prevent circular references
        
    Returns:
        Dictionary of environment variables (without ENVO_* special keys)
    """
    if not env_path:
        return {}
    if env_path == "os.environ":
        return dict(os.environ)
    
    env_path = resolve_relative(env_path, cwd=cwd)
    if not env_path.exists():
        return {}
    
    # Track loaded files to prevent circular references
    if _loaded_files is None:
        _loaded_files = set()
    
    if env_path in _loaded_files:
        # Already loaded this file, skip to prevent infinite loop
        return {}
    _loaded_files.add(env_path)

    # Load the file content
    file_type = _get_file_type(env_path)
    
    if file_type == 'json':
        current = _load_structured_file(env_path, json.loads, flatten)
    elif file_type == 'yaml':
        current = _load_structured_file(env_path, lambda s: _load_yaml(env_path), flatten)
    elif file_type == 'toml':
        current = _load_structured_file(env_path, lambda s: _load_toml(env_path), flatten)
    else:
        current = _load_dotenv_file(env_path)
    
    # Process ENVO_EXTENDS (lower priority - load first, then current overrides)
    extends_path = current.get(consts.ENVO_EXTENDS)
    if extends_path:
        # Resolve relative to the current file's directory
        extends_resolved = resolve_relative(extends_path, cwd=env_path.parent)
        base = load_single_env_raw(extends_resolved, cwd=env_path.parent, flatten=flatten, _loaded_files=_loaded_files)
        # Current overrides base
        base.update(current)
        current = base
    
    # Process ENVO_EXTENDED_BY (higher priority - load after, it overrides current)
    extended_by_path = current.get(consts.ENVO_EXTENDED_BY)
    if extended_by_path:
        # Resolve relative to the current file's directory
        extended_by_resolved = resolve_relative(extended_by_path, cwd=env_path.parent)
        override = load_single_env_raw(extended_by_resolved, cwd=env_path.parent, flatten=flatten, _loaded_files=_loaded_files)
        # Override takes precedence over current
        current.update(override)
    
    # Remove special ENVO keys from result
    for key in consts.ENVO_SPECIAL_KEYS:
        current.pop(key, None)
    
    return current


def _load_structured_file(path: Path, loader, flatten: bool = True) -> dict[str, str | None]:
    """Load a structured file (JSON/YAML/TOML) as environment variables."""
    content = path.read_text()
    data = loader(content)
    
    if not isinstance(data, dict):
        raise ValueError(f"Expected a dictionary at root level in {path}")
    
    if flatten:
        return _flatten_dict(data)
    else:
        # Convert values to strings without flattening
        result = {}
        for k, v in data.items():
            if v is None:
                result[k] = None
            elif isinstance(v, bool):
                result[k] = str(v).lower()
            elif isinstance(v, (dict, list)):
                result[k] = json.dumps(v)
            else:
                result[k] = str(v)
        return result


def _load_dotenv_file(env_path: Path) -> dict[str, str | None]:
    """Load a traditional .env file."""
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
            
            # Remove inline comments (before parsing value)
            value = remove_inline_comments(value)
            
            # Parse value - distinguishes None vs empty string
            # VAR= -> None
            # VAR="" -> ""
            # VAR=foo -> "foo"
            parsed_value = parse_env_value(value)
            
            # Store the parsed value
            if key:
                result[key] = parsed_value
    
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


def resolve_var_references(env_dict: dict[str, str | None]) -> dict[str, str | None]:
    """
    Resolve $VAR_NAME references in environment variables.

    Performs multiple passes until no more substitutions are made,
    with a maximum iteration limit to prevent infinite loops.
    
    None values are preserved (not substituted).

    Args:
        env_dict: Dictionary of environment variables

    Returns:
        Dictionary with variable references resolved
    """
    import re
    pattern = r'\$([A-Za-z_][A-Za-z0-9_]*)'
    result = env_dict.copy()

    for iteration in range(consts.VAR_REFERENCE_MAX_ITERATIONS):
        changed = False
        for key, value in result.items():
            # Skip None values
            if value is None:
                continue
            if '$' in value:
                def replace_var(match):
                    var_name = match.group(1)
                    # Don't reference self to avoid infinite loops
                    if var_name == key:
                        return match.group(0)
                    ref_val = result.get(var_name)
                    # If referenced value is None, keep the reference as-is
                    if ref_val is None:
                        return match.group(0)
                    return ref_val

                new_value = re.sub(pattern, replace_var, value)
                if new_value != value:
                    result[key] = new_value
                    changed = True

        if not changed:
            # No more substitutions needed
            break

    return result




def normalize_none_value(value: str) -> str | None:
    """
    Normalize various representations of None/null to None.

    Args:
        value: String value to normalize

    Returns:
        None if value represents None/null, otherwise original value
    """
    normalized = value.strip().lower()
    if normalized in consts.NULL_VALUES:
        return None
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
    
    Preserves the distinction between:
    - "" or '' -> returns "" (explicit empty string)
    - unquoted empty -> returns "" (caller handles None conversion)

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


def parse_env_value(value: str) -> str | None:
    """
    Parse an environment variable value, distinguishing empty vs None.
    
    - Empty with no quotes: returns None
    - Explicit empty quotes ("" or ''): returns ""
    - Any other value: returns the value (with quotes removed if quoted)
    
    Args:
        value: Raw value string (after inline comment removal)
        
    Returns:
        Parsed value, or None if empty/unset
    """
    value = value.strip()
    
    if not value:
        # Nothing there -> None
        return None
    
    # Check if it's quoted
    if (value.startswith('"') and value.endswith('"')) or \
       (value.startswith("'") and value.endswith("'")):
        # Remove quotes - "" becomes "", "foo" becomes "foo"
        return value[1:-1]
    
    # Check for none/null literals (case insensitive)
    if value.lower() in ("none", "null"):
        return None
    
    return value
