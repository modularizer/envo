"""
Environment variable loading, parsing, and type coercion.

This module provides the core `Env` class for loading environment variables from
multiple sources (.env files, os.environ), applying substitutions, and coercing
values to appropriate Python types.

Default loading priority (lowest to highest):
1. Spec file defaults (sample.env or .env.sample)
2. .env file
3. System environment variables (os.environ)

Example:
    >>> from envo import Env
    >>> env = Env()  # Auto-discovers spec and .env files
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
from envo.load import load_env_raw, resolve_var_references
from fpr import find_project_root

from envo.sentinel import unspecified
from envo.spec_type import parse_variable_spec, VariableSpecInput, VariableSpec, parse_spec_key, parse_spec, EnvSpec

# Special value that indicates "use the default from spec"
USE_SPEC_DEFAULT = "<default>"

# Default file names for auto-discovery
DEFAULT_ENV_FILE = ".env"
DEFAULT_SPEC_FILES = ("sample.env", ".env.sample")


def find_default_spec(cwd: Path | None = None) -> Path | None:
    """
    Find the default spec file in the project root.
    
    Searches for sample.env or .env.sample in order.
    
    Args:
        cwd: Directory to search in (defaults to project root)
        
    Returns:
        Path to spec file if found, None otherwise
    """
    if cwd is None:
        cwd = find_project_root()
        if not cwd:
            cwd = Path.cwd()
        else:
            cwd = Path(cwd)
    
    for name in DEFAULT_SPEC_FILES:
        path = cwd / name
        if path.exists():
            return path
    return None


def find_default_env(cwd: Path | None = None) -> Path | None:
    """
    Find the default env file in the project root.
    
    Args:
        cwd: Directory to search in (defaults to project root)
        
    Returns:
        Path to .env file if found, None otherwise
    """
    if cwd is None:
        cwd = find_project_root()
        if not cwd:
            cwd = Path.cwd()
        else:
            cwd = Path(cwd)
    
    path = cwd / DEFAULT_ENV_FILE
    if path.exists():
        return path
    return None


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
        spec: dict[str | re.Pattern, VariableSpec | dict | str | type] | EnvSpec | str | Path | None = "auto",
        spec_file: str | Path | None = None,
        default_variable_spec: VariableSpec | dict | str | type | None | Callable[[str], Any] = None,
        allow_extra: str | re.Pattern | bool = "*",
        docs: dict[str | re.Pattern, str] = None,
        defaults: dict[str | re.Pattern, str] = None,
        export_to_environ: bool = True,
        _groups: tuple | None = None,
        **spec_extra,
    ):
        """
        Initialize an Env instance.
        
        Default behavior (no arguments):
            1. Auto-discover spec from sample.env or .env.sample
            2. Load spec defaults at lowest priority
            3. Load .env if it exists
            4. Load os.environ at highest priority

        Args:
            *env_paths: Paths to .env files to load, in order from lowest to highest
                priority. Later files override earlier ones. Use the literal string
                "os.environ" to include system environment variables at that priority.
                If not provided, auto-discovers .env in project root.
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
            spec: Specification for expected variables:
                - "auto" (default): Auto-discover from sample.env/.env.sample
                - None: No spec (just load raw values)
                - dict: Variable specs (keys can be names, globs, or regex patterns)
                - EnvSpec: Pre-parsed spec object
                - str/Path: Path to spec file
            spec_file: Explicit path to spec file (alternative to spec parameter)
            default_variable_spec: Default specification for variables not in spec.
            allow_extra: Pattern for accepting unspecified variables:
                - "*" or True: Accept all (default)
                - False: Reject unspecified variables
                - Pattern: Accept only matching variables
            docs: Dictionary mapping variable names/patterns to documentation strings.
            defaults: Dictionary mapping variable names/patterns to default values.
            export_to_environ: If True (default), set all resolved values back to
                os.environ so they're available to subprocesses and other libraries.
            _groups: Internal parameter for tracking group filtering.
            **spec_extra: Additional spec entries as keyword arguments.

        Raises:
            KeyError: When accessing a variable that doesn't match any spec and
                allow_extra doesn't permit it.
            ValueError: When a value fails validation or coercion.
        """
        # Resolve cwd
        if cwd == "find_project_root":
            cwd = find_project_root()
        if cwd:
            cwd = Path(cwd)
        else:
            cwd = Path.cwd()
        
        self._parsed = {}
        self.default_variable_spec = VariableSpec()
        self._groups = _groups or ()
        
        # Handle spec - can be "auto", None, dict, EnvSpec, or path
        parsed_spec = None
        spec_defaults = {}
        
        if spec_file:
            # Explicit spec file path
            from envo.parse_spec import env_file_to_spec
            parsed_spec = env_file_to_spec(spec_file, cwd=cwd)
        elif spec == "auto":
            # Auto-discover spec file
            spec_path = find_default_spec(cwd)
            if spec_path:
                from envo.parse_spec import env_file_to_spec
                parsed_spec = env_file_to_spec(spec_path, cwd=cwd)
        elif isinstance(spec, (str, Path)):
            # Spec is a file path
            from envo.parse_spec import env_file_to_spec
            parsed_spec = env_file_to_spec(spec, cwd=cwd)
        elif isinstance(spec, EnvSpec):
            # Already parsed
            parsed_spec = spec
        elif isinstance(spec, dict):
            # Parse spec dict
            parsed_spec = parse_spec(
                spec,
                default_variable_spec=default_variable_spec,
                allow_extra=allow_extra,
                docs=docs,
                defaults=defaults,
                **spec_extra
            )
        elif spec is None:
            # No spec
            parsed_spec = parse_spec(
                {},
                default_variable_spec=default_variable_spec,
                allow_extra=allow_extra,
                **spec_extra
            )
        
        # If we loaded a spec from file, ensure allow_extra is applied
        if parsed_spec is not None and not isinstance(spec, dict) and spec is not None:
            # Add catch-all pattern if allow_extra is set and not already present
            if allow_extra:
                from envo.spec_type import parse_spec_key
                catch_all_key = parse_spec_key(allow_extra)
                # Check if there's already a catch-all
                has_catchall = any(
                    isinstance(k, re.Pattern) and parsed_spec._is_catchall_pattern(k)
                    for k in parsed_spec.keys()
                )
                if not has_catchall:
                    parsed_spec[catch_all_key] = parse_variable_spec(default_variable_spec)
            
            # Apply any additional spec options
            if spec_extra or docs or defaults:
                additional = parse_spec(
                    spec_extra,
                    default_variable_spec=default_variable_spec,
                    allow_extra=False,  # Don't add another catch-all
                    docs=docs,
                    defaults=defaults,
                )
                # Merge additional specs
                for k, v in additional.items():
                    if k not in parsed_spec:
                        parsed_spec[k] = v
        
        self.spec = parsed_spec or parse_spec({}, allow_extra=allow_extra)
        
        # Extract defaults from spec for lowest-priority loading
        for key, var_spec in self.spec.items():
            if isinstance(key, str) and var_spec.default is not None:
                spec_defaults[key] = var_spec.default
        
        # Build env loading chain
        if raw is not None:
            # Direct raw dict provided
            raw_dict = raw
        else:
            # Auto-discover env paths if none provided
            if not env_paths:
                default_env = find_default_env(cwd)
                if default_env:
                    env_paths = (str(default_env),)
                else:
                    env_paths = ()
            
            # Load env files
            raw_dict = load_env_raw(*env_paths,
                                    existing_env_priority=existing_env_priority,
                                    cwd=cwd)
        
        # Merge: spec_defaults (lowest) <- raw_dict (higher)
        merged = {**spec_defaults, **raw_dict}
        
        # Resolve variable references (e.g., $VAR_NAME) in the merged dict
        merged = resolve_var_references(merged)
        
        self.raw = apply_all_substitutions(merged)
        self._parsed = {k: self[k] for k in self.keys()}
        super().__init__(self._parsed)
        
        # Export resolved values back to os.environ
        if export_to_environ:
            self._export_to_environ()


    def __iter__(self):
        """Iterate over raw variable names."""
        return iter(self.raw)

    def _export_to_environ(self) -> None:
        """
        Export all resolved raw string values to os.environ.
        
        This makes the loaded and resolved values available to subprocesses
        and other libraries that read from os.environ directly.
        """
        import os
        for key, value in self.raw.items():
            if value is not None:
                os.environ[key] = str(value)
            elif key in os.environ:
                # If value is None and key exists in environ, remove it
                del os.environ[key]

    def export_to_environ(self) -> None:
        """
        Manually export all resolved values to os.environ.
        
        Call this if you created the Env with export_to_environ=False
        and later want to export the values.
        """
        self._export_to_environ()

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
        filtered_spec = self.spec.get_group(*groups)
        keys = filtered_spec.keys()
        raw = {k: self.raw[k] for k in keys if k in self.raw}
        return Env(raw=raw, spec=filtered_spec, allow_extra=False, _groups=tuple({*self._groups, *groups}))


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
# Pre-configured with default settings:
#   1. Auto-discovers spec from sample.env or .env.sample
#   2. Loads spec defaults at lowest priority
#   3. Loads .env if it exists
#   4. Loads os.environ at highest priority
#
# Example:
#     >>> from envo import env
#     >>> env.DEBUG
#     True
#     >>> env.PORT
#     8080
env = Env()
