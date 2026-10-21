"""UTC-naive finite timestamps and period grouping against original DuckDB SQL."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import pytest

from dataproof_verifier import join_cli, join_reference, replay
from dataproof_verifier.join_model import all_join_worlds, parse_join_query, parse_join_spec
from dataproof_verifier.join_replay import validate_serialized
from dataproof_verifier.models import SpecError, UnsupportedError


def _raw(unit: str = "month") -> dict[str, object]:
    return {
        "tables": [
            {
                "name": "orders",
                "max_rows": 2,
                "columns": [
                    {"name": "id", "type": "INTEGER", "domain": [1, 2]},
                    {"name": "cid", "type": "INTEGER", "domain": [1]},
                    {
                        "name": "ts",
                        "type": "TIMESTAMP",
                        "nullable": True,
                        "domain": ["2026-01-31T23:59:59", "2026-02-01T00:00:00"],
                    },
                ],
            },
            {
                "name": "customers",
                "max_rows": 1,
                "columns": [
                    {"name": "cid", "type": "INTEGER", "domain": [1]},
                ],
            },
        ],
        "view": (
            f"SELECT DATE_TRUNC('{unit}', o.ts) AS period, COUNT(*) AS n "
            "FROM orders AS o INNER JOIN customers AS c ON o.cid = c.cid "
            f"GROUP BY DATE_TRUNC('{unit}', o.ts)"
        ),
        "metric": (
            "SELECT COUNT(DISTINCT o.id) AS distinct_orders "
            "FROM orders AS o INNER JOIN customers AS c ON o.cid = c.cid"
        ),
    }


@pytest.mark.parametrize("unit", ["day", "month"])
@pytest.mark.parametrize("aggregate", ["COUNT(*)", "COUNT(DISTINCT o.id)"])
def test_period_groups_all_legal_worlds_match_duckdb(unit: str, aggregate: str) -> None:
    raw = _raw(unit)
    raw["view"] = str(raw["view"]).replace("COUNT(*)", aggregate)
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        worlds = all_join_worlds(spec)
        assert len(worlds) == 56
        for world in worlds:
            py_view = join_reference.evaluate_python(view, spec, world)
            py_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(py_view) == Counter(db_view)
            assert py_metric == db_metric
    finally:
        con.close()


def test_timestamp_column_comparison_where_and_two_group_columns() -> None:
    raw = _raw()
    raw["tables"][1]["columns"].append(  # type: ignore[index]
        {"name": "cutoff", "type": "TIMESTAMP", "domain": ["2026-02-01T00:00:00"]}
    )
    raw["view"] = (
        "SELECT DATE_TRUNC('month', o.ts) AS period, c.cid AS cid, COUNT(*) AS n "
        "FROM orders AS o LEFT JOIN customers AS c ON o.cid = c.cid "
        "WHERE o.ts >= c.cutoff OR o.ts IS NULL "
        "GROUP BY DATE_TRUNC('month', o.ts), c.cid"
    )
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            py_view = join_reference.evaluate_python(view, spec, world)
            join_reference._load(con, spec, world)
            db_view = tuple(tuple(row) for row in con.execute(spec.view_sql).fetchall())
            assert Counter(py_view) == Counter(db_view)
    finally:
        con.close()


def test_period_positive_witness_serialization_and_replay(tmp_path: Path) -> None:
    source = tmp_path / "period.json"
    source.write_text(json.dumps(_raw()), encoding="utf-8")
    output = tmp_path / "out"
    assert join_cli.preflight(source, True) == 0
    assert join_cli.check(source, output, True) == 0
    assert validate_serialized(output / "witness.json") == (True, "REPLAY_OK")
    witness = json.loads((output / "witness.json").read_text(encoding="utf-8"))
    assert any(
        "2026-" in str(row) for world in witness["worlds"].values() for bag in world for row in bag
    )


def test_empty_timestamp_world_is_complete_bounded_negative() -> None:
    raw = _raw()
    for table in raw["tables"]:  # type: ignore[union-attr]
        table["max_rows"] = 0  # type: ignore[index]
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    deadline = time.monotonic() + 10
    assert join_reference.search_python(spec, view, metric, deadline).status == (
        "BOUNDED_NO_COUNTEREXAMPLE"
    )
    assert join_reference.search_duckdb(spec, deadline).status == "BOUNDED_NO_COUNTEREXAMPLE"


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-01 00:00:00",
        "2026-02-01T00:00:00+00:00",
        "2026-02-01T00:00:00Z",
        "2026-02-30T00:00:00",
        "2026-02-01T00:00:00.123456",
    ],
)
def test_ambiguous_or_out_of_policy_timestamp_rejected(value: str) -> None:
    raw = _raw()
    raw["tables"][0]["columns"][2]["domain"][0] = value  # type: ignore[index]
    with pytest.raises(SpecError):
        parse_join_spec(raw)


@pytest.mark.parametrize(
    "replacement",
    [
        "DATE_TRUNC('week', o.ts)",
        "DATE_TRUNC('month', CAST(o.cid AS TIMESTAMP))",
        "ROW_NUMBER() OVER (PARTITION BY o.cid ORDER BY o.ts)",
    ],
)
def test_unmodeled_period_or_window_rejected(replacement: str) -> None:
    raw = _raw()
    raw["view"] = str(raw["view"]).replace("DATE_TRUNC('month', o.ts)", replacement)
    spec = parse_join_spec(raw)
    with pytest.raises(UnsupportedError):
        parse_join_query(spec.view_sql, spec, metric=False)
