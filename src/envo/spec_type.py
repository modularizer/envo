import inspect
import json
import re
from collections.abc import Iterable, Callable
from dataclasses import dataclass
from typing import Any


def is_pydantic_model(obj) -> bool:
    """
    Check if an object is a Pydantic BaseModel subclass.

    This function safely checks whether the given object is a class that
    inherits from Pydantic's BaseModel, handling the case where Pydantic
    is not installed.

    Args:
        obj: Any Python object to check.

    Returns:
        True if obj is a class that subclasses pydantic.BaseModel,
        False otherwise (including when Pydantic is not installed).
    """
    if not inspect.isclass(obj):
        return False
    try:
        from pydantic import BaseModel
        return issubclass(obj, BaseModel)
    except ImportError:
        return False


def pydantic_coercer(model_cls):
    """
    Create a coercion function for a Pydantic model.

    This factory function returns a callable that can parse string values
    (including JSON strings) into instances of the specified Pydantic model.

    Args:
        model_cls: A Pydantic BaseModel subclass to use for validation.

    Returns:
        A callable that takes a string and returns a validated model instance.

    Example:
        >>> from pydantic import BaseModel
        >>> class Config(BaseModel):
        ...     host: str
        ...     port: int
        >>> coerce_config = pydantic_coercer(Config)
        >>> coerce_config('{"host": "localhost", "port": 8080}')
        Config(host='localhost', port=8080)
    """
    def _coerce(s: str):
        if not isinstance(s, str):
            return model_cls.model_validate(s)
        # Try to parse as JSON first
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            data = s
        return model_cls.model_validate(data)
    return _coerce


@dataclass
class VariableSpec:
    """
    Specification for how to parse and validate an environment variable.

    VariableSpec defines the complete pipeline for processing an environment
    variable value from its raw string form to a validated Python object.

    The processing pipeline is:
        raw_string -> pre() -> raw_validator() -> coerce() -> post() -> validator() -> final_value

    Attributes:
        groups: Iterable of group names this variable belongs to. Groups allow
            organizing variables and retrieving subsets via `env.get_group()`.
        docs: Human-readable documentation string describing this variable.
        type: Type hint for coercion. Can be a Python type (int, bool, list),
            a string type name ("int", "json"), or None for auto-detection.
        pre: Optional pre-processing function applied to the raw string before
            coercion. Useful for normalization (e.g., stripping whitespace).
        coerce: Controls type coercion behavior:
            - True (default): Use the built-in coerce() function
            - False: Skip coercion, keep as raw string
            - Callable: Use this custom function for coercion
        post: Optional post-processing function applied after coercion.
            Receives the coerced value and returns the final value.
        raw_validator: Optional validator called on the raw string (after pre).
            Should raise an exception if validation fails.
        validator: Optional validator called on the final value (after post).
            Should raise an exception if validation fails.
        default: Default value to use if the variable is not set.
        required: If True, the variable must have a non-empty value.

    Example:
        >>> spec = VariableSpec(
        ...     groups=("database",),
        ...     docs="Database connection port",
        ...     type=int,
        ...     required=True,
        ...     validator=lambda x: x if 1 <= x <= 65535 else (_ for _ in ()).throw(ValueError("Invalid port"))
        ... )
    """

    groups: Iterable[str] = ("unknown",)
    docs: str = "No help available"
    type: str | type | None = None
    pre: Callable[[str], str] | None = None
    coerce: bool | Callable[[str], Any] = True
    post: Callable[[str], str] | None = None
    raw_validator: Callable[[str], Any] | None = None
    validator: Callable[[Any], Any] | None = None
    default: str = None
    required: bool = False

VariableSpecInput = VariableSpec | dict | str | type | None | Callable[[str], Any]

