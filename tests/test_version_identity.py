"""Source version and distribution metadata must not diverge in release builds."""

from __future__ import annotations

import tomllib
from pathlib import Path

from dataproof_verifier import __version__


def test_source_version_matches_pyproject() -> None:
    project = Path(__file__).resolve().parents[1] / "pyproject.toml"
    metadata = tomllib.loads(project.read_text(encoding="utf-8"))
    assert __version__ == metadata["project"]["version"]
