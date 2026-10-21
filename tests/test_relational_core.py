"""Compatibility and guard tests for the first versioned relational-plan slice."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from dataproof_verifier import join_reference, replay
from dataproof_verifier.join_model import all_join_worlds, parse_join_query, parse_join_spec
from dataproof_verifier.relational_core import (
    PLAN_VERSION,
    Aggregate,
    Filter,
    Join,
    compile_join_query,
    evaluate,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name",
    [
        "fanout.json",
        "left_missing_match.json",
        "projection_cte.json",
        "monthly_timestamp_distinct.json",
    ],
)
def test_plan_matches_original_sql_for_all_tiny_worlds(name: str) -> None:
    raw = json.loads((ROOT / "examples" / "join" / name).read_text(encoding="utf-8"))
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    view_plan = compile_join_query(view, spec)
    metric_plan = compile_join_query(metric, spec)
    assert view_plan.version == metric_plan.version == PLAN_VERSION
    assert isinstance(view_plan.root, Aggregate)
    assert isinstance(view_plan.root.source, (Filter, Join))
    assert view_plan.source_names == tuple(table.table for table in spec.tables)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        worlds = all_join_worlds(spec)
        assert worlds
        for world in worlds:
            actual_view, actual_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(evaluate(view_plan, spec, world)) == Counter(actual_view)
            assert evaluate(metric_plan, spec, world) == ((actual_metric,),)
    finally:
        con.close()


def test_plan_rejects_wrong_version_or_schema() -> None:
    raw = json.loads((ROOT / "examples/join/fanout.json").read_text(encoding="utf-8"))
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    plan = compile_join_query(view, spec)
    world = all_join_worlds(spec)[0]
    with pytest.raises(ValueError, match="version"):
        evaluate(replace(plan, version=PLAN_VERSION + 1), spec, world)
    with pytest.raises(ValueError, match="source schema"):
        evaluate(replace(plan, source_names=("wrong",)), spec, world)
