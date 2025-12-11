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


def _load_python_file(path: Path) -> dict[str, str | None]:
    """Load a Python file and extract environment variables as a dict."""
    import importlib.util
    import sys
    
    # Load the module
    spec = importlib.util.spec_from_file_location("_envo_temp_module", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Could not load Python file: {path}")
    
    module = importlib.util.module_from_spec(spec)
    sys.modules["_envo_temp_module"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        # Clean up
        if "_envo_temp_module" in sys.modules:
            del sys.modules["_envo_temp_module"]
    
    # Look for common names: env, ENV, env_dict, ENV_DICT, or a dict
    for attr_name in ['env', 'ENV', 'env_dict', 'ENV_DICT', 'env_vars', 'ENV_VARS']:
        if hasattr(module, attr_name):
            value = getattr(module, attr_name)
            if isinstance(value, dict):
                # Convert to string dict
                result = {}
                for k, v in value.items():
                    if v is None:
                        result[k] = None
                    elif isinstance(v, bool):
                        result[k] = str(v).lower()
                    elif isinstance(v, (list, dict)):
                        result[k] = json.dumps(v)
                    else:
                        result[k] = str(v)
                return result
    
    # If no standard name found, return module's __dict__ filtered to public attrs
    result = {}
    for k, v in module.__dict__.items():
        if not k.startswith('_') and isinstance(v, (str, int, float, bool, type(None))):
            if v is None:
                result[k] = None
            elif isinstance(v, bool):
                result[k] = str(v).lower()
            else:
                result[k] = str(v)
    return result


def _load_python_import(import_path: str) -> dict[str, str | None]:
    """Load a Python module via import path and extract environment variables as a dict."""
    import importlib
    
    try:
        module = importlib.import_module(import_path)
    except ImportError as e:
        raise ValueError(f"Could not import module: {import_path}") from e
    
    # Look for common names: env, ENV, env_dict, ENV_DICT, or a dict
    for attr_name in ['env', 'ENV', 'env_dict', 'ENV_DICT', 'env_vars', 'ENV_VARS']:
        if hasattr(module, attr_name):
            value = getattr(module, attr_name)
            if isinstance(value, dict):
                # Convert to string dict
                result = {}
                for k, v in value.items():
                    if v is None:
                        result[k] = None
                    elif isinstance(v, bool):
                        result[k] = str(v).lower()
                    elif isinstance(v, (list, dict)):
                        result[k] = json.dumps(v)
                    else:
                        result[k] = str(v)
                return result
    
    # If no standard name found, return module's __dict__ filtered to public attrs
    result = {}
    for k, v in module.__dict__.items():
        if not k.startswith('_') and isinstance(v, (str, int, float, bool, type(None))):
            if v is None:
                result[k] = None
            elif isinstance(v, bool):
                result[k] = str(v).lower()
            else:
                result[k] = str(v)
    return result


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
    if suffix == '.py':
        return 'python'
    elif suffix in ('.yaml', '.yml'):
        return 'yaml'
    elif suffix == '.json':
        return 'json'
    elif suffix == '.toml':
        return 'toml'
    else:
        return 'env'



def load_env_raw(*env_paths: str | Literal["os.environ"] | Path | dict,
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
    if isinstance(env_path, dict):
        return env_path
    if not env_path:
        return {}
    if env_path == "os.environ":
        return dict(os.environ)
    
    env_path_str = str(env_path)
    
    # Check if it's a Python import path (dots, no slashes, doesn't look like a file path)
    is_import = ('.' in env_path_str and 
                 '/' not in env_path_str and 
                 '\\' not in env_path_str and
                 not env_path_str.startswith('.') and
                 not env_path_str.endswith('.py'))
    
    if is_import:
        # Try as import path first
        try:
            return _load_python_import(env_path_str)
        except (ValueError, ImportError):
            # Fall through to try as file path
            pass
    
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
    
    if file_type == 'python':
        current = _load_python_file(env_path)
    elif file_type == 'json':
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
        extends_str = str(extends_path)
        # Check if it's a Python import path
        is_import = ('.' in extends_str and 
                     '/' not in extends_str and 
                     '\\' not in extends_str and
                     not extends_str.startswith('.') and
                     not extends_str.endswith('.py'))
        if is_import:
            # Try as import path
            try:
                base = _load_python_import(extends_str)
            except (ValueError, ImportError):
                # Fall back to file path
                extends_resolved = resolve_relative(extends_path, cwd=env_path.parent)
                base = load_single_env_raw(extends_resolved, cwd=env_path.parent, flatten=flatten, _loaded_files=_loaded_files)
        else:
            # Resolve relative to the current file's directory
            extends_resolved = resolve_relative(extends_path, cwd=env_path.parent)
            base = load_single_env_raw(extends_resolved, cwd=env_path.parent, flatten=flatten, _loaded_files=_loaded_files)
        # Current overrides base
        base.update(current)
        current = base
    
    # Process ENVO_EXTENDED_BY (higher priority - load after, it overrides current)
    extended_by_path = current.get(consts.ENVO_EXTENDED_BY)
    if extended_by_path:
        extended_by_str = str(extended_by_path)
        # Check if it's a Python import path
        is_import = ('.' in extended_by_str and 
                     '/' not in extended_by_str and 
                     '\\' not in extended_by_str and
                     not extended_by_str.startswith('.') and
                     not extended_by_str.endswith('.py'))
        if is_import:
            # Try as import path
            try:
                override = _load_python_import(extended_by_str)
            except (ValueError, ImportError):
                # Fall back to file path
                extended_by_resolved = resolve_relative(extended_by_path, cwd=env_path.parent)
                override = load_single_env_raw(extended_by_resolved, cwd=env_path.parent, flatten=flatten, _loaded_files=_loaded_files)
        else:
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


def _is_truthy(value: str | None) -> bool:
    """
    Check if a string value is truthy for logical operations.
    
    Returns False for: None, empty string, false-like values, null-like values.
    Returns True for everything else.
    """
    if value is None or value == '':
        return False
    lower = value.lower().strip()
    if lower in consts.BOOL_FALSE_VALUES:
        return False
    if lower in consts.NULL_VALUES:
        return False
    return True


def _find_operator(expr: str, op: str, start: int = 0) -> int:
    """
    Find the first occurrence of an operator at parenthesis depth 0.
    
    Args:
        expr: Expression string to search
        op: Operator to find
        start: Starting position
        
    Returns:
        Position of operator, or -1 if not found
    """
    depth = 0
    i = start
    op_len = len(op)
    while i <= len(expr) - op_len:
        c = expr[i]
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif depth == 0 and expr[i:i + op_len] == op:
            # Make sure we don't match == when looking for =
            if op == '=' and i + 1 < len(expr) and expr[i + 1] == '=':
                i += 1
                continue
            if op == '!' and i + 1 < len(expr) and expr[i + 1] == '=':
                i += 1
                continue
            return i
        i += 1
    return -1


def _rfind_operator(expr: str, op: str) -> int:
    """
    Find the last occurrence of an operator at parenthesis depth 0.
    
    Args:
        expr: Expression string to search
        op: Operator to find
        
    Returns:
        Position of operator, or -1 if not found
    """
    depth = 0
    op_len = len(op)
    i = len(expr) - op_len
    while i >= 0:
        c = expr[i]
        if c == ')':
            depth += 1
        elif c == '(':
            depth -= 1
        elif depth == 0 and expr[i:i + op_len] == op:
            # Make sure we don't match == when looking for single operators
            if op == '=' and i + 1 < len(expr) and expr[i + 1] == '=':
                i -= 1
                continue
            if op == '!' and i + 1 < len(expr) and expr[i + 1] == '=':
                i -= 1
                continue
            return i
        i -= 1
    return -1


def _try_numeric(value: str) -> int | float | None:
    """Try to parse a string as a number."""
    if not value:
        return None
    try:
        # Try int first
        return int(value.replace('_', ''))
    except ValueError:
        try:
            return float(value.replace('_', ''))
        except ValueError:
            return None


def _evaluate_expression(expr: str, env_dict: dict[str, str | None], ref_char: str) -> str:
    """
    Evaluate an expression with logical and arithmetic operators.
    
    Supports (in order of precedence, lowest to highest):
    - Ternary: $VAR?true_val:false_val
    - OR: $VAR||$OTHER
    - AND: $VAR&&$OTHER
    - Inequality: $VAR!=$OTHER or $VAR!=literal
    - Equality: $VAR==$OTHER or $VAR==literal
    - Addition/Subtraction: $A+$B, $A-$B
    - Multiplication: $A*$B
    - NOT: !$VAR or !expr
    - Parentheses: (expr)
    - Variable reference: $VAR
    - Literal value
    
    Note: Single | and / are NOT used as operators to avoid conflicts with paths.
    
    Args:
        expr: Expression to evaluate
        env_dict: Dictionary of resolved environment variables
        ref_char: Character used for variable references (default: $)
        
    Returns:
        Evaluated string result
    """
    import re
    expr = expr.strip()
    if not expr:
        return ''
    
    # 1. Ternary operator: condition?true_val:false_val
    q_pos = _find_operator(expr, '?')
    if q_pos > 0:
        # Find matching colon at same depth
        c_pos = _find_operator(expr, ':', q_pos + 1)
        if c_pos > q_pos:
            condition = expr[:q_pos]
            true_val = expr[q_pos + 1:c_pos]
            false_val = expr[c_pos + 1:]
            
            cond_result = _evaluate_expression(condition, env_dict, ref_char)
            if _is_truthy(cond_result):
                return _evaluate_expression(true_val, env_dict, ref_char)
            else:
                return _evaluate_expression(false_val, env_dict, ref_char)
    
    # 2. OR operator (use || to avoid conflict with path separators)
    pos = _rfind_operator(expr, '||')
    if pos >= 0:
        left = expr[:pos]
        right = expr[pos + 2:]
        left_val = _evaluate_expression(left, env_dict, ref_char)
        right_val = _evaluate_expression(right, env_dict, ref_char)
        return 'true' if (_is_truthy(left_val) or _is_truthy(right_val)) else 'false'
    
    # 3. AND operator (use && for consistency with ||)
    pos = _rfind_operator(expr, '&&')
    if pos >= 0:
        left = expr[:pos]
        right = expr[pos + 2:]
        left_val = _evaluate_expression(left, env_dict, ref_char)
        right_val = _evaluate_expression(right, env_dict, ref_char)
        return 'true' if (_is_truthy(left_val) and _is_truthy(right_val)) else 'false'
    
    # 4. Inequality operator
    pos = _find_operator(expr, '!=')
    if pos >= 0:
        left = expr[:pos]
        right = expr[pos + 2:]
        left_val = _evaluate_expression(left, env_dict, ref_char)
        right_val = _evaluate_expression(right, env_dict, ref_char)
        return 'true' if left_val != right_val else 'false'
    
    # 5. Equality operator
    pos = _find_operator(expr, '==')
    if pos >= 0:
        left = expr[:pos]
        right = expr[pos + 2:]
        left_val = _evaluate_expression(left, env_dict, ref_char)
        right_val = _evaluate_expression(right, env_dict, ref_char)
        return 'true' if left_val == right_val else 'false'
    
    # 6. Addition and Subtraction (right-to-left for left associativity)
    # Check subtraction first, but be careful not to match negative numbers
    pos = _rfind_operator(expr, '-')
    if pos > 0:  # Must be > 0 to not match unary minus at start
        left = expr[:pos]
        right = expr[pos + 1:]
        left_val = _evaluate_expression(left, env_dict, ref_char)
        right_val = _evaluate_expression(right, env_dict, ref_char)
        left_num = _try_numeric(left_val)
        right_num = _try_numeric(right_val)
        if left_num is not None and right_num is not None:
            result = left_num - right_num
            return str(int(result)) if isinstance(result, float) and result.is_integer() else str(result)
    
    pos = _rfind_operator(expr, '+')
    if pos >= 0:
        left = expr[:pos]
        right = expr[pos + 1:]
        left_val = _evaluate_expression(left, env_dict, ref_char)
        right_val = _evaluate_expression(right, env_dict, ref_char)
        left_num = _try_numeric(left_val)
        right_num = _try_numeric(right_val)
        if left_num is not None and right_num is not None:
            # Numeric addition
            result = left_num + right_num
            return str(int(result)) if isinstance(result, float) and result.is_integer() else str(result)
        else:
            # String concatenation
            return left_val + right_val
    
    # 7. Multiplication (no division to avoid conflict with paths)
    pos = _rfind_operator(expr, '*')
    if pos >= 0:
        left = expr[:pos]
        right = expr[pos + 1:]
        left_val = _evaluate_expression(left, env_dict, ref_char)
        right_val = _evaluate_expression(right, env_dict, ref_char)
        left_num = _try_numeric(left_val)
        right_num = _try_numeric(right_val)
        if left_num is not None and right_num is not None:
            result = left_num * right_num
            return str(int(result)) if isinstance(result, float) and result.is_integer() else str(result)
        # If not both numeric, return concatenated (fallback behavior)
        return left_val + right_val
    
    # 8. NOT operator (prefix)
    if expr.startswith('!'):
        inner = expr[1:]
        inner_val = _evaluate_expression(inner, env_dict, ref_char)
        return 'false' if _is_truthy(inner_val) else 'true'
    
    # 9. Parentheses
    if expr.startswith('(') and expr.endswith(')'):
        # Verify these are matching parentheses by checking depth
        depth = 0
        matched = False
        for i, c in enumerate(expr):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    # If we reach depth 0 at the last character, it's a wrapper
                    if i == len(expr) - 1:
                        matched = True
                    break
        if matched:
            # Parens wrap the whole expression
            return _evaluate_expression(expr[1:-1], env_dict, ref_char)
    
    # 10. Variable reference
    if expr.startswith(ref_char):
        var_name = expr[len(ref_char):]
        # Extract just the variable name (alphanumeric + underscore)
        match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)', var_name)
        if match:
            var_name = match.group(1)
            value = env_dict.get(var_name) or ''
            # If the value is still a variable reference, try to resolve it recursively
            if value and value.startswith(ref_char) and not _has_expression_operators(value, ref_char):
                # Simple variable reference - resolve it
                import re as re_module
                ref_escaped = re_module.escape(ref_char)
                simple_pattern = rf'{ref_escaped}([A-Za-z_][A-Za-z0-9_]*)'
                def replace_var(match):
                    ref_var_name = match.group(1)
                    if ref_var_name == var_name:
                        return match.group(0)  # Avoid self-reference
                    ref_val = env_dict.get(ref_var_name)
                    return ref_val if ref_val is not None else match.group(0)
                value = re_module.sub(simple_pattern, replace_var, value)
            return value
    
    # 11. Literal value - strip surrounding quotes if present
    expr = expr.strip()
    if (expr.startswith('"') and expr.endswith('"')) or \
       (expr.startswith("'") and expr.endswith("'")):
        return expr[1:-1]
    return expr


def _has_variable_reference(value: str, ref_char: str) -> bool:
    """Check if a value contains at least one variable reference."""
    import re
    ref_escaped = re.escape(ref_char)
    pattern = rf'{ref_escaped}[A-Za-z_][A-Za-z0-9_]*'
    return bool(re.search(pattern, value))


def _has_expression_operators(value: str, ref_char: str = None) -> bool:
    """
    Check if a value contains expression operators that need evaluation.
    
    IMPORTANT: Only returns True if there's at least one variable reference.
    We don't evaluate pure literals like "1+2" or "true||false".
    """
    if ref_char is None:
        ref_char = consts.REF_CHAR
    
    # First check: must have at least one variable reference
    if not _has_variable_reference(value, ref_char):
        return False
    
    # These operators indicate an expression (not just simple $VAR substitution)
    # Note: we use || for OR to avoid conflict with | in paths
    # Note: no division operator to avoid conflict with / in paths
    if '||' in value or '&&' in value or '==' in value or '!=' in value:
        return True
    if '?' in value and ':' in value:
        return True
    # Check for ! but not != (already handled above)
    if '!' in value and '!=' not in value:
        return True
    # Check for arithmetic operators
    # + and * are safe (not commonly in paths)
    if '+' in value or '*' in value:
        return True
    # - is tricky because it's common in filenames/paths
    # Only treat as operator if it appears between variable refs or numbers
    # Pattern: $VAR-something or number-something where something starts with $ or digit
    if '-' in value:
        import re
        # Look for patterns like $VAR-$OTHER or $VAR-123 or 123-$VAR
        ref_escaped = re.escape(ref_char)
        pattern = rf'({ref_escaped}[A-Za-z_][A-Za-z0-9_]*|\d+)-({ref_escaped}[A-Za-z_]|\d)'
        if re.search(pattern, value):
            return True
    return False


def resolve_var_references(env_dict: dict[str, str | None]) -> dict[str, str | None]:
    """
    Resolve variable references and expressions in environment variables.

    The reference character is configurable via ENVO_REF_CHAR (default: $).
    
    Supports:
    - Simple references: $VAR
    - Ternary: $VAR?true_value:false_value
    - Negation: !$VAR
    - Logical AND: $VAR&&$OTHER
    - Logical OR: $VAR||$OTHER
    - Equality: $VAR==$OTHER or $VAR==literal
    - Inequality: $VAR!=$OTHER or $VAR!=literal
    - Arithmetic: $A+$B, $A-$B, $A*$B
    - Parentheses for grouping: ($VAR&&$OTHER)||$THIRD
    
    Note: Single | and / are NOT operators (to avoid conflicts with paths).
    
    Performs multiple passes until no more substitutions are made,
    with a maximum iteration limit to prevent infinite loops.
    
    None values are preserved (not substituted).

    Args:
        env_dict: Dictionary of environment variables

    Returns:
        Dictionary with variable references and expressions resolved
    """
    import re
    ref_char = consts.REF_CHAR
    ref_char_escaped = re.escape(ref_char)
    simple_pattern = rf'{ref_char_escaped}([A-Za-z_][A-Za-z0-9_]*)'
    result = env_dict.copy()

    for iteration in range(consts.VAR_REFERENCE_MAX_ITERATIONS):
        changed = False
        for key, value in result.items():
            # Skip None values
            if value is None:
                continue
            if not isinstance(value, str):
                continue
            
            # Skip values without any references
            if ref_char not in value and '!' not in value:
                continue
            
            # Check if this contains expression operators
            if _has_expression_operators(value, ref_char):
                # Evaluate the entire value as an expression
                new_value = _evaluate_expression(value, result, ref_char)
            else:
                # Simple variable substitution only
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

                new_value = re.sub(simple_pattern, replace_var, value)
            
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
