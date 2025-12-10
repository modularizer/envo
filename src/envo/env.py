"""
Environment variable loading, parsing, and type coercion.

This module provides the core `Env` class for loading environment variables from
multiple sources (.env files, os.environ), applying substitutions, and coercing
values to appropriate Python types.

Example:
    >>> from envo import Env
    >>> env = Env(".env", ".env.local")
    >>> env.DEBUG  # Auto-coerced to bool
    True
    >>> env.get("PORT", type=int)
    8080
"""

from collections.abc import Callable
from pathlib import Path
import re
from typing import Literal, Any

from envo.coerce import coerce
from envo.load import load_env_raw
from fpr import find_project_root

from envo.sentinel import unspecified
from envo.spec_type import parse_variable_spec, VariableSpecInput, VariableSpec, parse_spec_key, parse_spec

# Special value that indicates "use the default from spec"
USE_SPEC_DEFAULT = "<default>"


def apply_all_substitutions(env_dict: dict[str, str | None]) -> dict[str, str | None]:
    """
    Apply all substitutions to a dictionary of environment variables.

    This function applies substitutions in order:
    1. % -> project root path
    2. $VAR_NAME -> environment variable references

    This is called AFTER all files are loaded and merged, so all values are available.
    None values are preserved (not substituted).

    Args:
        env_dict: Dictionary of environment variables (raw strings or None)

    Returns:
        Dictionary with all substitutions applied
    """
    project_root = find_project_root()
    result = env_dict.copy()

    # Step 1: Substitute % with project root
    for key, value in result.items():
        # Skip None values
        if value is None:
            continue
        if '%' in value:
            result[key] = value.replace("%", str(Path(project_root or Path.cwd()).expanduser().resolve()))
    return result



