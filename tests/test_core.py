from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from datetime import date
from pathlib import Path

import duckdb
import pytest
from conftest import BASE, CASES, case_spec
from hypothesis import given, settings
from hypothesis import strategies as st

from dataproof_verifier.cli import check, replay
from dataproof_verifier.models import SpecError, UnsupportedError, parse_spec
from dataproof_verifier.parser import parse_query
from dataproof_verifier.reference_enumerator import all_worlds, evaluate_for_test, reference_search
from dataproof_verifier.replay import validate, validate_serialized
from dataproof_verifier.solver import SearchResult, search
from dataproof_verifier.status import EXIT_CODES


def _write_spec(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_eight_core_fixtures(case: dict[str, object], tmp_path: Path) -> None:
    raw = case_spec(case, tmp_path / "artifacts")
    path = _write_spec(tmp_path, raw)
    expected = case["expected"]
    assert check(path, None, True) == EXIT_CODES[expected]
    if expected in {"INVALID_INPUT", "UNSUPPORTED"}:
        return
    result = json.loads((tmp_path / "artifacts/result.json").read_text())
    assert result["status"] == expected
    spec = parse_spec(raw)
    view = parse_query(spec.views[0], spec, metric=False)
    metric = parse_query(spec.metric, spec, metric=True)
    reference = reference_search(spec, view, metric)
    assert reference.status == expected
    if expected == "COUNTEREXAMPLE_FOUND":
        assert reference.witness is not None
        assert validate(spec, *reference.witness).valid
        witness_path = tmp_path / "artifacts/witness.json"
        assert validate_serialized(witness_path).valid
        assert replay(witness_path, False) == 0
        assert result["metric_values"][0] != result["metric_values"][1]
    else:
        assert "witness_path" not in result


def test_reference_differential_against_duckdb(base_spec: dict[str, object]) -> None:
    spec = parse_spec(base_spec)
    view = parse_query(spec.views[0], spec, metric=False)
    metric = parse_query(spec.metric, spec, metric=True)
    for world in all_worlds(spec):
        con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
        try:
            con.execute("CREATE TABLE orders (day DATE, customer_id INTEGER, amount INTEGER)")
            for row in world:
                con.execute("INSERT INTO orders VALUES (?, ?, ?)", row)
            actual_view = con.execute(spec.views[0]).fetchall()
            actual_metric = con.execute(spec.metric).fetchall()
            assert Counter(actual_view) == Counter(evaluate_for_test(view, world, spec))
            assert actual_metric == list(evaluate_for_test(metric, world, spec))
        finally:
            con.close()


@settings(max_examples=12, derandomize=True, deadline=None)
@given(st.integers(min_value=1, max_value=3), st.booleans())
def test_solver_reference_agreement(customer_count: int, nullable: bool) -> None:
    raw = deepcopy(BASE)
    raw["table"]["columns"][1]["domain"] = list(range(1, customer_count + 1))
    raw["table"]["columns"][1]["nullable"] = nullable
    if nullable:
        raw["table"]["columns"][1]["domain"].append(None)
    spec = parse_spec(raw)
    view = parse_query(spec.views[0], spec, metric=False)
    metric = parse_query(spec.metric, spec, metric=True)
    found = search(spec, view, metric)
    reference = reference_search(spec, view, metric)
    assert found.status != "INCONCLUSIVE"
    assert (found.worlds is not None) == (reference.witness is not None)
    if found.worlds is not None:
        assert validate(spec, *found.worlds).valid


def test_null_empty_and_duplicate_semantics(base_spec: dict[str, object]) -> None:
    raw = deepcopy(base_spec)
    raw["table"]["columns"][1]["nullable"] = True
    raw["table"]["columns"][1]["domain"].append(None)
    raw["table"]["columns"][2]["nullable"] = True
    raw["table"]["columns"][2]["domain"].append(None)
    spec = parse_spec(raw)
    assert evaluate_for_test(
        parse_query("SELECT SUM(amount) AS x FROM orders", spec, metric=True), (), spec
    ) == ((None,),)
    rows = (
        (date(2026, 1, 1), None, None),
        (date(2026, 1, 1), None, None),
    )
    for sql, expected in (
        ("SELECT COUNT(*) AS x FROM orders", 2),
        ("SELECT COUNT(customer_id) AS x FROM orders", 0),
        ("SELECT COUNT(DISTINCT customer_id) AS x FROM orders", 0),
        ("SELECT SUM(amount) AS x FROM orders", None),
    ):
        query = parse_query(sql, spec, metric=True)
        assert evaluate_for_test(query, rows, spec) == ((expected,),)


def test_nullable_group_and_input_reordering(base_spec: dict[str, object]) -> None:
    raw = deepcopy(base_spec)
    raw["table"]["columns"][0]["nullable"] = True
    raw["table"]["columns"][0]["domain"].append(None)
    spec = parse_spec(raw)
    view = parse_query(spec.views[0], spec, metric=False)
    rows = ((None, 1, 10), (date(2026, 1, 1), 2, 10))
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE orders (day DATE, customer_id INTEGER, amount INTEGER)")
        for row in rows:
            con.execute("INSERT INTO orders VALUES (?, ?, ?)", row)
        assert Counter(con.execute(spec.views[0]).fetchall()) == Counter(
            evaluate_for_test(view, rows, spec)
        )
    finally:
        con.close()
    found = search(spec, view, parse_query(spec.metric, spec, metric=True))
    assert found.worlds is not None
    left, right = found.worlds
    assert validate(spec, left[::-1], right[::-1]).valid


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "SELECT day, ROW_NUMBER() OVER (PARTITION BY day) AS n FROM orders GROUP BY day",
        "SELECT day, random() AS n FROM orders GROUP BY day",
        "SELECT day, COUNT(*) AS n FROM read_csv('secret.csv') GROUP BY day",
        "SELECT day, COUNT(*) AS n FROM orders WHERE customer_id > 1 GROUP BY day",
        "SELECT day, COUNT(*) AS n FROM orders GROUP BY day ORDER BY day",
        "SELECT day, COUNT(*) AS n FROM orders GROUP BY day; DROP TABLE orders",
    ],
)
def test_unsupported_sql_fails_closed(sql: str, base_spec: dict[str, object]) -> None:
    spec = parse_spec(base_spec)
    with pytest.raises(UnsupportedError):
        parse_query(sql, spec, metric=False)


