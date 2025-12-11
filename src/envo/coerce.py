"""
Coerce environment variable values to specific types.
"""
import contextlib
import glob
import json
from pathlib import Path, PosixPath

from envo.consts import BOOL_TRUE_VALUES, BOOL_FALSE_VALUES, NULL_VALUES


def coerce_bool(value: str, default: bool = False) -> bool:
    """
    Coerce a string value to boolean.
    
    Lenient parsing:
    - True values: "true", "True", "TRUE", "1", "yes", "Yes", "YES", "on", "On", "ON", "y"
    - False values: "false", "False", "FALSE", "0", "no", "No", "NO", "off", "Off", "OFF", "n"
    - Empty/None values: returns default
    
    Args:
        value: String value to coerce
        default: Default value if empty/invalid
        
    Returns:
        Boolean value
    """
    if not value:
        return default
    
    # Case-insensitive comparison
    value_lower = value.lower()
    
    # True values
    if value_lower in BOOL_TRUE_VALUES:
        return True
    
    # False values
    if value_lower in BOOL_FALSE_VALUES:
        return False
    
    # If not recognized, return default
    return default


def coerce_int(value: str, default: int | None = None) -> int | None:
    """
    Coerce a string value to integer.
    
    Args:
        value: String value to coerce
        default: Default value if not found/invalid
        
    Returns:
        Integer value or default if not found/invalid
    """
    value = value.replace("_","")
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def coerce_float(value: str, default: float | None = None) -> float | None:
    """
    Coerce a string value to float.
    
    Args:
        value: String value to coerce
        default: Default value if not found/invalid
        
    Returns:
        Float value or default if not found/invalid
    """
    value = value.replace("_","")
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def coerce_path(value: str, cwd=None) -> Path:
    parts = value.split("|")
    if len(parts) > 1:
        for part in parts:
            p = coerce_path(part, cwd)
            if p.exists():
                return p
        return p
    p = Path(value.strip()).expanduser()
    if not p.is_absolute():
        cwd = Path(cwd).expanduser() if cwd is not None else Path.cwd()
        p = (cwd / p)
    return p.resolve()

def coerce_path_str(value: str, cwd=None) -> str:
    return str(coerce_path(value, cwd=cwd))


def coerce_glob(pattern: str, project_root: str | Path | None = None) -> str:
    """
    Resolve a glob pattern (expand ~, convert to absolute if relative).

    Note: % substitution is already done in apply_all_substitutions().

    Args:
        pattern: Glob pattern string (already has % substituted)
        project_root: Project root for relative path resolution

    Returns:
        Resolved glob pattern
    """
    project_root = Path(project_root or Path.cwd()).expanduser().resolve()


    # Expand ~
    pattern = str(Path(pattern).expanduser())

    # Convert relative paths to absolute (relative to project root)
    path_obj = Path(pattern)
    if not path_obj.is_absolute():
        # If it's a relative glob, make it absolute relative to project root
        # Preserve the glob pattern part
        if any(char in pattern for char in ['*', '?', '[']):
            # It's a glob pattern - find the directory part
            # Find the last / before the glob chars
            last_slash = max(
                (i for i, c in enumerate(pattern) if c == '/'),
                default=-1
            )
            if last_slash >= 0:
                # Has directory part
                dir_part = pattern[:last_slash + 1]
                glob_part = pattern[last_slash + 1:]
                resolved_dir = (project_root / dir_part).resolve()
                pattern = str(resolved_dir / glob_part)
            else:
                # No directory part, just glob pattern
                pattern = str((project_root / pattern).resolve())
        else:
            # Not a glob, just a regular path
            pattern = str((project_root / pattern).resolve())

    return pattern


def coerce_unknown(s: str | None, **kwargs):
    # None stays None
    if s is None:
        return None
    if not isinstance(s, str):
        return s
    try:
        # Only "null" and "none" literals become None, empty string stays empty
        if s.lower() in NULL_VALUES:
            return None
        # Empty string stays as empty string
        if s == "":
            return ""
        if s.lower() in BOOL_TRUE_VALUES | BOOL_FALSE_VALUES:
            return coerce_bool(s, **kwargs)
        if s.replace("_","").isdigit() or (s.startswith('-') and s[1:].replace("_","").isdigit()):
            return coerce_int(s, **kwargs)
        if s.count('.') == 1 and s.replace('.', '').replace('-', '').replace("_","").isdigit():
            return coerce_float(s, **kwargs)
        with contextlib.suppress(Exception):
            if all(Path(p.strip()).expanduser().exists() for p in s.split("|") if p.strip()):
                return coerce_path(s, **kwargs)
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            return json.loads(s, **kwargs)
        if "/" in s:
            return coerce_path_str(s, **kwargs)
        return s
    except:
        return s


def coerce(s: str | None, t = None, **kwargs) -> str | float | int | bool | None | Path | dict:
    # None stays None
    if s is None:
        return None
    if not isinstance(s, str):
        return s
    # Only "null" and "none" literals become None, empty string stays empty
    if s.lower() in NULL_VALUES:
        return None
    if t is None:
        return coerce_unknown(s, **kwargs)
    if t in [bool, "bool"]:
        return coerce_bool(s, **kwargs)
    if t in [str, "str"]:
        return s
    if t in [int, "int"]:
        return coerce_int(s, **kwargs)
    if t in [float, "float"]:
        return coerce_float(s, **kwargs)
    if t in [bool, "bool"]:
        return coerce_bool(s, **kwargs)
    if t in [dict, "dict"]:
        return json.loads(s, **kwargs)
    if t in [Path, PosixPath, "Path"]:
        return coerce_path(s, **kwargs)
    if t in ["path_str"]:
        return coerce_path_str(s, **kwargs)
    if t in [glob, glob.glob, "glob"]:
        return coerce_glob(s, **kwargs)
    raise TypeError(f"Unsupported type: {type}")