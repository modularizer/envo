from pathlib import Path
from typing import Literal

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




class Env:
    def __init__(self, *env_paths: str | Literal["os.environ"] | Path,
                 existing_env_priority: Literal["none", "highest", "lowest"] | None = None,
                 cwd: str | Path | None ="find_project_root"):
        cwd = find_project_root() if cwd == "find_project_root" else cwd
        # Load and merge all env files, then apply substitutions
        raw_dict = load_env_raw(*env_paths,
                                existing_env_priority=existing_env_priority,
                                cwd=cwd)
        self.raw = apply_all_substitutions(raw_dict)

    def __iter__(self):
        return iter(self.raw)

    def get(self, key, default=None, type=None):
        s = self.raw.get(key, default)
        return coerce(s, type)

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