def test_invalid_constraints_and_types(base_spec: dict[str, object]) -> None:
    raw = deepcopy(base_spec)
    raw["table"]["columns"][1]["nullable"] = True
    raw["table"]["primary_key"] = ["customer_id"]
    with pytest.raises(SpecError):
        parse_spec(raw)
    raw = deepcopy(base_spec)
    raw["table"]["foreign_keys"] = []
    with pytest.raises(UnsupportedError):
        parse_spec(raw)
    spec = parse_spec(base_spec)
    assert not validate(spec, ((date(2026, 1, 1), True, 10),), ()).valid
    raw = deepcopy(base_spec)
    raw["table"]["columns"][2]["type"] = "FLOAT"
    with pytest.raises(UnsupportedError):
        parse_spec(raw)
    raw = deepcopy(base_spec)
    raw["table"]["columns"][2]["domain"] = [True]
    with pytest.raises(SpecError):
        parse_spec(raw)


def test_invalid_candidate_and_tampered_replay(
    base_spec: dict[str, object], tmp_path: Path
) -> None:
    spec = parse_spec(base_spec)
    same = ((date(2026, 1, 1), 1, 10),)
    assert not validate(spec, same, same).valid
    raw = deepcopy(base_spec)
    raw["output_dir"] = str(tmp_path / "artifacts")
    path = _write_spec(tmp_path, raw)
    assert check(path, None, False) == 0
    witness = tmp_path / "artifacts/witness.json"
    (tmp_path / "artifacts/replay.sql").write_text("SELECT 'REPLAY_OK';", encoding="utf-8")
    assert not validate_serialized(witness).valid
    assert replay(witness, False) == EXIT_CODES["INVALID_CANDIDATE"]
    witness_data = json.loads(witness.read_text())
    witness_data["worlds"]["D1"][0][1] = True
    witness.write_text(json.dumps(witness_data), encoding="utf-8")
    assert not validate_serialized(witness).valid


