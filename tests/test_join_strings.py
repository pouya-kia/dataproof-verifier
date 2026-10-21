"""Finite ASCII STRING semantics in the separate bounded join workflow."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import pytest

from dataproof_verifier import join_cli, join_reference, replay
from dataproof_verifier.join_model import (
    all_join_worlds,
    parse_join_query,
    parse_join_spec,
)
from dataproof_verifier.join_replay import validate_serialized
from dataproof_verifier.models import UnsupportedError, parse_spec


def _spec() -> dict[str, object]:
    return {
        "tables": [
            {
                "name": "orders",
                "max_rows": 2,
                "columns": [
                    {"name": "k", "type": "INTEGER", "domain": [1]},
                    {"name": "label", "type": "STRING", "nullable": True, "domain": ["a", "b"]},
                ],
            },
            {
                "name": "customers",
                "max_rows": 1,
                "columns": [
                    {"name": "k", "type": "INTEGER", "domain": [1]},
                    {"name": "name", "type": "STRING", "domain": ["O'Brien"]},
                ],
            },
        ],
        "view": (
            "SELECT o.k AS k, COUNT(*) AS n FROM orders AS o "
            "INNER JOIN customers AS c ON o.k = c.k GROUP BY o.k"
        ),
        "metric": (
            "SELECT COUNT(DISTINCT o.label) AS n FROM orders AS o "
            "INNER JOIN customers AS c ON o.k = c.k"
        ),
    }


def _source(tmp_path: Path, raw: dict[str, object]) -> Path:
    source = tmp_path / "spec.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    return source


def test_join_string_witness_and_independent_replay(tmp_path: Path) -> None:
    source = _source(tmp_path, _spec())
    out = tmp_path / "out"
    assert join_cli.preflight(source, True) == 0
    assert join_cli.check(source, out, True) == 0
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "COUNTEREXAMPLE_FOUND"
    assert result["fragment_limits"]["string_collation"] == "ASCII_BINARY_CASE_SENSITIVE"
    assert validate_serialized(out / "witness.json") == (True, "REPLAY_OK")
    assert "O''Brien" in (out / "replay.sql").read_text(encoding="utf-8")
    witness = out / "witness.json"
    evidence = json.loads(witness.read_text(encoding="utf-8"))
    evidence["worlds"]["D1"][0][0][1] = "tampered"
    witness.write_text(json.dumps(evidence), encoding="utf-8")
    assert validate_serialized(witness)[0] is False


def test_case_aggregate_witness_replays(tmp_path: Path) -> None:
    raw = _spec()
    raw["metric"] = (
        "SELECT SUM(CASE WHEN o.label = 'a' THEN 1 ELSE 2 END) AS n "
        "FROM orders AS o INNER JOIN customers AS c ON o.k = c.k"
    )
    source = _source(tmp_path, raw)
    out = tmp_path / "case-out"
    assert join_cli.check(source, out, True) == 0
    assert validate_serialized(out / "witness.json") == (True, "REPLAY_OK")


def test_binary_string_predicates_null_and_grouping_agree_with_duckdb() -> None:
    raw = _spec()
    raw["view"] = (
        "SELECT o.label AS label, COUNT(*) AS n FROM orders AS o "
        "LEFT JOIN customers AS c ON o.k = c.k "
        "WHERE o.label = 'a' OR o.label IS NULL GROUP BY o.label"
    )
    raw["metric"] = (
        "SELECT COUNT(DISTINCT o.label) AS n FROM orders AS o "
        "LEFT JOIN customers AS c ON o.k = c.k WHERE o.label != 'b'"
    )
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            expected_view = join_reference.evaluate_python(view, spec, world)
            expected_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            actual_view, actual_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(expected_view) == Counter(actual_view)
            assert expected_metric == actual_metric
    finally:
        con.close()


def test_string_key_and_bounded_negative_agree() -> None:
    raw = _spec()
    raw["tables"][0]["max_rows"] = 1  # type: ignore[index]
    raw["tables"][0]["columns"][0] = {  # type: ignore[index]
        "name": "k",
        "type": "STRING",
        "domain": ["x", "y"],
    }
    raw["tables"][1]["columns"][0] = {  # type: ignore[index]
        "name": "k",
        "type": "STRING",
        "domain": ["x", "y"],
    }
    raw["metric"] = str(raw["metric"]).replace("COUNT(DISTINCT o.label)", "COUNT(*)")
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    deadline = time.monotonic() + 10
    python = join_reference.search_python(spec, view, metric, deadline)
    duckdb = join_reference.search_duckdb(spec, deadline)
    assert python.status == duckdb.status == "BOUNDED_NO_COUNTEREXAMPLE"
    assert python.worlds_checked == duckdb.worlds_checked == len(all_join_worlds(spec))


def test_ascii_binary_case_sensitive_join_and_duplicates() -> None:
    raw = _spec()
    raw["tables"][0]["columns"][0] = {  # type: ignore[index]
        "name": "k",
        "type": "STRING",
        "domain": ["A", "a"],
    }
    raw["tables"][1]["columns"][0] = {  # type: ignore[index]
        "name": "k",
        "type": "STRING",
        "domain": ["A", "a"],
    }
    raw["tables"][1]["columns"][1] = {  # type: ignore[index]
        "name": "name",
        "type": "STRING",
        "domain": ["x"],
    }
    raw["tables"][0]["columns"][1] = {  # type: ignore[index]
        "name": "label",
        "type": "STRING",
        "domain": ["x"],
    }
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            expected_view = join_reference.evaluate_python(view, spec, world)
            expected_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            actual_view, actual_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(expected_view) == Counter(actual_view)
            assert expected_metric == actual_metric
    finally:
        con.close()


def test_searched_and_simple_case_integer_arithmetic_cast_all_worlds() -> None:
    raw = _spec()
    raw["tables"][0]["max_rows"] = 1  # type: ignore[index]
    raw["tables"][0]["columns"] = [  # type: ignore[index]
        {"name": "k", "type": "INTEGER", "domain": [1]},
        {"name": "x", "type": "INTEGER", "nullable": True, "domain": [-1, 2]},
    ]
    raw["tables"][1]["columns"] = [  # type: ignore[index]
        {"name": "k", "type": "INTEGER", "domain": [1]}
    ]
    raw["view"] = (
        "SELECT o.k AS k, SUM(CASE WHEN o.x > 0 THEN o.x + 1 ELSE 0 END) AS n "
        "FROM orders AS o INNER JOIN customers AS c ON o.k = c.k GROUP BY o.k"
    )
    raw["metric"] = (
        "SELECT SUM(CASE o.x WHEN -1 THEN CAST(o.x AS INTEGER) ELSE o.x - 1 END) AS n "
        "FROM orders AS o INNER JOIN customers AS c ON o.k = c.k"
    )
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            expected_view = join_reference.evaluate_python(view, spec, world)
            expected_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            actual_view, actual_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(expected_view) == Counter(actual_view)
            assert expected_metric == actual_metric
    finally:
        con.close()


def test_simple_string_case_and_implicit_null_all_worlds() -> None:
    raw = _spec()
    raw["view"] = (
        "SELECT o.label AS label, COUNT(CASE o.label "
        "WHEN 'a' THEN o.label WHEN 'b' THEN o.label END) AS n "
        "FROM orders AS o LEFT JOIN customers AS c ON o.k = c.k GROUP BY o.label"
    )
    raw["metric"] = (
        "SELECT SUM(CASE o.label WHEN 'a' THEN 1 WHEN 'b' THEN 2 END) AS n "
        "FROM orders AS o LEFT JOIN customers AS c ON o.k = c.k"
    )
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            expected_view = join_reference.evaluate_python(view, spec, world)
            expected_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            actual_view, actual_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(expected_view) == Counter(actual_view)
            assert expected_metric == actual_metric
    finally:
        con.close()


@pytest.mark.parametrize(
    "expression",
    [
        "o.k / 2",
        "CAST(o.k AS VARCHAR)",
        "CAST(o.label AS VARCHAR(2))",
        "TRY_CAST(o.k AS INTEGER)",
        "CASE WHEN o.k = 1 THEN o.k ELSE 'a' END",
        "o.k * 2",
    ],
)
def test_unsupported_expression_rejected(expression: str) -> None:
    spec = parse_join_spec(_spec())
    sql = f"SELECT SUM({expression}) AS n FROM orders AS o INNER JOIN customers AS c ON o.k = c.k"
    with pytest.raises(UnsupportedError):
        parse_join_query(sql, spec, metric=True)


def test_arithmetic_overflow_bound_rejected() -> None:
    raw = _spec()
    raw["tables"][0]["columns"][0]["domain"] = [2**31 - 1]  # type: ignore[index]
    raw["tables"][1]["columns"][0]["domain"] = [2**31 - 1]  # type: ignore[index]
    spec = parse_join_spec(raw)
    sql = "SELECT SUM(o.k + 1) AS n FROM orders AS o INNER JOIN customers AS c ON o.k = c.k"
    with pytest.raises(UnsupportedError, match="overflow"):
        parse_join_query(sql, spec, metric=True)


def test_string_is_not_silently_added_to_one_table_z3() -> None:
    table = dict(_spec()["tables"][0])  # type: ignore[index]
    table.pop("max_rows")
    raw = {
        "table": table,
        "views": ["SELECT label, COUNT(*) AS n FROM orders GROUP BY label"],
        "metric": "SELECT COUNT(*) AS n FROM orders",
        "max_rows": 1,
    }
    with pytest.raises(UnsupportedError, match="unsupported column type"):
        parse_spec(raw)


@pytest.mark.parametrize("bad", ["", "é", "line\nbreak", "x" * 33])
def test_out_of_fragment_string_domains_rejected(bad: str) -> None:
    raw = _spec()
    raw["tables"][0]["columns"][1]["domain"] = [bad]  # type: ignore[index]
    with pytest.raises(ValueError):
        parse_join_spec(raw)


@pytest.mark.parametrize(
    "literal",
    ["'é'", "''", "'a' COLLATE NOCASE", "1", "'a' || 'b'"],
)
def test_unsupported_string_semantics_fail_closed(literal: str) -> None:
    spec = parse_join_spec(_spec())
    sql = (
        "SELECT COUNT(*) AS n FROM orders AS o INNER JOIN customers AS c "
        f"ON o.k = c.k WHERE o.label = {literal}"
    )
    with pytest.raises(UnsupportedError):
        parse_join_query(sql, spec, metric=True)
