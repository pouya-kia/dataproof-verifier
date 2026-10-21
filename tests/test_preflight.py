"""Static preflight must mirror production validation without doing a search."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from dataproof_verifier import preflight
from dataproof_verifier.doppel_model import load_doppel_spec
from dataproof_verifier.models import SpecError, UnsupportedError, load_spec
from dataproof_verifier.parser import parse_query

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/preflight"


def _run_cli(workflow: str, path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "dataproof_verifier", "preflight", workflow, str(path), "--json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _mutated(tmp_path: Path, source: Path, change: dict[str, Any]) -> Path:
    data = json.loads(source.read_text(encoding="utf-8"))
    data.update(change)
    path = tmp_path / "case.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("workflow", "filename"),
    [
        ("no-undo", "no_undo_starter.json"),
        ("doppelganger", "doppelganger_starter.json"),
    ],
)
def test_starters_pass_real_validation_and_cli(workflow: str, filename: str) -> None:
    path = EXAMPLES / filename
    if workflow == "no-undo":
        spec = load_spec(path)
        parse_query(spec.views[0], spec, metric=False)
        parse_query(spec.metric, spec, metric=True)
    else:
        load_doppel_spec(path)
    run = _run_cli(workflow, path)
    assert run.returncode == 0, run.stderr
    data = json.loads(run.stdout)
    assert data["status"] == "ELIGIBLE"
    assert data["limits"]["max_rows_per_world"] == 3
    assert data["limits"]["timeout_ms"] == "1..30000"
    assert "does not guarantee a witness" in data["note"]


@pytest.mark.parametrize(
    ("workflow", "path"),
    [
        ("no-undo", ROOT / "examples/no_undo/daily_distinct.json"),
        ("no-undo", ROOT / "examples/no_undo/daily_sum.json"),
        ("no-undo", ROOT / "examples/no_undo/constrained_customer.json"),
        ("no-undo", ROOT / "examples/no_undo/filtered_customers.json"),
        ("no-undo", ROOT / "examples/no_undo/integer_extrema.json"),
        ("doppelganger", ROOT / "examples/doppelganger/nonnegative_amount.json"),
    ],
)
def test_existing_accepted_specs_remain_eligible(workflow: str, path: Path) -> None:
    assert json.loads(_run_cli(workflow, path).stdout)["status"] == "ELIGIBLE"


def test_unsupported_join_names_clause() -> None:
    run = _run_cli("no-undo", EXAMPLES / "unsupported_join.json")
    assert run.returncode == 5
    result = json.loads(run.stdout)
    assert result["status"] == "UNSUPPORTED"
    assert "JOIN" in result["reason"]


@pytest.mark.parametrize(
    ("workflow", "filename", "change", "expected"),
    [
        ("no-undo", "no_undo_starter.json", {"max_rows": 4}, "INVALID_INPUT"),
        ("no-undo", "no_undo_starter.json", {"max_rows": "2"}, "INVALID_INPUT"),
        ("no-undo", "no_undo_starter.json", {"metric": 7}, "INVALID_INPUT"),
        ("no-undo", "no_undo_starter.json", {"views": []}, "INVALID_INPUT"),
        (
            "no-undo",
            "no_undo_starter.json",
            {"metric": "SELECT COUNT(*) AS n FROM orders HAVING COUNT(*) > 0"},
            "UNSUPPORTED",
        ),
        (
            "no-undo",
            "no_undo_starter.json",
            {"metric": "SELECT COUNT(*) AS n FROM orders WHERE customer_id = 1 AND day IS NULL"},
            "UNSUPPORTED",
        ),
        ("doppelganger", "doppelganger_starter.json", {"tests": []}, "INVALID_INPUT"),
        ("doppelganger", "doppelganger_starter.json", {"max_rows": 4}, "INVALID_INPUT"),
    ],
)
def test_preflight_matches_production_validation_boundary(
    tmp_path: Path, workflow: str, filename: str, change: dict[str, Any], expected: str
) -> None:
    path = _mutated(tmp_path, EXAMPLES / filename, change)
    with pytest.raises((SpecError, UnsupportedError)) as exc:
        if workflow == "no-undo":
            spec = load_spec(path)
            parse_query(spec.views[0], spec, metric=False)
            parse_query(spec.metric, spec, metric=True)
        else:
            load_doppel_spec(path)
    run = _run_cli(workflow, path)
    result = json.loads(run.stdout)
    assert result["status"] == expected
    assert result["reason"] == str(exc.value)
    assert run.returncode == (5 if expected == "UNSUPPORTED" else 6)


def test_bad_json_missing_file_and_invalid_domain(tmp_path: Path) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{", encoding="utf-8")
    for path in (bad_json, tmp_path / "missing.json"):
        run = _run_cli("no-undo", path)
        assert run.returncode == 6
        assert json.loads(run.stdout)["status"] == "INVALID_INPUT"
    data = json.loads((EXAMPLES / "no_undo_starter.json").read_text())
    data["table"]["columns"][0]["domain"] = ["not-a-date"]
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(data), encoding="utf-8")
    assert json.loads(_run_cli("no-undo", invalid).stdout)["status"] == "INVALID_INPUT"


def test_unsupported_type_and_column_bound(tmp_path: Path) -> None:
    source = EXAMPLES / "no_undo_starter.json"
    data = json.loads(source.read_text())
    data["table"]["columns"][0]["type"] = "VARCHAR"
    path = tmp_path / "type.json"
    path.write_text(json.dumps(data))
    assert json.loads(_run_cli("no-undo", path).stdout)["status"] == "UNSUPPORTED"
    data["table"]["columns"] *= 3
    path.write_text(json.dumps(data))
    assert json.loads(_run_cli("no-undo", path).stdout)["status"] == "INVALID_INPUT"


def test_preflight_never_searches_executes_sql_or_writes_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import dataproof_verifier.cli
    import dataproof_verifier.doppel_cli
    import dataproof_verifier.doppel_replay
    import dataproof_verifier.replay

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("preflight tried to search or execute SQL")

    monkeypatch.setattr(dataproof_verifier.cli, "search", forbidden)
    monkeypatch.setattr(dataproof_verifier.doppel_cli, "search", forbidden)
    monkeypatch.setattr(dataproof_verifier.replay, "_connection", forbidden)
    monkeypatch.setattr(dataproof_verifier.doppel_replay, "_connection", forbidden)
    for workflow, filename in (
        ("no-undo", "no_undo_starter.json"),
        ("doppelganger", "doppelganger_starter.json"),
    ):
        output = tmp_path / workflow
        input_path = _mutated(
            tmp_path, EXAMPLES / filename, {"output_dir": str(output), "timeout_ms": 1}
        )
        assert preflight.check(workflow, input_path, True) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "ELIGIBLE"
        assert not output.exists()
    owned = tmp_path / "existing"
    owned.mkdir()
    sentinel = owned / "result.json"
    sentinel.write_text("do not touch", encoding="utf-8")
    input_path = _mutated(tmp_path, EXAMPLES / "no_undo_starter.json", {"output_dir": str(owned)})
    assert preflight.check("no-undo", input_path, False) == 0
    assert sentinel.read_text(encoding="utf-8") == "do not touch"


def test_unexpected_validation_error_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(path: Path) -> None:
        raise RuntimeError("do not expose internal details")

    monkeypatch.setattr(preflight, "load_spec", broken)
    assert preflight.check("no-undo", EXAMPLES / "no_undo_starter.json", True) == 8
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "INCONCLUSIVE"
    assert result["reason_code"] == "VALIDATION_ERROR"
    assert "internal details" not in json.dumps(result)