def parse_variable_spec(v: VariableSpecInput, default_variable_spec: VariableSpecInput = None) -> VariableSpec:
    """
    Parse a variable specification into a VariableSpec instance.

    This method normalizes various shorthand formats for specifying how a
    variable should be parsed into a full VariableSpec object.

    Args:
        v: The specification to parse. Can be:
            - None: Returns the default_variable_spec
            - VariableSpec: Returned as-is
            - dict: Passed as kwargs to VariableSpec
            - Pydantic BaseModel subclass: Creates spec with Pydantic coercer
            - str or type: Creates spec with this as the type hint
            - Callable: Creates spec using this as the coerce function

    Returns:
        A VariableSpec instance.

    Raises:
        ValueError: If the specification format is not recognized.

    Example:
        >>> env.parse_variable_spec(int)
        VariableSpec(type=int, ...)
        >>> env.parse_variable_spec({"type": int, "docs": "Port number"})
        VariableSpec(type=int, docs="Port number", ...)
    """
    if v is None:
        return parse_variable_spec(default_variable_spec) if default_variable_spec is not None else VariableSpec()
    if isinstance(v, VariableSpec):
        v2 = v
    elif isinstance(v, dict):
        v2 = VariableSpec(**v)
    elif is_pydantic_model(v):
        v2 = VariableSpec(coerce=pydantic_coercer(v))
    elif isinstance(v, str | type):
        v2 = VariableSpec(type=v)
    elif isinstance(v, Callable):
        v2 = VariableSpec(coerce=v)
    else:
        raise ValueError(f"Unknown spec: {v}")
    
    # Infer type from default if type is not set
    if v2.type is None and v2.default is not None and v2.default != "":
        # Try to infer type from default value
        from envo.coerce import coerce_unknown
        try:
            coerced_default = coerce_unknown(v2.default)
            # Get the type of the coerced value
            if isinstance(coerced_default, bool):
                v2.type = bool
            elif isinstance(coerced_default, int):
                v2.type = int
            elif isinstance(coerced_default, float):
                v2.type = float
            # For strings, paths, dicts, lists - keep as None (no type enforcement)
        except Exception:
            # If coercion fails, leave type as None
            pass
    
    return v2

def parse_spec_key(k: str | re.Pattern) -> str | re.Pattern:
    """
    Parse a specification key into a string or compiled regex pattern.

    This method interprets various key formats and converts them into either
    an exact string match or a compiled regex pattern for flexible variable
    name matching.

    Args:
        k: The key to parse. Supported formats:
            - re.Pattern: Returned as-is
            - Simple identifier (e.g., "PORT"): Returned as exact string
            - Glob pattern (e.g., "DB_*"): Converted to regex
            - Regex literal (e.g., "/^AWS_.+/i"): Parsed and compiled
            - Other strings: Compiled as regex directly

    Returns:
        Either the original string (for exact matches) or a compiled
        re.Pattern for pattern matching.

    Raises:
        ValueError: If the key format is invalid.

    Example:
        >>> env.parse_spec_key("PORT")
        'PORT'
        >>> env.parse_spec_key("DB_*")
        re.compile('DB_.*')
        >>> env.parse_spec_key("/^secret_.+/i")
        re.compile('^secret_.+', re.IGNORECASE)
    """
    if isinstance(k, re.Pattern):
        k2 = k
    elif re.fullmatch(r"[a-zA-Z_\-\d]+", k):
        # Simple identifier without wildcards - exact string match
        k2 = k
    elif re.fullmatch(r"[a-zA-Z_\-\d\*]+", k):
        # Glob pattern with * - convert to regex
        k2 = re.compile(k.replace("*", ".*"))
    elif m := re.match(r'r?/(.*)/([imsxal]*)', k):
        pattern_text = m.group(1)
        flags_text = m.group(2)

        # convert flag letters to actual re flags
        flag_map = {
            "i": re.I,
            "m": re.M,
            "s": re.S,
            "x": re.X,
            "a": re.A,
            "l": re.L,
        }

        flags = 0
        for ch in flags_text:
            flags |= flag_map[ch]

        pat = re.compile(pattern_text, flags)
        k2 = pat
    elif isinstance(k, str):
        k2 = re.compile(k)
    else:
        raise ValueError(f"Invalid key: '{k}'")
    return k2




