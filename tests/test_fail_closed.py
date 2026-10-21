"""Fault injection at solver and independent-validation boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import z3

from dataproof_verifier.cli import check
from dataproof_verifier.models import parse_spec
from dataproof_verifier.parser import parse_query
from dataproof_verifier.solver import search
from dataproof_verifier.status import EXIT_CODES


def _queries(raw: dict[str, Any]) -> tuple[Any, Any, Any]:
    spec = parse_spec(raw)
    return (
        spec,
        parse_query(spec.views[0], spec, metric=False),
        parse_query(spec.metric, spec, metric=True),
    )


@pytest.mark.parametrize(
    ("reason", "expected"),
    [("timeout", "TIMEOUT"), ("max. memory exceeded", "MEMORY_LIMIT"), ("incomplete", "UNKNOWN")],
)
def test_z3_unknown_is_inconclusive(
    base_spec: dict[str, Any], monkeypatch: pytest.MonkeyPatch, reason: str, expected: str
) -> None:
    monkeypatch.setattr(z3.Optimize, "check", lambda self: z3.unknown)
    monkeypatch.setattr(z3.Optimize, "reason_unknown", lambda self: reason)
    result = search(*_queries(base_spec))
    assert result.status == "INCONCLUSIVE"
    assert result.worlds is None
    assert result.reason_code == expected


@pytest.mark.parametrize("exc", [z3.Z3Exception("broken"), MemoryError()])
def test_z3_exception_is_inconclusive(
    base_spec: dict[str, Any], monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    def fail(self: Any) -> Any:
        raise exc

    monkeypatch.setattr(z3.Optimize, "check", fail)
    result = search(*_queries(base_spec))
    assert result.status == "INCONCLUSIVE"
    assert result.worlds is None
    assert result.reason_code == (
        "MEMORY_LIMIT" if isinstance(exc, MemoryError) else "SOLVER_ERROR"
    )


@pytest.mark.parametrize("boundary", ["search", "validate", "validate_serialized"])
def test_unexpected_backend_failure_cannot_publish_witness(
    base_spec: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    raw = dict(base_spec)
    raw["output_dir"] = str(tmp_path / "out")
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(raw), encoding="utf-8")

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("backend broke")

    monkeypatch.setattr(f"dataproof_verifier.cli.{boundary}", fail)
    assert check(spec_path, None, False) == EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    result = json.loads((tmp_path / "out/result.json").read_text())
    assert result["status"] == "INCONCLUSIVE"
    assert result["reason_code"] == "BACKEND_ERROR"
    assert not (tmp_path / "out/witness.json").exists()
