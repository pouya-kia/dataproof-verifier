"""Read-only witness explanation and evidence-integrity regressions."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from dataproof_verifier import cli, doppel_cli, explain
from dataproof_verifier.doppel_model import parse_doppel_spec
from dataproof_verifier.doppel_replay import (
    evaluation_mapping,
    make_replay_sql,
    rows_hash,
    validate,
)
from dataproof_verifier.models import parse_spec
from dataproof_verifier.replay import serialize_rows
from dataproof_verifier.replay import validate as validate_no_undo
from dataproof_verifier.report import result_data, write_result, write_witness

ROOT = Path(__file__).resolve().parents[1]


def _copy_evidence(tmp_path: Path, module: str) -> Path:
    source = ROOT / "examples" / module / "evidence"
    for name in ("witness.json", "result.json", "replay.sql"):
        shutil.copy2(source / name, tmp_path / name)
    return tmp_path / "witness.json"


def _hashes(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}


def test_no_undo_example_is_deterministic_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    witness = _copy_evidence(tmp_path, "no_undo")
    monkeypatch.setattr(cli, "search", lambda *_: pytest.fail("solver invoked"))
    before = _hashes(tmp_path)
    first = explain.explain(witness)
    assert first == explain.explain(witness)
    assert "KPI monthly_customers: D1 = 1; D2 = 2 — DIFFERENT" in first
    assert "EQUAL as unordered SQL bags" in first
    assert 'DATE "2026-01-01"' in first
    assert "order_count, revenue_sum, daily_customers" in first
    assert "0..2 rows per dataset" in first
    assert "REPLAY_OK" in first
    assert cli.explain(witness) == 0
    assert _hashes(tmp_path) == before


def test_doppel_example_is_deterministic_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    witness = _copy_evidence(tmp_path, "doppelganger")
    monkeypatch.setattr(doppel_cli, "search", lambda *_: pytest.fail("solver invoked"))
    before = _hashes(tmp_path)
    first = explain.explain(witness)
    assert first == explain.explain(witness)
    assert "(-1) x 1" in first
    assert "has_orders: 1 >= 1 = TRUE" in first
    assert "no_negative_amount: 1 = 0 = FALSE — VIOLATED" in first
    assert "User-supplied rationale" in first
    assert "FALSE and UNKNOWN would not pass" in first
    assert cli.explain(witness) == 0
    assert _hashes(tmp_path) == before


def test_no_undo_bag_null_group_and_scalar_sum(tmp_path: Path) -> None:
    raw = {
        "table": {
            "name": "orders",
            "columns": [
                {"name": "day", "type": "DATE", "nullable": True, "domain": [None, "2026-01-01"]},
                {"name": "amount", "type": "INTEGER", "nullable": True, "domain": [None, 1]},
            ],
        },
        "views": ["SELECT day, COUNT(*) AS n FROM orders GROUP BY day"],
        "metric": "SELECT SUM(amount) AS total FROM orders WHERE day IS NOT NULL",
        "max_rows": 3,
        "output_dir": str(tmp_path),
    }
    spec = parse_spec(raw)
    d1 = ((None, None), (None, None), (date(2026, 1, 1), None))
    d2 = ((None, None), (None, None), (date(2026, 1, 1), 1))
    checked = validate_no_undo(spec, d1, d2)
    assert checked.valid
    result = result_data(spec, "COUNTEREXAMPLE_FOUND", None, "synthetic-input")
    result.update(
        witness_path=str(tmp_path / "witness.json"),
        replay_sql_path=str(tmp_path / "replay.sql"),
        view_rows=[list(map(list, view)) for view in checked.views],
        metric_values=list(checked.metrics),
    )
    write_witness(spec, result, d1, d2)
    write_result(spec, result)
    output = explain.explain(tmp_path / "witness.json")
    assert "(NULL, NULL) x 2" in output
    assert "(NULL, 2) x 1" in output
    assert 'DATE "2026-01-01"' in output
    assert "KPI total: D1 = NULL; D2 = 1 — DIFFERENT" in output


def test_doppel_duplicate_null_bag_and_unknown_display(tmp_path: Path) -> None:
    raw = {
        "schema_version": 1,
        "table": {
            "name": "orders",
            "columns": [{"name": "amount", "type": "INTEGER", "nullable": True, "domain": [None]}],
            "unique": [["amount"]],
        },
        "max_rows": 2,
        "output_dir": str(tmp_path),
        "tests": [
            {"id": "two_rows", "sql": "SELECT COUNT(*) AS n FROM orders", "op": "=", "value": 2}
        ],
        "invariant": {
            "id": "all_present",
            "sql": "SELECT COUNT(amount) AS n FROM orders",
            "op": "=",
            "value": 2,
            "rationale": "Éléments must not be NULL.\nNo terminal control.",
        },
    }
    spec = parse_doppel_spec(raw)
    rows = ((None,), (None,))
    checked = validate(spec, rows)
    assert checked.valid and checked.invariant is not None
    source = tmp_path / "input.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    result = doppel_cli._result(spec, source, "BLIND_SPOT_FOUND", None)
    result.update(
        test_evaluations=[evaluation_mapping(item) for item in checked.tests],
        invariant_evaluation=evaluation_mapping(checked.invariant),
        witness_path=str(tmp_path / "witness.json"),
        replay_sql_path=str(tmp_path / "replay.sql"),
    )
    witness = {**result, "rows": serialize_rows(rows), "rows_sha256": rows_hash(rows)}
    (tmp_path / "witness.json").write_text(json.dumps(witness), encoding="utf-8")
    (tmp_path / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (tmp_path / "replay.sql").write_text(make_replay_sql(spec, rows), encoding="utf-8")
    output = explain.explain(tmp_path / "witness.json")
    assert "(NULL) x 2" in output
    assert "all_present: 0 = 2 = FALSE" in output
    assert "Éléments" in output
    assert "\nNo terminal control" not in output
    assert "\\nNo terminal control" in output
    assert "\x1b" not in output
    assert explain._truth(None) == "UNKNOWN"
    assert explain._cell("É\u202eX") == '"É\\u202eX"'


@pytest.mark.parametrize("name", ["witness.json", "result.json", "replay.sql"])
def test_missing_sidecar_fails_closed(tmp_path: Path, name: str) -> None:
    witness = _copy_evidence(tmp_path, "no_undo")
    (tmp_path / name).unlink()
    assert cli.explain(witness) != 0


@pytest.mark.parametrize("name", ["witness.json", "result.json", "replay.sql"])
def test_tampered_sidecar_fails_closed(tmp_path: Path, name: str) -> None:
    witness = _copy_evidence(tmp_path, "doppelganger")
    (tmp_path / name).write_text("{}", encoding="utf-8")
    assert cli.explain(witness) != 0


def test_sql_unknown_cannot_be_reported_as_passing(tmp_path: Path) -> None:
    witness = _copy_evidence(tmp_path, "doppelganger")
    data = json.loads(witness.read_text())
    result = json.loads((tmp_path / "result.json").read_text())
    data["test_evaluations"][0]["truth"] = None
    result["test_evaluations"][0]["truth"] = None
    witness.write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "result.json").write_text(json.dumps(result), encoding="utf-8")
    assert cli.explain(witness) == 7


def test_stale_result_and_owned_marker_fail_closed(tmp_path: Path) -> None:
    witness = _copy_evidence(tmp_path, "no_undo")
    result = json.loads((tmp_path / "result.json").read_text())
    result["status"] = "INCONCLUSIVE"
    (tmp_path / "result.json").write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(explain.ExplanationError, match="does not match"):
        explain.explain(witness)
    shutil.copy2(ROOT / "examples/no_undo/evidence/result.json", tmp_path / "result.json")
    (tmp_path / ".dataproof-owned.json").write_text(
        json.dumps({"schema_version": 1, "files": {"witness.json": "0" * 64}}),
        encoding="utf-8",
    )
    with pytest.raises(explain.ExplanationError, match="ownership mismatch"):
        explain.explain(witness)


def test_valid_owned_marker_and_backend_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    witness = _copy_evidence(tmp_path, "doppelganger")
    files = {
        name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        for name in ("witness.json", "result.json", "replay.sql")
    }
    (tmp_path / ".dataproof-owned.json").write_text(
        json.dumps({"schema_version": 1, "files": files}), encoding="utf-8"
    )
    assert "Doppelgänger — bounded test blind spot" in explain.explain(witness)
    monkeypatch.setattr("dataproof_verifier.doppel_replay.validate_serialized", lambda *_: 1 / 0)
    assert cli.explain(witness) == 8


def test_cli_entrypoint_plain_terminal(tmp_path: Path) -> None:
    witness = _copy_evidence(tmp_path, "no_undo")
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "NO_COLOR": "1"}
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from dataproof_verifier.cli import main; main()",
            "explain",
            str(witness),
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert process.returncode == 0
    assert "KPI monthly_customers" in process.stdout
    assert "\x1b" not in process.stdout
    assert process.stderr == ""


def test_invalid_schema_status_and_symlink_fail_closed(tmp_path: Path) -> None:
    witness = _copy_evidence(tmp_path, "no_undo")
    data = json.loads(witness.read_text())
    data["schema_version"] = 2
    witness.write_text(json.dumps(data), encoding="utf-8")
    assert cli.explain(witness) == 6
    data["schema_version"] = 1
    data["status"] = "BOUNDED_NO_COUNTEREXAMPLE"
    witness.write_text(json.dumps(data), encoding="utf-8")
    assert cli.explain(witness) == 6
    witness.unlink()
    witness.symlink_to(ROOT / "examples/no_undo/evidence/witness.json")
    assert cli.explain(witness) == 6


def test_inconclusive_unsupported_and_invalid_result_only(tmp_path: Path) -> None:
    for status in ("INCONCLUSIVE", "UNSUPPORTED", "INVALID_INPUT", "INVALID_CANDIDATE"):
        (tmp_path / "witness.json").write_text(
            json.dumps({"schema_version": 1, "status": status}), encoding="utf-8"
        )
        assert cli.explain(tmp_path / "witness.json") == 6


def test_duplicate_json_keys_and_renamed_witness_fail_closed(tmp_path: Path) -> None:
    witness = _copy_evidence(tmp_path, "no_undo")
    witness.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    assert cli.explain(witness) == 6
    witness.rename(tmp_path / "other.json")
    assert cli.explain(tmp_path / "other.json") == 6
