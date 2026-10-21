"""Two distinct complete evaluators for the bounded INNER JOIN obligation.

The Python bag evaluator is the search backend. DuckDB executes the accepted
original SQL as a second finite reference. They share schema admission and
world enumeration, so agreement is not a proof of unrestricted correctness.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import duckdb

from dataproof_verifier import replay
from dataproof_verifier.join_model import (
    JoinAggregate,
    JoinQuery,
    JoinSpec,
    Ref,
    World,
    all_join_worlds,
)


@dataclass(frozen=True)
class FiniteResult:
    status: str
    worlds_checked: int
    witness: tuple[World, World] | None
    reason: str | None = None


def _value(ref: Ref, joined: tuple[tuple[Any, ...], tuple[Any, ...]], spec: JoinSpec) -> Any:
    return joined[ref.table][spec.tables[ref.table].names.index(ref.column)]


def _aggregate(
    aggregate: JoinAggregate,
    rows: list[tuple[tuple[Any, ...], tuple[Any, ...]]],
    spec: JoinSpec,
) -> int | None:
    if aggregate.kind == "count_star":
        return len(rows)
    assert aggregate.ref is not None
    values = [_value(aggregate.ref, row, spec) for row in rows]
    nonnull = [value for value in values if value is not None]
    if aggregate.kind == "count":
        return len(nonnull)
    if aggregate.kind == "count_distinct":
        return len(set(nonnull))
    if aggregate.kind == "sum":
        return sum(nonnull) if nonnull else None
    if aggregate.kind == "min":
        return min(nonnull) if nonnull else None
    if aggregate.kind == "max":
        return max(nonnull) if nonnull else None
    raise AssertionError("unrecognized admitted aggregate")


def evaluate_python(query: JoinQuery, spec: JoinSpec, world: World) -> tuple[tuple[Any, ...], ...]:
    joined = [
        (left, right)
        for left in world[0]
        for right in world[1]
        if _value(query.on[0], (left, right), spec) is not None
        and _value(query.on[0], (left, right), spec) == _value(query.on[1], (left, right), spec)
    ]
    if query.group_by is None:
        agg = query.projections[0].aggregate
        assert agg is not None
        return ((_aggregate(agg, joined, spec),),)
    groups: dict[Any, list[tuple[tuple[Any, ...], tuple[Any, ...]]]] = {}
    for row in joined:
        groups.setdefault(_value(query.group_by, row, spec), []).append(row)
    result: list[tuple[Any, ...]] = []
    for key, members in groups.items():
        output: list[Any] = []
        for projection in query.projections:
            if projection.ref is not None:
                output.append(key)
            else:
                assert projection.aggregate is not None
                output.append(_aggregate(projection.aggregate, members, spec))
        result.append(tuple(output))
    return tuple(result)


def _key(view: tuple[tuple[Any, ...], ...]) -> frozenset[tuple[tuple[Any, ...], int]]:
    return frozenset(Counter(view).items())


def _search(
    worlds: list[World],
    evaluate: Callable[[World], tuple[tuple[tuple[Any, ...], ...], Any]],
    deadline: float,
) -> FiniteResult:
    seen: dict[frozenset[tuple[tuple[Any, ...], int]], tuple[Any, World]] = {}
    checked = 0
    for world in worlds:
        if time.monotonic() >= deadline:
            return FiniteResult("INCONCLUSIVE", checked, None, "TIMEOUT")
        view, metric = evaluate(world)
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
    return _search(
        worlds,
        lambda world: (
            evaluate_python(view, spec, world),
            evaluate_python(metric, spec, world)[0][0],
        ),
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
