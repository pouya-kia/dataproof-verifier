"""Finite original-SQL checks for one materialized aggregate pipeline."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import pytest

from dataproof_verifier import join_cli, join_reference, replay
from dataproof_verifier.join_model import all_join_worlds, parse_join_spec
from dataproof_verifier.models import UnsupportedError
from dataproof_verifier.relational_core import Aggregate, Materialize, evaluate
from dataproof_verifier.relational_pipeline import admit_query

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "examples/join/aggregate_cte_fanout.json"


def _raw() -> dict[str, object]:
    return json.loads(CASE.read_text(encoding="utf-8"))


def test_aggregate_cte_complete_world_differential() -> None:
    spec = parse_join_spec(_raw())
    view = admit_query(spec.view_sql, spec, metric=False)
    metric = admit_query(spec.metric_sql, spec, metric=True)
    assert isinstance(view.root, Aggregate)
    assert isinstance(view.root.source, Materialize)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        worlds = all_join_worlds(spec)
        assert len(worlds) == 18
        for world in worlds:
            db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(evaluate(view, spec, world)) == Counter(db_view)
            assert evaluate(metric, spec, world) == ((db_metric,),)
        assert evaluate(view, spec, worlds[0]) == ()
        assert evaluate(metric, spec, worlds[0]) == ((None,),)
    finally:
        con.close()
    deadline = time.monotonic() + 10
    python = join_reference.search_python(spec, view, metric, deadline)
    duckdb = join_reference.search_duckdb(spec, deadline)
    assert python.status == duckdb.status == "COUNTEREXAMPLE_FOUND"
    assert python.witness is not None
    assert join_reference.check_pair_duckdb(spec, python.witness)[0]


def test_aggregate_cte_cli_replay_and_explain(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = _raw()
    source = tmp_path / "case.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    output = tmp_path / "out"
    assert join_cli.preflight(source, True) == 0
    assert join_cli.check(source, output, True) == 0
    assert join_cli.replay_witness(output / "witness.json", True) == 0
    assert join_cli.explain_witness(output / "witness.json") == 0
    assert "aggregate CTE/derived JOIN" in capsys.readouterr().out
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["plan_version"] == 1
    assert result["worlds_examined"] <= 18
    assert result["reference_worlds_examined"] <= 18


def test_complete_bounded_negative_pipeline(tmp_path: Path) -> None:
    raw = _raw()
    assert isinstance(raw["metric"], str)
    raw["metric"] = raw["metric"].replace("MAX(x.n) AS peak", "SUM(x.n) AS total")
    source = tmp_path / "negative.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    output = tmp_path / "out"
    assert join_cli.check(source, output, True) == 3
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "BOUNDED_NO_COUNTEREXAMPLE"
    assert result["bounded_exhaustion_complete"] is True
    assert result["worlds_examined"] == result["reference_worlds_examined"] == 18
    assert not (output / "witness.json").exists()


def test_derived_aggregate_source_uses_same_plan() -> None:
    raw = _raw()
    view_sql = raw["view"]
    assert isinstance(view_sql, str)
    inner = view_sql.removeprefix("WITH x AS (").split(") SELECT x.cid", 1)[0]
    raw["view"] = f"SELECT x.cid AS cid, SUM(x.n) AS total FROM ({inner}) AS x GROUP BY x.cid"
    spec = parse_join_spec(raw)
    view = admit_query(spec.view_sql, spec, metric=False)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            actual, _ = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(evaluate(view, spec, world)) == Counter(actual)
    finally:
        con.close()


def test_materialized_null_count_distinct_and_empty_scalar() -> None:
    raw = _raw()
    tables = raw["tables"]
    assert isinstance(tables, list)
    orders = tables[0]
    assert isinstance(orders, dict)
    columns = orders["columns"]
    assert isinstance(columns, list)
    identifier = columns[0]
    assert isinstance(identifier, dict)
    identifier["nullable"] = True
    raw["metric"] = str(raw["metric"]).replace(
        "MAX(x.n) AS peak", "COUNT(DISTINCT x.oid) AS distinct_orders"
    )
    spec = parse_join_spec(raw)
    view = admit_query(spec.view_sql, spec, metric=False)
    metric = admit_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in (
            ((), ()),
            (((None, 7), (None, 7)), ((7,),)),
            (((1, 7), (None, 7)), ((7,),)),
        ):
            db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(evaluate(view, spec, world)) == Counter(db_view)
            assert evaluate(metric, spec, world) == ((db_metric,),)
    finally:
        con.close()


def test_inner_where_and_outer_grouping_preserve_original_sql() -> None:
    raw = _raw()
    raw["view"] = str(raw["view"]).replace(
        "GROUP BY o.cid, o.id)", "WHERE o.id IS NOT NULL GROUP BY o.cid, o.id)"
    )
    raw["metric"] = str(raw["metric"]).replace(
        "GROUP BY o.cid, o.id)", "WHERE o.id IS NOT NULL GROUP BY o.cid, o.id)"
    )
    spec = parse_join_spec(raw)
    view = admit_query(spec.view_sql, spec, metric=False)
    metric = admit_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(evaluate(view, spec, world)) == Counter(db_view)
            assert evaluate(metric, spec, world) == ((db_metric,),)
    finally:
        con.close()


@pytest.mark.parametrize(
    "replacement",
    [
        "WITH RECURSIVE x AS",
        "WITH y AS",
        "WITH x(a, b, c) AS",
    ],
)
def test_unsupported_cte_declarations_fail_closed(replacement: str) -> None:
    raw = _raw()
    sql = raw["view"]
    assert isinstance(sql, str)
    raw["view"] = sql.replace("WITH x AS", replacement, 1)
    spec = parse_join_spec(raw)
    with pytest.raises(UnsupportedError):
        admit_query(spec.view_sql, spec, metric=False)


@pytest.mark.parametrize(
    "suffix",
    [" HAVING COUNT(*) > 0", " ORDER BY x.cid", " LIMIT 1", "; DELETE FROM orders"],
)
def test_unsupported_outer_clauses_fail_closed(suffix: str) -> None:
    raw = _raw()
    sql = raw["view"]
    assert isinstance(sql, str)
    raw["view"] = sql + suffix
    spec = parse_join_spec(raw)
    with pytest.raises(UnsupportedError):
        admit_query(spec.view_sql, spec, metric=False)
