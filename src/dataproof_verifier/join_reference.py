"""Complete finite joined-query search and original-SQL DuckDB reference.

The shared relational plan evaluates admitted SQL for search. DuckDB executes
the unchanged source SQL over the same legal worlds as a differential check.
Both paths share schema admission and world generation.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import duckdb

from dataproof_verifier import replay
from dataproof_verifier.join_model import JoinQuery, JoinSpec, World, all_join_worlds
from dataproof_verifier.relational_core import compile_join_query, evaluate


@dataclass(frozen=True)
class FiniteResult:
    status: str
    worlds_checked: int
    witness: tuple[World, World] | None
    reason: str | None = None


def evaluate_python(query: JoinQuery, spec: JoinSpec, world: World) -> tuple[tuple[Any, ...], ...]:
    return evaluate(compile_join_query(query, spec), spec, world)


def _key(view: tuple[tuple[Any, ...], ...]) -> frozenset[tuple[tuple[Any, ...], int]]:
    return frozenset(Counter(view).items())


def _search(
    worlds: list[World],
    evaluate_world: Callable[[World], tuple[tuple[tuple[Any, ...], ...], Any]],
    deadline: float,
) -> FiniteResult:
    seen: dict[frozenset[tuple[tuple[Any, ...], int]], tuple[Any, World]] = {}
    checked = 0
    for world in worlds:
        if time.monotonic() >= deadline:
            return FiniteResult("INCONCLUSIVE", checked, None, "TIMEOUT")
        view, metric = evaluate_world(world)
        checked += 1
        if time.monotonic() >= deadline:
            return FiniteResult("INCONCLUSIVE", checked, None, "TIMEOUT")
        key = _key(view)
        previous = seen.get(key)
        if previous is not None and previous[0] != metric:
            return FiniteResult("COUNTEREXAMPLE_FOUND", checked, (previous[1], world))
        seen.setdefault(key, (metric, world))
    return FiniteResult("BOUNDED_NO_COUNTEREXAMPLE", checked, None)


def search_python(
    spec: JoinSpec, view: JoinQuery, metric: JoinQuery, deadline: float
) -> FiniteResult:
    worlds = all_join_worlds(spec)
    view_plan = compile_join_query(view, spec)
    metric_plan = compile_join_query(metric, spec)
    return _search(
        worlds,
        lambda world: (evaluate(view_plan, spec, world), evaluate(metric_plan, spec, world)[0][0]),
        deadline,
    )


def _load(con: duckdb.DuckDBPyConnection, spec: JoinSpec, world: World) -> None:
    for table, rows in zip(spec.tables, world, strict=True):
        con.execute(f'DELETE FROM "{table.table}"')
        for statement in replay._insert_sql(table, rows):
            con.execute(statement)


def evaluate_duckdb(
    con: duckdb.DuckDBPyConnection, spec: JoinSpec, world: World
) -> tuple[tuple[tuple[Any, ...], ...], Any]:
    _load(con, spec, world)
    view = tuple(tuple(row) for row in con.execute(spec.view_sql).fetchall())
    metric_rows = con.execute(spec.metric_sql).fetchall()
    if len(metric_rows) != 1 or len(metric_rows[0]) != 1:
        raise ValueError("metric is not scalar in DuckDB")
    return view, metric_rows[0][0]


def search_duckdb(spec: JoinSpec, deadline: float) -> FiniteResult:
    """Independent SQL-execution reference over the identical declared worlds."""
    worlds = all_join_worlds(spec)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        return _search(worlds, lambda world: evaluate_duckdb(con, spec, world), deadline)
    finally:
        con.close()


def check_pair_duckdb(
    spec: JoinSpec, pair: tuple[World, World]
) -> tuple[bool, tuple[tuple[tuple[Any, ...], ...], ...], tuple[Any, Any]]:
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        left = evaluate_duckdb(con, spec, pair[0])
        right = evaluate_duckdb(con, spec, pair[1])
        views = (left[0], right[0])
        metrics = (left[1], right[1])
        return _key(views[0]) == _key(views[1]) and metrics[0] != metrics[1], views, metrics
    finally:
        con.close()
