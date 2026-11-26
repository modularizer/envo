"""Verify explicit environment loading and import isolation."""

import os
import subprocess
import sys
from pathlib import Path

from envo import Env


def test_import_does_not_load_or_export(tmp_path: Path) -> None:
    """Importing envo must not consume or export a neighboring dotenv specification."""
    (tmp_path / "sample.env").write_text("ENVO_IMPORT_PROBE=default\n", encoding="utf-8")
    (tmp_path / ".env").write_text("ENVO_IMPORT_PROBE=override\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-c", "import os; before = dict(os.environ); import envo; assert dict(os.environ) == before"],
        cwd=tmp_path, check=False, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_explicit_sources_and_no_export(tmp_path: Path) -> None:
    """Explicit loading resolves file values without changing process variables."""
    path = tmp_path / ".env"
    path.write_text("ENVO_EXAMPLE=42\n", encoding="utf-8")
    before = dict(os.environ)
    environment = Env(path, spec={"ENVO_EXAMPLE": int}, existing_env_priority="none", export_to_environ=False)
    assert environment["ENVO_EXAMPLE"] == 42
    assert dict(os.environ) == before