raise_error = object()

class EnvSpec(dict):
    def get(self, key: str, default=None) -> VariableSpec:
        """
        Get the VariableSpec for a given variable name.

        Looks up the specification for a variable, first checking for an exact
        match, then checking pattern matches in order.

        Args:
            key: The variable name to look up.

        Returns:
            The VariableSpec that applies to this variable.

        Raises:
            KeyError: If no spec matches the key and allow_extra is False.

        Example:
            >>> env.get_spec("PORT")
            VariableSpec(type=int, ...)
            >>> env.get_spec("DB_HOST")  # Matches "DB_*" pattern
            VariableSpec(groups=("database",), ...)
        """
        if key in self:
            return super().__getitem__(key)
        else:
            for k, v in self.items():
                if isinstance(k, re.Pattern) and k.match(key):
                    return v
        if default is raise_error:
            raise KeyError(f"Unexpected key: {key}")
        return raise_error

    def __getitem__(self, item: str) -> VariableSpec:
        return self.get(item, default=raise_error)

    def __getattr__(self, item):
        return self.get(item, default=raise_error) if item in self else None

    def __repr__(self):
        return f"EnvSpec<{str(dict(self))}>"

    def __str__(self):
        return str(dict(self))

    def list_groups(self) -> tuple[str, ...]:
        """
        List all unique group names defined in the spec.

        Returns:
            Tuple of all group names used across all variable specs.

        Example:
            >>> env.list_groups()
            ("database", "api", "required", "unknown")
        """
        return tuple(set(g for v in self.values() for g in v.groups))

    def get_group(self, *groups: str) -> "EnvSpec":
        """
        Get a filtered EnvSpec containing only variables in specified groups.
        """
        return EnvSpec({k: v for k, v in self.items() if isinstance(k, str) and all(group in v.groups for group in groups)})

    def __call__(self, *groups) -> "EnvSpec":
        """
        Shorthand for get_group().
        """
        return self.get_group(*groups)

    @property
    def groups(self) -> dict[str, "EnvSpec"]:
        """
        Dictionary of all groups, each mapped to a filtered EnvSpec.
        """
        return {g: self(g) for g in self.list_groups()}

    def get_required(self) -> "EnvSpec":
        """
        Get a filtered EnvSpec containing only required variables.
        
        Returns:
            EnvSpec with only variables where required=True.
            
        Example:
            >>> required = spec.get_required()
            >>> list(required.keys())
            ['DB_HOST', 'API_KEY']
        """
        return EnvSpec({k: v for k, v in self.items() if isinstance(k, str) and v.required})

    @property
    def required(self) -> "EnvSpec":
        """
        Property shorthand for get_required().
        
        Example:
            >>> spec.required
            EnvSpec({'DB_HOST': VariableSpec(...), 'API_KEY': VariableSpec(...)})
        """
        return self.get_required()

    def list_required(self) -> tuple[str, ...]:
        """
        List all required variable names.
        
        Returns:
            Tuple of variable names that are marked as required.
            
        Example:
            >>> spec.list_required()
            ('DB_HOST', 'API_KEY')
        """
        return tuple(k for k, v in self.items() if isinstance(k, str) and v.required)

    def is_required(self, key: str) -> bool:
        """
        Check if a specific variable is required.
        
        Args:
            key: The variable name to check.
            
        Returns:
            True if the variable is required, False otherwise.
            
        Example:
            >>> spec.is_required('DB_HOST')
            True
            >>> spec.is_required('DEBUG')
            False
        """
        try:
            return self[key].required
        except KeyError:
            return False

    def _is_catchall_pattern(self, pattern: re.Pattern) -> bool:
        """Check if a regex pattern is a catch-all (matches essentially anything)."""
        # Common catch-all patterns that match any string
        catchall_patterns = {
            '.*',      # match all
            '.+',      # match all non-empty
            '.*$',     # match all
            '^.*$',    # match all
            '^.+$',    # match all non-empty
            '[^]*',    # match all (weird but valid)
            '.+$',     # match all non-empty
        }
        # Also check if it's effectively a catch-all (just anchors around .*)
        normalized = pattern.pattern.strip('^$')
        return pattern.pattern in catchall_patterns or normalized in ('.*', '.+')

    def has_explicit_spec(self, key: str) -> bool:
        """
        Check if a key has an explicit spec (not just a catch-all fallback).
        
        Args:
            key: The variable name to check.
            
        Returns:
            True if the key matches an explicit spec entry (exact string match
            or a non-catch-all pattern), False if it only matches a catch-all.
            
        Example:
            >>> spec = parse_spec({"DB_HOST": str, "DB_*": str}, allow_extra="*")
            >>> spec.has_explicit_spec("DB_HOST")  # exact match
            True
            >>> spec.has_explicit_spec("DB_PORT")  # matches DB_*
            True
            >>> spec.has_explicit_spec("RANDOM_VAR")  # only matches *
            False
        """
        # Check for exact string match first
        if key in dict.keys(self):
            return True
        
        # Check pattern matches, excluding catch-alls
        for k in self.keys():
            if isinstance(k, re.Pattern):
                if k.match(key) and not self._is_catchall_pattern(k):
                    return True
        
        return False

    def filter_explicit(self, keys: list[str]) -> list[str]:
        """
        Filter a list of keys to only those with explicit specs.
        
        Args:
            keys: List of variable names to filter.
            
        Returns:
            List of keys that have explicit specs (not just catch-all matches).
            
        Example:
            >>> spec = parse_spec({"DB_HOST": str, "DB_*": str}, allow_extra="*")
            >>> spec.filter_explicit(["DB_HOST", "DB_PORT", "RANDOM"])
            ["DB_HOST", "DB_PORT"]
        """
        return [k for k in keys if self.has_explicit_spec(k)]

    def list_explicit_keys(self) -> tuple[str, ...]:
        """
        List all explicitly defined keys (exact string matches only).
        
        Returns:
            Tuple of variable names that are explicitly defined in the spec.
            Does not include pattern-matched keys.
            
        Example:
            >>> spec = parse_spec({"DB_HOST": str, "DB_*": str})
            >>> spec.list_explicit_keys()
            ('DB_HOST',)
        """
        return tuple(k for k in self.keys() if isinstance(k, str))




