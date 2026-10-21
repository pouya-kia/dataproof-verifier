"""Regressions for reused CLI output directories."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from dataproof_verifier.cli import check
from dataproof_verifier.replay import ReplayResult, validate_serialized
from dataproof_verifier.solver import SearchResult
from dataproof_verifier.status import EXIT_CODES


def test_success_then_bounded_cannot_leave_stale_evidence(
    base_spec: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = deepcopy(base_spec)
    raw["output_dir"] = str(tmp_path / "out")
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == EXIT_CODES["COUNTEREXAMPLE_FOUND"]
    assert (tmp_path / "out/witness.json").exists()
    assert (tmp_path / "out/replay.sql").exists()
    monkeypatch.setattr(
        "dataproof_verifier.cli.search",
        lambda *_: SearchResult("BOUNDED_NO_COUNTEREXAMPLE", None, None),
    )
    assert check(path, None, False) == EXIT_CODES["BOUNDED_NO_COUNTEREXAMPLE"]
    assert json.loads((tmp_path / "out/result.json").read_text())["status"] == (
        "BOUNDED_NO_COUNTEREXAMPLE"
    )
    assert not (tmp_path / "out/witness.json").exists()
    assert not (tmp_path / "out/replay.sql").exists()


@pytest.mark.parametrize("failure", ["bounded", "inconclusive", "invalid_candidate", "backend"])
def test_success_to_failure_and_back(
    base_spec: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    raw = deepcopy(base_spec)
    output = tmp_path / "out"
    raw["output_dir"] = str(output)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    sentinel = output / "notes.txt"
    assert check(path, None, False) == 0
    sentinel.write_text("keep me", encoding="utf-8")
    original_hash = json.loads((output / "witness.json").read_text())["worlds_sha256"]

    def broken(*args: Any) -> SearchResult:
        if failure == "backend":
            raise RuntimeError("injected backend fault")
        if failure == "invalid_candidate":
            same = ((date(2026, 1, 1), 1, 10),)
            return SearchResult("CANDIDATE", (same, same), None)
        if failure == "inconclusive":
            return SearchResult("INCONCLUSIVE", None, "timeout")
        return SearchResult("BOUNDED_NO_COUNTEREXAMPLE", None, None)

    with monkeypatch.context() as patcher:
        patcher.setattr("dataproof_verifier.cli.search", broken)
        code = check(path, None, False)
    expected = {
        "bounded": "BOUNDED_NO_COUNTEREXAMPLE",
        "inconclusive": "INCONCLUSIVE",
        "invalid_candidate": "INVALID_CANDIDATE",
        "backend": "INCONCLUSIVE",
    }[failure]
    assert code == EXIT_CODES["INCONCLUSIVE_UNKNOWN" if failure == "backend" else expected]
    result = json.loads((output / "result.json").read_text())
    assert result["status"] == expected
    assert "witness_path" not in result
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()
    assert sentinel.read_text(encoding="utf-8") == "keep me"
    for _ in range(2):
        assert check(path, None, False) == 0
        result = json.loads((output / "result.json").read_text())
        assert result["status"] == "COUNTEREXAMPLE_FOUND"
        assert json.loads((output / "witness.json").read_text())["worlds_sha256"] == (original_hash)
        assert validate_serialized(output / "witness.json").valid
        assert (output / "replay.sql").exists()
    assert sentinel.read_text(encoding="utf-8") == "keep me"


def test_invalid_input_with_explicit_output_clears_owned_evidence(
    base_spec: dict[str, Any], tmp_path: Path
) -> None:
    raw = deepcopy(base_spec)
    output = tmp_path / "out"
    raw["output_dir"] = str(output)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == 0
    path.write_text("{broken json", encoding="utf-8")
    assert check(path, output, False) == EXIT_CODES["INVALID_INPUT"]
    assert json.loads((output / "result.json").read_text())["status"] == "INVALID_INPUT"
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == 0


def test_invalid_schema_with_embedded_output_clears_owned_evidence(
    base_spec: dict[str, Any], tmp_path: Path
) -> None:
    raw = deepcopy(base_spec)
    output = tmp_path / "out"
    raw["output_dir"] = str(output)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == 0
    raw["max_rows"] = "bad"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == EXIT_CODES["INVALID_INPUT"]
    assert json.loads((output / "result.json").read_text())["status"] == "INVALID_INPUT"
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()


@pytest.mark.parametrize("view", ["SELECT ) FROM orders", "DELETE FROM orders"])
def test_bad_sql_with_embedded_output_clears_owned_evidence(
    base_spec: dict[str, Any], tmp_path: Path, view: str
) -> None:
    raw = deepcopy(base_spec)
    output = tmp_path / "out"
    raw["output_dir"] = str(output)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == 0
    raw["views"] = [view]
    path.write_text(json.dumps(raw), encoding="utf-8")
    code = check(path, None, False)
    expected = "UNSUPPORTED" if view.startswith("DELETE") else "INVALID_INPUT"
    assert code == EXIT_CODES[expected]
    assert json.loads((output / "result.json").read_text())["status"] == expected
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()


def test_unowned_or_modified_artifacts_are_never_deleted(
    base_spec: dict[str, Any], tmp_path: Path
) -> None:
    raw = deepcopy(base_spec)
    output = tmp_path / "out"
    raw["output_dir"] = str(output)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    output.mkdir()
    unowned = output / "witness.json"
    unowned.write_text("user data", encoding="utf-8")
    assert check(path, None, False) == EXIT_CODES["INVALID_INPUT"]
    assert unowned.read_text(encoding="utf-8") == "user data"
    unowned.unlink()
    assert check(path, None, False) == 0
    unowned.write_text("modified by user", encoding="utf-8")
    assert check(path, None, False) == EXIT_CODES["INVALID_INPUT"]
    assert unowned.read_text(encoding="utf-8") == "modified by user"
    assert (output / "replay.sql").exists()


def test_backend_failure_after_candidate_move_removes_current_evidence(
    base_spec: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataproof_verifier.cli as cli

    raw = deepcopy(base_spec)
    output = tmp_path / "out"
    raw["output_dir"] = str(output)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == 0
    original = cli.validate_serialized
    calls = 0

    def fail_after_move(witness: Path) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("replay failed after move")
        return original(witness)

    monkeypatch.setattr(cli, "validate_serialized", fail_after_move)
    assert check(path, None, False) == EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    assert calls == 2
    assert json.loads((output / "result.json").read_text())["status"] == "INCONCLUSIVE"
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()


def test_invalid_candidate_diagnostics_are_owned_and_cleared_on_next_run(
    base_spec: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataproof_verifier.cli as cli

    raw = deepcopy(base_spec)
    output = tmp_path / "out"
    raw["output_dir"] = str(output)
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    original = cli.validate_serialized
    calls = 0

    def reject_after_move(witness: Path) -> ReplayResult:
        nonlocal calls
        calls += 1
        if calls == 2:
            return ReplayResult(False, ((), ()), (None, None), "injected disagreement")
        return original(witness)

    with monkeypatch.context() as patcher:
        patcher.setattr(cli, "validate_serialized", reject_after_move)
        assert check(path, None, False) == EXIT_CODES["INVALID_CANDIDATE"]
    assert (output / "invalid_candidate.json").exists()
    assert (output / "invalid_candidate.sql").exists()
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()
    assert check(path, None, False) == 0
    assert not (output / "invalid_candidate.json").exists()
    assert not (output / "invalid_candidate.sql").exists()
    assert validate_serialized(output / "witness.json").valid
