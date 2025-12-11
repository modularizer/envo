"""
Parse .env files into EnvSpec with full metadata extraction.

Supports multiple file formats:
- .env files (with special comment directives)
- .json files
- .yaml/.yml files
- .toml files

This module parses structured files to extract:
- Variable names and default values
- Group membership from section headers
- Help text from comments (inline and above)
- Type hints and validation rules from special directives

Supported directive syntax in .env comments:
    @type:<type>     - Type hint (int, float, bool, str, path, json)
    @min:<n>         - Minimum value (numeric)
    @max:<n>         - Maximum value (numeric)
    @range:<n>-<m>   - Range constraint (numeric)  
    @choices:<a,b,c> - Valid choices (comma-separated)
    @pattern:<regex> - Regex pattern validation
    @required        - Value must be non-empty

Example .env file:
    # ============================================================================
    # database - Database Configuration
    # ============================================================================
    DB_HOST=localhost# Database hostname @required
    DB_PORT=5432# Port number @type:int @range:1-65535
    DB_NAME=myapp# Database name
    
Example JSON/YAML/TOML format (flat):
    {
        "DB_HOST": "localhost",
        "DB_PORT": 5432
    }

Example JSON/YAML/TOML format (rich):
    {
        "DB_HOST": {
            "default": "localhost",
            "type": "str",
            "help": "Database hostname",
            "required": true,
            "group": "database"
        },
        "DB_PORT": {
            "default": 5432,
            "type": "int",
            "min": 1,
            "max": 65535,
            "group": "database"
        }
    }

Example YAML format (grouped):
    database:
        DB_HOST:
            default: localhost
            help: Database hostname
        DB_PORT:
            default: 5432
            type: int
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fpr import find_project_root

from envo.spec_type import VariableSpec, EnvSpec
from envo.consts import DEFAULT_GROUP, DEFAULT_DOCS


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


@dataclass
class ParsedVariable:
    """Intermediate representation of a parsed variable."""
    name: str
    value: str | None  # default value: None means unset, "" means explicit empty string
    help_text: str = ""
    groups: tuple[str, ...] = (DEFAULT_GROUP,)
    type_hint: str | type | None = None
    min_val: float | None = None
    max_val: float | None = None
    choices: tuple[str, ...] | None = None
    pattern: str | None = None
    required: bool = False
    line_number: int = 0


@dataclass
class ParsedGroup:
    """Represents a parsed group section."""
    name: str
    description: str = ""
    line_number: int = 0


# Regex patterns for parsing
GROUP_HEADER_PATTERN = re.compile(r'^#\s*=+\s*$')
GROUP_NAME_PATTERN = re.compile(r'^#\s*(\S+)\s*[-–—]\s*(.*)$')
VARIABLE_PATTERN = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$')
DIRECTIVE_PATTERN = re.compile(r'@(\w+)(?::([^\s@]+))?')


def parse_directives(text: str) -> dict[str, Any]:
    """
    Parse special directives from comment text.
    
    Args:
        text: Comment text that may contain directives
        
    Returns:
        Dictionary of directive name -> value mappings
        
    Example:
        >>> parse_directives("Some help @type:int @min:0 @max:100")
        {'type': 'int', 'min': '0', 'max': '100'}
    """
    directives = {}
    for match in DIRECTIVE_PATTERN.finditer(text):
        name = match.group(1).lower()
        value = match.group(2)
        directives[name] = value if value else True
    return directives


def extract_help_text(text: str) -> str:
    """
    Extract help text from a comment, removing directives.
    
    Args:
        text: Comment text possibly containing directives
        
    Returns:
        Clean help text with directives removed
    """
    # Remove all @directive patterns
    clean = DIRECTIVE_PATTERN.sub('', text)
    # Clean up extra whitespace
    return ' '.join(clean.split()).strip()


def parse_type_hint(type_str: str | None) -> str | type | None:
    """
    Convert a type string to a type hint.
    
    Args:
        type_str: String type name like 'int', 'float', 'bool'
        
    Returns:
        Corresponding type or string for special types
    """
    if not type_str:
        return None
    
    type_map = {
        'int': int,
        'integer': int,
        'float': float,
        'number': float,
        'bool': bool,
        'boolean': bool,
        'str': str,
        'string': str,
        'path': 'path',
        'path_str': 'path_str',
        'json': dict,
        'dict': dict,
        'list': list,
        'glob': 'glob',
    }
    return type_map.get(type_str.lower(), type_str)


def build_validator(parsed: ParsedVariable) -> Callable[[Any], Any] | None:
    """
    Build a validator function from parsed constraints.
    
    Args:
        parsed: ParsedVariable with constraint information
        
    Returns:
        Validator function or None if no constraints
    """
    validators = []
    
    if parsed.required:
        def required_validator(x):
            if x is None or x == '':
                raise ValueError(f"{parsed.name} is required")
            return x
        validators.append(required_validator)
    
    if parsed.min_val is not None:
        min_v = parsed.min_val
        def min_validator(x):
            if x is not None and x < min_v:
                raise ValueError(f"{parsed.name} must be >= {min_v}, got {x}")
            return x
        validators.append(min_validator)
    
    if parsed.max_val is not None:
        max_v = parsed.max_val
        def max_validator(x):
            if x is not None and x > max_v:
                raise ValueError(f"{parsed.name} must be <= {max_v}, got {x}")
            return x
        validators.append(max_validator)
    
    if parsed.choices:
        choices = parsed.choices
        def choices_validator(x):
            if x is not None and str(x) not in choices:
                raise ValueError(f"{parsed.name} must be one of {choices}, got {x}")
            return x
        validators.append(choices_validator)
    
    if parsed.pattern:
        pat = re.compile(parsed.pattern)
        def pattern_validator(x):
            if x is not None and not pat.match(str(x)):
                raise ValueError(f"{parsed.name} must match pattern {parsed.pattern}, got {x}")
            return x
        validators.append(pattern_validator)
    
    if not validators:
        return None
    
    def combined_validator(x):
        for v in validators:
            x = v(x)
        return x
    
    return combined_validator


def parse_env_file(
    path: str | Path,
    default_group: str = DEFAULT_GROUP,
) -> tuple[list[ParsedVariable], list[ParsedGroup]]:
    """
    Parse an env file into structured data.
    
    Args:
        path: Path to the .env file
        default_group: Default group name for variables outside sections
        
    Returns:
        Tuple of (list of ParsedVariable, list of ParsedGroup)
    """
    path = Path(path).expanduser()
    if not path.exists():
        return [], []
    
    lines = path.read_text().splitlines()
    variables: list[ParsedVariable] = []
    groups: list[ParsedGroup] = []
    
    current_group = default_group
    current_group_desc = ""
    pending_comments: list[str] = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        line_num = i + 1
        
        # Check for group header (=== line)
        if GROUP_HEADER_PATTERN.match(line):
            # Look for group name on next line
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if name_match := GROUP_NAME_PATTERN.match(next_line):
                    current_group = name_match.group(1).lower()
                    current_group_desc = name_match.group(2).strip()
                    groups.append(ParsedGroup(
                        name=current_group,
                        description=current_group_desc,
                        line_number=line_num
                    ))
                    # Skip past the header block (=== line, name line, === line)
                    i += 1
                    if i + 1 < len(lines) and GROUP_HEADER_PATTERN.match(lines[i + 1].strip()):
                        i += 1
            pending_comments = []
            i += 1
            continue
        
        # Check for comment line
        if line.startswith('#'):
            comment_text = line[1:].strip()
            # Skip subgroup markers like "# params"
            if comment_text.lower() not in ('params', 'parameters', 'options', 'settings'):
                pending_comments.append(comment_text)
            i += 1
            continue
        
        # Check for variable definition
        if var_match := VARIABLE_PATTERN.match(line):
            var_name = var_match.group(1)
            value_and_comment = var_match.group(2)
            
            # Split value from inline comment
            value, inline_comment = split_value_comment(value_and_comment)
            
            # Combine pending comments with inline comment
            all_comments = pending_comments + ([inline_comment] if inline_comment else [])
            full_comment = ' '.join(all_comments)
            
            # Parse directives from comments
            directives = parse_directives(full_comment)
            help_text = extract_help_text(full_comment)
            
            # Parse range directive
            min_val = None
            max_val = None
            if 'range' in directives:
                range_str = directives['range']
                if '-' in range_str:
                    parts = range_str.split('-', 1)
                    try:
                        min_val = float(parts[0])
                        max_val = float(parts[1])
                    except ValueError:
                        pass
            
            # Parse individual min/max
            if 'min' in directives:
                try:
                    min_val = float(directives['min'])
                except ValueError:
                    pass
            if 'max' in directives:
                try:
                    max_val = float(directives['max'])
                except ValueError:
                    pass
            
            # Parse choices
            choices = None
            if 'choices' in directives:
                choices = tuple(c.strip() for c in directives['choices'].split(','))
            
            parsed = ParsedVariable(
                name=var_name,
                value=value,
                help_text=help_text,
                groups=(current_group,),
                type_hint=parse_type_hint(directives.get('type')),
                min_val=min_val,
                max_val=max_val,
                choices=choices,
                pattern=directives.get('pattern'),
                required=directives.get('required', False) is not False,
                line_number=line_num,
            )
            variables.append(parsed)
            pending_comments = []
        
        # Empty line clears pending comments
        elif not line:
            pending_comments = []
        
        i += 1
    
    return variables, groups


def split_value_comment(text: str) -> tuple[str | None, str | None]:
    """
    Split a value from its inline comment.
    
    Handles quoted strings correctly.
    Distinguishes between:
        - Empty (no value): returns None
        - Explicit empty quotes ("" or ''): returns ""
        - Actual value: returns the value
    
    Args:
        text: Value text that may contain an inline comment
        
    Returns:
        Tuple of (value or None, comment or None)
    """
    # Find the comment position (if any), respecting quotes
    comment_pos = None
    in_quotes = False
    quote_char = None
    
    for i, char in enumerate(text):
        if char in ('"', "'") and (i == 0 or text[i-1] != '\\'):
            if not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char:
                in_quotes = False
                quote_char = None
        elif char == '#' and not in_quotes:
            comment_pos = i
            break
    
    if comment_pos is not None:
        raw_value = text[:comment_pos].strip()
        comment = text[comment_pos+1:].strip()
    else:
        raw_value = text.strip()
        comment = None
    
    # Now parse the value, distinguishing None vs empty string
    value = parse_value_with_quotes(raw_value)
    
    return value, comment


def parse_value_with_quotes(raw_value: str) -> str | None:
    """
    Parse a raw value string, distinguishing between None and empty string.
    
    - Empty string (nothing): returns None
    - Explicit empty quotes ("" or ''): returns ""
    - Quoted value: returns unquoted value
    - Unquoted value: returns as-is
    
    Args:
        raw_value: The raw value string (already stripped)
        
    Returns:
        The parsed value, or None if empty/unset
    """
    if not raw_value:
        # Nothing there at all -> None
        return None
    
    # Check for quoted strings
    if (raw_value.startswith('"') and raw_value.endswith('"')) or \
       (raw_value.startswith("'") and raw_value.endswith("'")):
        # Remove quotes - this preserves "" as empty string
        return raw_value[1:-1]
    
    # Unquoted value - return as-is
    return raw_value


def parsed_to_variable_spec(parsed: ParsedVariable) -> VariableSpec:
    """
    Convert a ParsedVariable to a VariableSpec.
    
    Args:
        parsed: ParsedVariable instance
        
    Returns:
        Corresponding VariableSpec
        
    Note:
        - parsed.value of None means "not set" -> default=None
        - parsed.value of "" means "explicitly empty" -> default=""
        - If type is not set but default is not None, infer type from default
    """
    # Infer type from default if type is not set
    inferred_type = parsed.type_hint
    if inferred_type is None and parsed.value is not None and parsed.value != "":
        # Try to infer type from default value
        from envo.coerce import coerce_unknown
        try:
            coerced_default = coerce_unknown(parsed.value)
            # Get the type of the coerced value
            if isinstance(coerced_default, bool):
                inferred_type = bool
            elif isinstance(coerced_default, int):
                inferred_type = int
            elif isinstance(coerced_default, float):
                inferred_type = float
            # For strings, paths, dicts, lists - keep as str (default)
            # We don't want to infer str type since that's the default
        except Exception:
            # If coercion fails, leave type as None
            pass
    
    return VariableSpec(
        groups=parsed.groups,
        docs=parsed.help_text or DEFAULT_DOCS,
        type=inferred_type,
        default=parsed.value,  # None means unset, "" means explicit empty
        required=parsed.required,
        validator=build_validator(parsed),
    )


def _parse_structured_spec(data: dict, default_group: str = DEFAULT_GROUP) -> list[ParsedVariable]:
    """
    Parse a structured dictionary (from JSON/YAML/TOML) into ParsedVariable list.
    
    Supports multiple formats:
    1. Flat format: {"VAR": "value"} or {"VAR": 123}
    2. Rich format: {"VAR": {"default": "value", "type": "str", "help": "..."}}
    3. Grouped format: {"group_name": {"VAR": {...}}}
    
    Args:
        data: Dictionary loaded from JSON/YAML/TOML
        default_group: Default group for ungrouped variables
        
    Returns:
        List of ParsedVariable instances
    """
    variables = []
    
    for key, value in data.items():
        # Check if this is a grouped structure (value is dict with nested var specs)
        if isinstance(value, dict) and _is_group_dict(value):
            # This is a group: {"database": {"DB_HOST": {...}, "DB_PORT": {...}}}
            group_name = key.lower()
            for var_name, var_spec in value.items():
                parsed = _parse_variable_entry(var_name, var_spec, group_name)
                variables.append(parsed)
        else:
            # This is a variable at the top level
            parsed = _parse_variable_entry(key, value, default_group)
            variables.append(parsed)
    
    return variables


def _is_group_dict(d: dict) -> bool:
    """
    Check if a dict represents a group of variables vs a variable spec.
    
    A group dict contains variable names as keys.
    A variable spec dict has keys like 'default', 'type', 'help', etc.
    """
    spec_keys = {'default', 'type', 'help', 'docs', 'min', 'max', 'range', 
                 'choices', 'pattern', 'required', 'group', 'groups', 'value'}
    
    # If any key looks like a spec key, it's probably a variable spec
    if any(k.lower() in spec_keys for k in d.keys()):
        return False
    
    # If all values are dicts or simple values, and keys look like var names, it's a group
    return all(
        isinstance(v, (dict, str, int, float, bool, type(None)))
        for v in d.values()
    )


def _parse_variable_entry(name: str, value: Any, default_group: str) -> ParsedVariable:
    """
    Parse a single variable entry from structured format.
    
    Args:
        name: Variable name
        value: Can be a simple value or a dict with spec details
        default_group: Default group name
        
    Returns:
        ParsedVariable instance
    """
    if not isinstance(value, dict):
        # Simple value: {"VAR": "value"} or {"VAR": 123}
        return ParsedVariable(
            name=name,
            value=_convert_to_string(value),
            groups=(default_group,),
        )
    
    # Rich format: {"VAR": {"default": "value", "type": "str", ...}}
    spec = value
    
    # Get the default value
    default_val = spec.get('default', spec.get('value'))
    if default_val is not None:
        default_val = _convert_to_string(default_val)
    
    # Get group(s)
    groups = spec.get('groups', spec.get('group', default_group))
    if isinstance(groups, str):
        groups = (groups,)
    else:
        groups = tuple(groups) if groups else (default_group,)
    
    # Parse range if specified
    min_val = None
    max_val = None
    if 'range' in spec:
        range_val = spec['range']
        if isinstance(range_val, str) and '-' in range_val:
            parts = range_val.split('-', 1)
            try:
                min_val = float(parts[0])
                max_val = float(parts[1])
            except ValueError:
                pass
        elif isinstance(range_val, (list, tuple)) and len(range_val) == 2:
            min_val, max_val = range_val
    
    # Get individual min/max
    if 'min' in spec:
        min_val = float(spec['min'])
    if 'max' in spec:
        max_val = float(spec['max'])
    
    # Get choices
    choices = spec.get('choices')
    if choices:
        if isinstance(choices, str):
            choices = tuple(c.strip() for c in choices.split(','))
        else:
            choices = tuple(str(c) for c in choices)
    
    return ParsedVariable(
        name=name,
        value=default_val,
        help_text=spec.get('help', spec.get('docs', '')),
        groups=groups,
        type_hint=parse_type_hint(spec.get('type')),
        min_val=min_val,
        max_val=max_val,
        choices=choices,
        pattern=spec.get('pattern'),
        required=spec.get('required', False),
    )


def _convert_to_string(value: Any) -> str | None:
    """Convert a value to string format for storage."""
    if value is None:
        return None
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def env_file_to_spec(
    path: str | Path,
    default_group: str = DEFAULT_GROUP,
    cwd: str | Path | None = "find_project_root",
) -> EnvSpec:
    """
    Parse an env/json/yaml/toml file and create an EnvSpec.
    
    This is the main entry point for converting a config file to a spec.
    Automatically detects file type from extension.
    
    Args:
        path: Path to the file (.env, .json, .yaml, .yml, .toml)
        default_group: Default group for variables outside sections
        cwd: Working directory for relative paths
        
    Returns:
        EnvSpec with all parsed variable specifications
        
    Example:
        >>> spec = env_file_to_spec("sample.env")
        >>> spec.AMC_WORDLIST_LANG
        VariableSpec(groups=('amcw',), docs='Language code for wordfreq wordlist', ...)
        
        >>> spec = env_file_to_spec("config.yaml")
        >>> spec.DB_HOST
        VariableSpec(groups=('database',), ...)
    """
    cwd = find_project_root() if cwd == "find_project_root" else cwd
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = cwd / path
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}, {cwd=}")
    
    file_type = _get_file_type(path)
    
    if file_type == 'json':
        data = json.loads(path.read_text())
        variables = _parse_structured_spec(data, default_group)
    elif file_type == 'yaml':
        data = _load_yaml(path)
        variables = _parse_structured_spec(data, default_group)
    elif file_type == 'toml':
        data = _load_toml(path)
        variables = _parse_structured_spec(data, default_group)
    else:
        variables, _ = parse_env_file(path, default_group)
    
    spec_dict = {}
    for var in variables:
        spec_dict[var.name] = parsed_to_variable_spec(var)
    
    return EnvSpec(spec_dict)


def env_file_to_defaults(path: str | Path) -> dict[str, str | None]:
    """
    Extract just the default values from an env file.
    
    Args:
        path: Path to the .env file
        
    Returns:
        Dictionary mapping variable names to their default values.
        Values can be:
            - None: variable defined but empty (VAR=)
            - "": variable explicitly empty (VAR="")
            - str: variable has a value
    """
    variables, _ = parse_env_file(path)
    return {v.name: v.value for v in variables}


def env_file_to_docs(path: str | Path) -> dict[str, str]:
    """
    Extract documentation/help text from an env file.
    
    Args:
        path: Path to the .env file
        
    Returns:
        Dictionary mapping variable names to their help text
    """
    variables, _ = parse_env_file(path)
    return {v.name: v.help_text for v in variables if v.help_text}


def print_spec_summary(spec: EnvSpec) -> None:
    """
    Print a formatted summary of an EnvSpec.
    
    Useful for debugging and documentation generation.
    
    Args:
        spec: EnvSpec to summarize
    """
    print("=" * 60)
    print("Environment Variable Specification")
    print("=" * 60)
    
    # Group by groups
    by_group: dict[str, list[tuple[str, VariableSpec]]] = {}
    for name, var_spec in spec.items():
        if isinstance(name, str):
            for group in var_spec.groups:
                by_group.setdefault(group, []).append((name, var_spec))
    
    for group_name, vars in sorted(by_group.items()):
        print(f"\n[{group_name}]")
        print("-" * 40)
        for name, var_spec in vars:
            type_str = ""
            if var_spec.type:
                if isinstance(var_spec.type, type):
                    type_str = f" ({var_spec.type.__name__})"
                else:
                    type_str = f" ({var_spec.type})"
            default_str = f" = {var_spec.default!r}" if var_spec.default else ""
            print(f"  {name}{type_str}{default_str}")
            if var_spec.docs and var_spec.docs != DEFAULT_DOCS:
                print(f"    {var_spec.docs}")



if __name__ == "__main__":
    from envo import env_file_to_spec, print_spec_summary

    # Parse sample.env into a spec
    spec = env_file_to_spec("sample.env")

    # Access individual variable specs
    print(spec.AMC_WORDLIST_LANG.docs)  # "Language code for wordfreq wordlist..."
    print(spec.AMC_WORDLIST_LANG.groups)  # ('amcw',)
    print(spec.AMC_WORDLIST_LANG.default)  # 'en'

    # Print formatted summary
    print_spec_summary(spec)