class Env(dict):
    """
    Environment variable container with type coercion and validation.

    Env provides a powerful interface for loading environment variables from
    multiple sources, merging them with configurable priority, and accessing
    them with automatic type coercion.

    Features:
        - Load from multiple .env files with priority-based merging
        - Automatic type coercion (strings to int, bool, list, dict, etc.)
        - Custom validation and transformation pipelines
        - Variable grouping for organized access
        - Pattern-based specification matching
        - Pydantic model support for complex types

    Example:
        >>> # Basic usage
        >>> env = Env(".env")
        >>> env.DEBUG  # Auto-coerced based on value
        True
        >>> env.PORT  # "8080" becomes 8080
        8080

        >>> # With explicit spec
        >>> env = Env(".env", spec={
        ...     "PORT": int,
        ...     "HOSTS": list,
        ...     "DB_*": {"groups": ("database",), "type": str}
        ... })

        >>> # Access by group
        >>> db_env = env.get_group("database")

    Attributes:
        raw: Dictionary of raw string values after substitutions are applied.
        spec: Parsed specification dictionary mapping keys/patterns to VariableSpec.
        parsed: Dictionary of all parsed (coerced) values.
    """

    def __init__(
        self,
        *env_paths: str | Literal["os.environ"] | Path,
        raw: dict[str, str] | None = None,
        existing_env_priority: Literal["none", "highest", "lowest"] | None = "highest",
        cwd: str | Path | None = "find_project_root",
        spec: dict[str | re.Pattern, VariableSpec | dict | str | type] = None,
        default_variable_spec: VariableSpec | dict | str | type | None | Callable[[str], Any] = None,
        allow_extra: str | re.Pattern | bool = "*",
        docs: dict[str | re.Pattern, str] = None,
        defaults: dict[str | re.Pattern, str] = None,
        _groups: tuple | None = None,
        **spec_extra,
    ):
        """
        Initialize an Env instance.

        Args:
            *env_paths: Paths to .env files to load, in order from lowest to highest
                priority. Later files override earlier ones. Use the literal string
                "os.environ" to include system environment variables at that priority.
            raw: If provided, use this dictionary directly instead of loading files.
                Useful for testing or when you already have parsed env data.
            existing_env_priority: How to handle variables already in os.environ:
                - "highest": System env vars override all files (default)
                - "lowest": System env vars are overridden by all files
                - "none": Ignore system env vars entirely
                For custom priority, include "os.environ" in env_paths instead.
            cwd: Working directory for resolving relative paths in env_paths.
                - "find_project_root" (default): Auto-detect project root
                - Path or string: Use this specific directory
                - None: Use current working directory
            spec: Specification for expected variables. Keys can be:
                - Exact variable names: "PORT", "DEBUG"
                - Glob patterns: "DB_*", "*_URL"
                - Regex patterns: "/^AWS_.+/i"
                Values can be types, VariableSpec instances, or dicts.
            default_variable_spec: Default specification for variables not in spec.
            allow_extra: Pattern for accepting unspecified variables:
                - "*" or True: Accept all (default)
                - False: Reject unspecified variables
                - Pattern: Accept only matching variables
            docs: Dictionary mapping variable names/patterns to documentation strings.
            defaults: Dictionary mapping variable names/patterns to default values.
            _groups: Internal parameter for tracking group filtering.
            **spec_extra: Additional spec entries as keyword arguments.

        Raises:
            KeyError: When accessing a variable that doesn't match any spec and
                allow_extra doesn't permit it.
            ValueError: When a value fails validation or coercion.
        """
        cwd = find_project_root() if cwd == "find_project_root" else cwd
        # Load and merge all env files, then apply substitutions
        raw_dict = load_env_raw(*env_paths,
                                existing_env_priority=existing_env_priority,
                                cwd=cwd) if raw is None else raw
        self._parsed = {}
        self.default_variable_spec = VariableSpec()
        self._groups = _groups or ()

        self.raw = apply_all_substitutions(raw_dict)
        self.spec = parse_spec(
            spec,
            default_variable_spec=default_variable_spec,
            allow_extra=allow_extra,
            docs=docs,
            defaults=defaults,
            **spec_extra
        )
        self._parsed = {k: self[k] for k in self.keys()}
        super().__init__(self._parsed)


    def __iter__(self):
        """Iterate over raw variable names."""
        return iter(self.raw)

    def get(self, key, default: Any = unspecified, type: str | type | None = unspecified) -> Any:
        """
        Get a variable's value with optional default and type override.

        Retrieves and parses an environment variable. If already parsed and no
        overrides are specified, returns the cached value.
        
        Special value "<default>" in the raw value will use the spec's default.

        Args:
            key: The variable name to retrieve.
            default: Default value if the variable is not set. If not provided,
                uses the default from the variable's spec.
            type: Override the type hint for coercion. If not provided, uses
                the type from the variable's spec.

        Returns:
            The parsed and coerced value.

        Raises:
            KeyError: If the variable is not set and no default is available.

        Example:
            >>> env.get("PORT")
            8080
            >>> env.get("PORT", default=3000)
            8080  # Uses actual value, not default
            >>> env.get("MISSING", default=3000)
            3000
            >>> env.get("PORT", type=str)
            "8080"  # Override coercion
        """
        if default is not unspecified or type is not unspecified or key not in self._parsed:
            spec = self.spec[key]
            s = self.raw.get(key, spec.default if default is unspecified else default)
            # Handle <default> special value - use spec's default
            if s == USE_SPEC_DEFAULT:
                s = spec.default
            return self.parse_value(key, s, type=type)
        return self._parsed[key]

    def parse_value(self, key, s: str, type: str | type | None = unspecified) -> Any:
        """
        Parse a raw string value according to its specification.

        Applies the full processing pipeline: pre -> raw_validator -> coerce -> post -> validator.

        Args:
            key: The variable name (used to look up the spec).
            s: The raw string value to parse.
            type: Optional type override for coercion.

        Returns:
            The fully processed and validated value.

        Raises:
            Exception: If any validator fails or coercion is not possible.
        """
        spec = self.spec[key]
        t = spec.type if type is unspecified else type
        if spec.pre:
            s = spec.pre(s)
        if spec.raw_validator:
            spec.raw_validator(s)
        x = coerce(s, t) if spec.coerce is True else spec.coerce(s) if spec.coerce else s
        if spec.post:
            x = spec.post(x)
        if spec.validator:
            spec.validator(x)
        return x

    def get_as(self, key: str, type, default=None) -> Any:
        """
        Get a variable coerced to a specific type.

        Convenience method that wraps get() with explicit type coercion.

        Args:
            key: The variable name to retrieve.
            type: The type to coerce the value to.
            default: Default value if the variable is not set.

        Returns:
            The value coerced to the specified type.

        Example:
            >>> env.get_as("PORT", int)
            8080
            >>> env.get_as("HOSTS", list)
            ["host1", "host2"]
        """
        return self.get(key, default=default, type=type)

    def get_group(self, *groups: str) -> "Env":
        """
        Get a filtered Env containing only variables in specified groups.

        Creates a new Env instance containing only variables whose specs
        include all of the specified groups.

        Args:
            *groups: Group names to filter by. A variable must belong to ALL
                specified groups to be included.

        Returns:
            A new Env instance with filtered variables.

        Example:
            >>> env = Env(".env", spec={
            ...     "DB_HOST": {"groups": ("database", "required")},
            ...     "DB_PORT": {"groups": ("database",)},
            ...     "API_KEY": {"groups": ("api",)}
            ... })
            >>> db_env = env.get_group("database")
            >>> list(db_env.keys())
            ["DB_HOST", "DB_PORT"]
            >>> required_db = env.get_group("database", "required")
            >>> list(required_db.keys())
            ["DB_HOST"]
        """
        keys = self.spec.get_group(*groups).keys()
        raw = {k: self.raw[k] for k in keys if k in self.raw}
        return Env(raw=raw, spec=self.spec, allow_extra=False, _groups=tuple({*self._groups, *groups}))


    @property
    def parsed(self) -> dict[str, Any]:
        """
        Dictionary of all parsed (coerced) variable values.

        Returns:
            Dictionary mapping variable names to their coerced Python values.
        """
        return self._parsed

    def __getitem__(self, item) -> Any:
        """Allow dict-style access: env["PORT"]."""
        return self.get(item)

    def __getattr__(self, item) -> Any:
        """Allow attribute-style access: env.PORT."""
        return self.get(item)

    def __contains__(self, item) -> bool:
        """Check if a variable exists: "PORT" in env."""
        return item in self.raw

    def keys(self):
        """Return an iterator over variable names."""
        return self.raw.keys()

    def values(self):
        """Return an iterator over parsed variable values."""
        return self.parsed.values()

    def items(self):
        """Return an iterator over (name, value) pairs of parsed variables."""
        return self.parsed.items()

    def __iter__(self):
        """Iterate over parsed variable names."""
        return iter(self.parsed)

    def __repr__(self) -> str:
        """Return a detailed string representation for debugging."""
        g = f"({','.join(self._groups)})" if self._groups else ""
        return f"Env{g}<{self.parsed!r}>"

    def __str__(self) -> str:
        """Return a string representation of the parsed values."""
        return str(self.parsed)

    @property
    def group(self):
        """Alias for get_group method (deprecated, use get_group instead)."""
        return self.get_group

    def __call__(self, *groups) -> "Env":
        """
        Shorthand for get_group().

        Example:
            >>> db_env = Env("database")  # Same as env.get_group("database")
        """
        return self.get_group(*groups)

    def list_groups(self) -> tuple[str, ...]:
        """
        List all unique group names defined in the spec.

        Returns:
            Tuple of all group names used across all variable specs.

        Example:
            >>> env.list_groups()
            ("database", "api", "required", "unknown")
        """
        return self.spec.list_groups()

    @property
    def groups(self) -> dict[str, "Env"]:
        """
        Dictionary of all groups, each mapped to a filtered Env.

        Provides quick access to all group-filtered environments.

        Returns:
            Dictionary mapping group names to filtered Env instances.

        Example:
            >>> env.groups["database"]
            Env(database)<{'DB_HOST': 'localhost', 'DB_PORT': 5432}>
        """
        return {g: self(g) for g in self.list_groups()}



# Default Env instance for convenient access to environment variables.
# Pre-configured with default settings: loads from os.environ with auto-coercion.
#
# Example:
#     >>> from envo import env
#     >>> env.DEBUG
#     True
#     >>> env.PORT
#     8080
env = Env("sample.env", ".env")
