"""Adversarial semantics, artifacts and replay for Doppelgänger."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from test_doppelganger import example_spec

from dataproof_verifier import doppel_cli
from dataproof_verifier.doppel_model import parse_doppel_spec
from dataproof_verifier.doppel_replay import validate, validate_serialized
from dataproof_verifier.doppel_solver import DoppelSearchResult, search
from dataproof_verifier.models import legal_world


def _file(path: Path, raw: dict[str, object]) -> Path:
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_null_unique_bag_and_primary_key() -> None:
    raw = example_spec()
    raw["table"] = {
        "name": "orders",
        "columns": [{"name": "amount", "type": "INTEGER", "nullable": True, "domain": [None]}],
        "unique": [["amount"]],
    }
    raw["tests"] = [
        {"id": "two_rows", "sql": "SELECT COUNT(*) AS n FROM orders", "op": "=", "value": 2}
    ]
    raw["invariant"] = {
        "id": "all_values_present",
        "sql": "SELECT COUNT(amount) AS n FROM orders",
        "op": "=",
        "value": 2,
        "rationale": "An explicitly supplied completeness expectation.",
    }
    spec = parse_doppel_spec(raw)
    assert legal_world(spec.table, ((None,), (None,)))
    assert search(spec).rows == ((None,), (None,))
    assert validate(spec, ((None,), (None,))).valid
    raw["table"]["primary_key"] = ["amount"]  # type: ignore[index]
    with pytest.raises(ValueError):
        parse_doppel_spec(raw)


def test_duplicate_bag_and_key_rejection() -> None:
    raw = example_spec()
    raw["table"] = {
        "name": "orders",
        "columns": [{"name": "amount", "type": "INTEGER", "nullable": False, "domain": [1]}],
    }
    raw["tests"] = [
        {"id": "two_rows", "sql": "SELECT COUNT(*) AS n FROM orders", "op": "=", "value": 2}
    ]
    raw["invariant"] = {
        "id": "two_distinct",
        "sql": "SELECT COUNT(DISTINCT amount) AS n FROM orders",
        "op": "=",
        "value": 2,
        "rationale": "A user-declared distinctness expectation.",
    }
    spec = parse_doppel_spec(raw)
    assert search(spec).rows == ((1,), (1,))
    assert validate(spec, ((1,), (1,))).valid
    raw["table"]["primary_key"] = ["amount"]  # type: ignore[index]
    assert search(parse_doppel_spec(raw)).status == "INCONSISTENT_TESTS"


def test_invalid_candidate_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _file(tmp_path / "spec.json", example_spec())
    monkeypatch.setattr(
        doppel_cli,
        "search",
        lambda _: DoppelSearchResult("CANDIDATE", ((99,),)),
    )
    output = tmp_path / "out"
    assert doppel_cli.check(source, output, True) == 7
    assert not (output / "witness.json").exists()
    assert json.loads((output / "result.json").read_text())["status"] == "INVALID_CANDIDATE"


def test_artifact_reuse_and_tampering(tmp_path: Path) -> None:
    raw = example_spec()
    source = _file(tmp_path / "spec.json", raw)
    output = tmp_path / "out"
    output.mkdir()
    (output / "user.txt").write_text("untouched", encoding="utf-8")
    assert doppel_cli.check(source, output, False) == 0
    assert validate_serialized(output / "witness.json").valid
    assert json.loads((output / "witness.json").read_text())["rows"] == [[-1]]
    assert doppel_cli.check(source, output, False) == 0
    assert validate_serialized(output / "witness.json").valid
    raw["tests"] = [
        {
            "id": "no_negative_test",
            "sql": "SELECT COUNT(*) AS n FROM orders WHERE amount = -1",
            "op": "=",
            "value": 0,
        }
    ]
    _file(source, raw)
    assert doppel_cli.check(source, output, False) == 3
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()
    assert (output / "user.txt").read_text() == "untouched"
    _file(source, example_spec())
    assert doppel_cli.check(source, output, False) == 0
    witness = json.loads((output / "witness.json").read_text())
    witness["rows"] = [[1]]
    (output / "witness.json").write_text(json.dumps(witness), encoding="utf-8")
    assert not validate_serialized(output / "witness.json").valid
    # Hash-checked ownership refuses to overwrite modified evidence.
    assert doppel_cli.check(source, output, False) == 6
    assert (output / "user.txt").read_text() == "untouched"


def test_serialized_evaluations_and_sql_tampering(tmp_path: Path) -> None:
    source = _file(tmp_path / "spec.json", example_spec())
    output = tmp_path / "out"
    assert doppel_cli.check(source, output, False) == 0
    evidence = tmp_path / "copied"
    evidence.mkdir()
    shutil.copy2(output / "witness.json", evidence / "witness.json")
    shutil.copy2(output / "replay.sql", evidence / "replay.sql")
    witness = json.loads((evidence / "witness.json").read_text())
    witness["test_evaluations"][0]["truth"] = False
    (evidence / "witness.json").write_text(json.dumps(witness), encoding="utf-8")
    assert not validate_serialized(evidence / "witness.json").valid
    shutil.copy2(output / "witness.json", evidence / "witness.json")
    (evidence / "replay.sql").write_text("SELECT 'REPLAY_OK';", encoding="utf-8")
    assert not validate_serialized(evidence / "witness.json").valid


def test_invalid_input_and_unsupported_clear_owned_evidence(tmp_path: Path) -> None:
    raw = example_spec()
    source = _file(tmp_path / "spec.json", raw)
    output = tmp_path / "out"
    assert doppel_cli.check(source, output, False) == 0
    raw["tests"] = []
    _file(source, raw)
    assert doppel_cli.check(source, output, False) == 6
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()
    _file(source, example_spec())
    assert doppel_cli.check(source, output, False) == 0
    raw = example_spec()
    raw["tests"][0]["sql"] = "SELECT RANDOM() FROM orders"  # type: ignore[index]
    _file(source, raw)
    assert doppel_cli.check(source, output, False) == 5
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()


def test_indeterminate_existing_test_is_not_pass(tmp_path: Path) -> None:
    raw = example_spec()
    raw["max_rows"] = 0
    raw["tests"] = [
        {"id": "unknown_sum", "sql": "SELECT SUM(amount) AS n FROM orders", "op": "=", "value": 0}
    ]
    spec = parse_doppel_spec(raw)
    checked = validate(spec, ())
    assert not checked.valid
    assert checked.tests[0].truth is None
    assert search(spec).status == "INCONSISTENT_TESTS"


def test_legal_but_false_solver_candidate_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _file(tmp_path / "spec.json", example_spec())
    monkeypatch.setattr(doppel_cli, "search", lambda _: DoppelSearchResult("CANDIDATE", ((1,),)))
    output = tmp_path / "out"
    assert doppel_cli.check(source, output, False) == 7
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()


@pytest.mark.parametrize(
    "status,code",
    [("INCONCLUSIVE", 4), ("INCONCLUSIVE", 8)],
)
def test_solver_fail_closed_statuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str, code: int
) -> None:
    source = _file(tmp_path / "spec.json", example_spec())
    reason = "TIMEOUT" if code == 4 else "SOLVER_ERROR"
    monkeypatch.setattr(
        doppel_cli,
        "search",
        lambda _: DoppelSearchResult(status, None, reason, reason),
    )
    output = tmp_path / "out"
    assert doppel_cli.check(source, output, False) == code
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()


def test_backend_exception_clears_previous_witness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _file(tmp_path / "spec.json", example_spec())
    output = tmp_path / "out"
    assert doppel_cli.check(source, output, False) == 0

    def fail(_: object) -> None:
        raise RuntimeError("injected failure")

    monkeypatch.setattr(doppel_cli, "search", fail)
    assert doppel_cli.check(source, output, False) == 8
    assert json.loads((output / "result.json").read_text())["reason_code"] == "BACKEND_ERROR"
    assert not (output / "witness.json").exists()
    assert not (output / "replay.sql").exists()
