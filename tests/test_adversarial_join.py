"""Generated legal two-table worlds versus fresh direct DuckDB SQL execution."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import duckdb
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from dataproof_verifier import relational_core
from dataproof_verifier.join_model import JoinSpec, World, legal_join_world, parse_join_spec
from dataproof_verifier.relational_core import Scan, evaluate
from dataproof_verifier.relational_pipeline import admit_query

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = 60 if os.environ.get("DATAPROOF_STRESS") == "1" else 12
CASES = (
    "fanout",
    "left_missing_match",
    "right_missing_match",
    "string_distinct",
    "projection_cte",
    "aggregate_cte_fanout",
    "monthly_timestamp_distinct",
    "full_nullable_composite",
    "case_arithmetic",
)


def _raw(name: str) -> dict[str, object]:
    if name == "full_nullable_composite":
        return {
            "tables": [
                {
                    "name": "orders",
                    "max_rows": 1,
                    "columns": [
                        {"name": "id", "type": "INTEGER", "domain": [1, 2]},
                        {"name": "k", "type": "INTEGER", "nullable": True, "domain": [7, None]},
                    ],
                },
                {
                    "name": "customers",
                    "max_rows": 1,
                    "columns": [
                        {"name": "id", "type": "INTEGER", "domain": [3]},
                        {"name": "k", "type": "INTEGER", "nullable": True, "domain": [7, None]},
                    ],
                },
            ],
            "view": (
                "SELECT o.k AS left_k, c.k AS right_k, COUNT(*) AS n, COUNT(o.id) AS matched "
                "FROM orders AS o FULL JOIN customers AS c "
                "ON o.k = c.k AND o.id = c.id GROUP BY o.k, c.k"
            ),
            "metric": (
                "SELECT COUNT(c.id) AS n FROM orders AS o FULL JOIN customers AS c "
                "ON o.k = c.k AND o.id = c.id"
            ),
        }
    if name == "case_arithmetic":
        return {
            "tables": [
                {
                    "name": "orders",
                    "max_rows": 1,
                    "columns": [
                        {"name": "k", "type": "INTEGER", "domain": [1]},
                        {"name": "x", "type": "INTEGER", "nullable": True, "domain": [-1, 2]},
                    ],
                },
                {
                    "name": "customers",
                    "max_rows": 1,
                    "columns": [{"name": "k", "type": "INTEGER", "domain": [1]}],
                },
            ],
            "view": (
                "SELECT o.k AS k, SUM(CASE WHEN o.x > 0 THEN o.x + 1 ELSE 0 END) AS n "
                "FROM orders AS o INNER JOIN customers AS c ON o.k = c.k GROUP BY o.k"
            ),
            "metric": (
                "SELECT SUM(CASE o.x WHEN -1 THEN CAST(o.x AS INTEGER) ELSE o.x - 1 END) AS n "
                "FROM orders AS o INNER JOIN customers AS c ON o.k = c.k"
            ),
        }
    return json.loads((ROOT / "examples/join" / f"{name}.json").read_text())


def _direct_duckdb(spec: JoinSpec, world: World, sql: str) -> Counter[tuple[object, ...]]:
    """Use parameterized inserts, not DataProof replay/create/evaluate helpers."""
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        for table, rows in zip(spec.tables, world, strict=True):
            columns = ", ".join(
                f'"{column.name}" '
                + {
                    "INTEGER": "INTEGER",
                    "DATE": "DATE",
                    "STRING": "VARCHAR",
                    "TIMESTAMP": "TIMESTAMP",
                }[column.type]
                for column in table.columns
            )
            con.execute(f'CREATE TABLE "{table.table}" ({columns})')
            if rows:
                placeholders = ", ".join("?" for _ in table.columns)
                con.executemany(f'INSERT INTO "{table.table}" VALUES ({placeholders})', rows)
        return Counter(tuple(row) for row in con.execute(sql).fetchall())
    finally:
        con.close()


def _assert_both_queries(spec: JoinSpec, world: World) -> None:
    for sql, metric in ((spec.view_sql, False), (spec.metric_sql, True)):
        plan = admit_query(sql, spec, metric=metric)
        assert Counter(evaluate(plan, spec, world)) == _direct_duckdb(spec, world, sql)


@pytest.mark.parametrize("name", CASES)
@settings(max_examples=EXAMPLES, derandomize=True, deadline=None)
@given(data=st.data())
def test_generated_join_worlds_match_original_sql(name: str, data: st.DataObject) -> None:
    spec = parse_join_spec(_raw(name))
    sources: list[tuple[tuple[object, ...], ...]] = []
    for table in spec.tables:
        row_strategy = st.tuples(*(st.sampled_from(column.domain) for column in table.columns))
        rows = data.draw(st.lists(row_strategy, max_size=table.max_rows), label=table.table)
        sources.append(tuple(rows))
    world: World = (sources[0], sources[1])
    assume(legal_join_world(spec, world))
    _assert_both_queries(spec, world)
    reversed_world: World = (world[0][::-1], world[1][::-1])
    _assert_both_queries(spec, reversed_world)
    assert _direct_duckdb(spec, world, spec.view_sql) == _direct_duckdb(
        spec, reversed_world, spec.view_sql
    )


def test_null_keys_never_match_and_outer_rows_remain() -> None:
    raw = _raw("full_nullable_composite")
    raw["view"] = (
        "SELECT o.k AS left_k, c.k AS right_k, COUNT(*) AS n, COUNT(o.id) AS left_count "
        "FROM orders AS o FULL JOIN customers AS c ON o.k = c.k "
        "GROUP BY o.k, c.k"
    )
    raw["metric"] = "SELECT COUNT(c.id) AS n FROM orders AS o FULL JOIN customers AS c ON o.k = c.k"
    spec = parse_join_spec(raw)
    world: World = (((1, None),), ((3, None),))
    assert legal_join_world(spec, world)
    _assert_both_queries(spec, world)
    assert _direct_duckdb(spec, world, spec.view_sql) == Counter({(None, None, 2, 1): 1})


def test_null_safe_join_mutation_changes_declared_equality_semantics() -> None:
    raw = _raw("full_nullable_composite")
    raw["view"] = str(raw["view"]).replace(" AND o.id = c.id", "")
    raw["metric"] = str(raw["metric"]).replace(" AND o.id = c.id", "")
    spec = parse_join_spec(raw)
    world: World = (((1, None),), ((3, None),))
    original = _direct_duckdb(spec, world, spec.view_sql)
    mutant_sql = spec.view_sql.replace("o.k = c.k", "o.k IS NOT DISTINCT FROM c.k")
    assert original != _direct_duckdb(spec, world, mutant_sql)
    _assert_both_queries(spec, world)


def test_projected_alias_rename_preserves_bag() -> None:
    original = parse_join_spec(_raw("fanout"))
    raw = _raw("fanout")
    raw["view"] = str(raw["view"]).replace("o.cid AS cid", "o.cid AS grouped_customer")
    renamed = parse_join_spec(raw)
    world: World = (((1, 7), (2, 7)), ((7,), (7,)))
    assert legal_join_world(original, world)
    old = _direct_duckdb(original, world, original.view_sql)
    new = _direct_duckdb(renamed, world, renamed.view_sql)
    assert old == new
    _assert_both_queries(original, world)
    _assert_both_queries(renamed, world)


def test_differential_detects_scan_deduplication_mutant(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = parse_join_spec(_raw("fanout"))
    world: World = (((1, 7), (1, 7)), ((7,),))
    plan = admit_query(spec.view_sql, spec, metric=False)
    expected = _direct_duckdb(spec, world, spec.view_sql)
    assert Counter(evaluate(plan, spec, world)) == expected
    original = relational_core._eval

    def mutant(node: object, source_spec: JoinSpec, source_world: World) -> object:
        rows = original(node, source_spec, source_world)  # type: ignore[arg-type]
        if isinstance(node, Scan):
            return tuple(dict.fromkeys(rows))  # deliberately drops a bag duplicate
        return rows

    monkeypatch.setattr(relational_core, "_eval", mutant)
    with pytest.raises(AssertionError):
        assert Counter(evaluate(plan, spec, world)) == expected