def parse_spec(
        spec: dict[str | re.Pattern, VariableSpecInput] = None,
        default_variable_spec: VariableSpecInput = None,
        allow_extra: str | re.Pattern | bool = "*",
        docs: dict[str | re.Pattern, str] = None,
        defaults: dict[str | re.Pattern, str] = None,
        **spec_extra,
) -> EnvSpec:
    """
    Parse a complete specification dictionary.

    Converts a user-provided spec dictionary (with various shorthand formats)
    into a normalized dictionary mapping parsed keys to VariableSpec instances.

    Args:
        spec: Dictionary mapping variable names/patterns to their specifications.

    Returns:
        Normalized dictionary with parsed keys and VariableSpec values.

    Example:
        >>> env.parse_spec({
        ...     "PORT": int,
        ...     "DB_*": {"type": str, "groups": ("database",)}
        ... })
        {'PORT': VariableSpec(type=int, ...), re.compile('DB_.*'): VariableSpec(...)}
    """
    spec = {**(spec or {}), **spec_extra}
    p = {}
    for k, v in spec.items():
        v2 = parse_variable_spec(v, default_variable_spec)
        k2 = parse_spec_key(k)
        p[k2] = v2
    if allow_extra:
        p[parse_spec_key(allow_extra)] = parse_variable_spec(default_variable_spec)
    if docs:
        for k, v in docs.items():
            p[parse_spec_key(k)].docs = v
    if defaults:
        for k, v in defaults.items():
            p[parse_spec_key(k)].default = v
    return EnvSpec(p)