@pytest.mark.parametrize("table_name", ["d1_view", "d2_view", "d1_metric", "d2_metric"])
def test_source_table_cannot_collide_with_replay_tables(
    base_spec: dict[str, object], tmp_path: Path, table_name: str
) -> None:
    raw = deepcopy(base_spec)
    raw["table"]["name"] = table_name
    raw["views"] = [raw["views"][0].replace("orders", table_name)]
    raw["metric"] = raw["metric"].replace("orders", table_name)
    raw["output_dir"] = str(tmp_path / "out")
    assert check(_write_spec(tmp_path, raw), None, False) == 0
    assert validate_serialized(tmp_path / "out/witness.json").valid


def test_deliberately_wrong_solver_model_is_rejected(
    base_spec: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = deepcopy(base_spec)
    raw["output_dir"] = str(tmp_path / "out")
    path = _write_spec(tmp_path, raw)
    same = ((date(2026, 1, 1), 1, 10),)
    monkeypatch.setattr(
        "dataproof_verifier.cli.search", lambda *_: SearchResult("CANDIDATE", (same, same), None)
    )
    assert check(path, None, False) == EXIT_CODES["INVALID_CANDIDATE"]
    assert not (tmp_path / "out/witness.json").exists()
    assert json.loads((tmp_path / "out/result.json").read_text())["status"] == "INVALID_CANDIDATE"


def test_yaml_safe_load_and_parser_error(base_spec: dict[str, object], tmp_path: Path) -> None:
    import yaml

    raw = deepcopy(base_spec)
    raw["output_dir"] = str(tmp_path / "yaml-out")
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert check(path, None, False) == 0
    raw["views"] = ["SELECT ) FROM orders"]
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    assert check(path, None, False) == EXIT_CODES["INVALID_INPUT"]
    path.write_text("!!python/object/apply:os.system ['true']", encoding="utf-8")
    assert check(path, None, False) == EXIT_CODES["INVALID_INPUT"]


def test_deterministic_seed(base_spec: dict[str, object], tmp_path: Path) -> None:
    hashes = []
    for name in ("first", "second"):
        raw = deepcopy(base_spec)
        raw["output_dir"] = str(tmp_path / name)
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        assert check(path, None, False) == 0
        result = json.loads((tmp_path / name / "witness.json").read_text())
        hashes.append(result["worlds_sha256"])
    assert hashes[0] == hashes[1]


def test_inconclusive_exit_is_distinct(
    base_spec: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = deepcopy(base_spec)
    raw["output_dir"] = str(tmp_path / "out")
    path = _write_spec(tmp_path, raw)
    monkeypatch.setattr(
        "dataproof_verifier.cli.search", lambda *_: SearchResult("INCONCLUSIVE", None, "timeout")
    )
    assert check(path, None, False) == EXIT_CODES["INCONCLUSIVE"]
    result = json.loads((tmp_path / "out/result.json").read_text())
    assert result["status"] == "INCONCLUSIVE"
    assert result["reason_code"] == "TIMEOUT"
    assert not (tmp_path / "out/witness.json").exists()
    monkeypatch.setattr(
        "dataproof_verifier.cli.search", lambda *_: SearchResult("INCONCLUSIVE", None, "incomplete")
    )
    assert check(path, None, False) == EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    assert json.loads((tmp_path / "out/result.json").read_text())["reason_code"] == "UNKNOWN"
