from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal, Any

from envo.coerce import coerce
from envo.load import load_env_raw
from fpr import find_project_root






def apply_all_substitutions(env_dict: dict[str, str]) -> dict[str, str]:
    """
    Apply all substitutions to a dictionary of environment variables.

    This function applies substitutions in order:
    1. % -> project root path
    2. $VAR_NAME -> environment variable references

    This is called AFTER all files are loaded and merged, so all values are available.

    Args:
        env_dict: Dictionary of environment variables (raw strings)

    Returns:
        Dictionary with all substitutions applied
    """
    project_root = find_project_root()
    result = env_dict.copy()

    # Step 1: Substitute % with project root
    for key, value in result.items():
        if '%' in value:
            result[key] = value.replace("%", str(Path(project_root or Path.cwd()).expanduser().resolve()))
    return result

@dataclass
class VariableSpec:
    type: str | type | None = None # passed into the coerce function, call be None to auto-detect
    pre: Callable[[str], str] | None = None # if specified, run pre-coercion
    coerce: bool | Callable[[str], Any] = True # if true, we use our coerce function, if false, we do not coerce at all, if a callable, we call it
    post: Callable[[str], str] | None = None # if specified, run pre-coercion
    raw_validator: Callable[[str], Any] | None = None# if specified, run after pre. should throw an exception if it fails
    validator: Callable[[Any], Any] | None = None # if specified, run after post. should throw an exception if it fails
    default: str = None

unspecified = object()

class Env:
    def __init__(self, *env_paths: str | Literal["os.environ"] | Path,
                 existing_env_priority: Literal["none", "highest", "lowest"] | None = None,
                 cwd: str | Path | None ="find_project_root",
                 spec: dict[str | re.Pattern, VariableSpec | dict | str | type] = None,
                 default_variable_spec: VariableSpec | dict | str | type | None | Callable[[str], Any] = None,
                 allow_extra: str | re.Pattern | bool = "*"
                 ):
        cwd = find_project_root() if cwd == "find_project_root" else cwd
        # Load and merge all env files, then apply substitutions
        raw_dict = load_env_raw(*env_paths,
                                existing_env_priority=existing_env_priority,
                                cwd=cwd)
        self.raw = apply_all_substitutions(raw_dict)
        self.default_variable_spec = VariableSpec()
        self.default_variable_spec = self.parse_variable_spec(default_variable_spec)
        self.spec = self.parse_spec(spec if spec is not None else {})
        if allow_extra:
            self.spec[self.parse_spec_key(allow_extra)] = self.default_variable_spec

    def parse_variable_spec(self, v: VariableSpec | dict | str | type | None | Callable[[str], Any]):
        if v is None:
            return self.default_variable_spec
        if isinstance(v, VariableSpec):
            v2 = v
        elif isinstance(v, dict):
            v2 = VariableSpec(**v)
        elif isinstance(v, str | type):
            v2 = VariableSpec(type=v)
        elif isinstance(v, Callable):
            v2 = VariableSpec(coerce=v)
        else:
            raise ValueError(f"Unknown spec: {v}")
        return v2


    def parse_spec_key(self, k: str | re.Pattern) -> str | re.Pattern:
        if isinstance(k, re.Pattern):
            k2 = k
        elif re.match("[a-zA-Z_\-\d]+", k):
            k2 = k
        elif re.match("[a-zA-Z_\-\d\*]+", k):
            k2 = re.compile(k.replace("*", ".*"))
        elif m:= re.match('r?/(.*)/([imsxal]*)', k):
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

    def parse_spec(self, spec: dict[str | re.Pattern, VariableSpec | dict | str | type | None | Callable[[str], Any]]) -> dict[str | re.Pattern, VariableSpec]:
        p = {}
        for k, v in spec.items():
            v2 = self.parse_variable_spec(v)
            k2 = self.parse_spec_key(k)
            p[k2] = v2
        return p

    def get_spec(self, key: str) -> VariableSpec:
        if key in self.spec:
            return self.spec[key]
        else:
            for k, v in self.spec.items():
                if isinstance(k, re.Pattern) and k.match(key):
                    return v
        raise KeyError(f"Unexpected key: {key}")

    def __iter__(self):
        return iter(self.raw)

    def get(self, key, default: Any = unspecified, type: str | type | None = unspecified) -> Any:
        spec = self.get_spec(key)
        s = self.raw.get(key, spec.default if default is unspecified else default)
        t = spec.type if type is unspecified else type
        if spec.pre:
            s = spec.pre(s)
        if spec.raw_validator:
            spec.raw_validator(s)
        x = coerce(s, t) if spec.coerce is None else spec.coerce(s)
        if spec.post:
            x = spec.post(x)
        if spec.validator:
            spec.validator(x)
        return x

    def get_as(self, key: str, type, default=None):
        return self.get(key, default=default, type=type)

    @property
    def parsed(self):
        return {k: self[k] for k in self.keys()}

    def __getitem__(self, item):
        return self.get(item)

    def __getattr__(self, item):
        return self.get(item)

    def __contains__(self, item):
        return item in self.raw

    def keys(self):
        return self.keys()

    def values(self):
        return self.parsed.values()

    def __iter__(self):
        return iter(self.parsed)




env = Env()
