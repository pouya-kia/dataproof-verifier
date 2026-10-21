"""Two distinct complete evaluators for the bounded INNER/LEFT JOIN obligation.

The Python bag evaluator is the search backend. DuckDB executes the accepted
original SQL as a second finite reference. They share schema admission and
world enumeration, so agreement is not a proof of unrestricted correctness.
"""

from __future__ import annotations

import operator
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb

from dataproof_verifier import replay
from dataproof_verifier.join_model import (
    JoinAggregate,
    JoinPredicate,
    JoinQuery,
    JoinScalar,
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
    assert aggregate.value is not None
    values = [_scalar_value(aggregate.value, row, spec) for row in rows]
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


def _scalar_value(
    value: JoinScalar,
    row: tuple[tuple[Any, ...], tuple[Any, ...]],
    spec: JoinSpec,
) -> Any:
    if value.kind == "ref":
        return _value(value.args[0], row, spec)
    if value.kind == "timestamp_trunc":
        unit, ref = value.args
        current = _value(ref, row, spec)
        if current is None:
            return None
        assert isinstance(current, datetime)
        return current.replace(
            day=1 if unit == "MONTH" else current.day,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    if value.kind == "literal":
        return value.args[0]
    if value.kind == "null":
        return None
    if value.kind == "identity_cast":
        return _scalar_value(value.args[0], row, spec)
    if value.kind in {"add", "sub"}:
        left = _scalar_value(value.args[0], row, spec)
        right = _scalar_value(value.args[1], row, spec)
        if left is None or right is None:
            return None
        return left + right if value.kind == "add" else left - right
    if value.kind == "case":
        base, arms, default = value.args
        base_value = _scalar_value(base, row, spec) if base is not None else None
        for condition, result in arms:
            if base is None:
                assert isinstance(condition, JoinPredicate)
                selected = _truth(condition, row, spec) is True
            else:
                assert isinstance(condition, JoinScalar)
                candidate = _scalar_value(condition, row, spec)
                selected = (
                    base_value is not None and candidate is not None and base_value == candidate
                )
            if selected:
                return _scalar_value(result, row, spec)
        return _scalar_value(default, row, spec)
    raise AssertionError("unrecognized admitted scalar")


def _truth(
    predicate: JoinPredicate,
    row: tuple[tuple[Any, ...], tuple[Any, ...]],
    spec: JoinSpec,
) -> bool | None:
    op = predicate.op
    operands = predicate.operands
    if op in {"and", "or"}:
        left, right = operands
        assert isinstance(left, JoinPredicate) and isinstance(right, JoinPredicate)
        a, b = _truth(left, row, spec), _truth(right, row, spec)
        if op == "and":
            return False if a is False or b is False else None if a is None or b is None else True
        return True if a is True or b is True else None if a is None or b is None else False
    if op == "not":
        inner = operands[0]
        assert isinstance(inner, JoinPredicate)
        value = _truth(inner, row, spec)
        return None if value is None else not value
    if op == "is_null":
        ref = operands[0]
        assert isinstance(ref, Ref)
        return _value(ref, row, spec) is None
    left, right = operands
    if isinstance(left, JoinPredicate) or isinstance(right, JoinPredicate):
        raise AssertionError("comparison operands must be scalar")
    left_value = _value(left, row, spec) if isinstance(left, Ref) else left
    right_value = _value(right, row, spec) if isinstance(right, Ref) else right
    if left_value is None or right_value is None:
        return None
    if op == "eq":
        return left_value == right_value
    if op == "neq":
        return left_value != right_value
    ordering = {"lt": operator.lt, "lte": operator.le, "gt": operator.gt, "gte": operator.ge}
    if op in ordering:
        return bool(ordering[op](left_value, right_value))
    raise AssertionError("unrecognized admitted predicate")


def evaluate_python(query: JoinQuery, spec: JoinSpec, world: World) -> tuple[tuple[Any, ...], ...]:
    joined: list[tuple[tuple[Any, ...], tuple[Any, ...]]] = []
    null_right = (None,) * len(spec.tables[1].columns)
    null_left = (None,) * len(spec.tables[0].columns)
    matched_right: set[int] = set()
    for left in world[0]:
        matched = False
        for index, right in enumerate(world[1]):
            pair = (left, right)
            if all(
                _value(left_key, pair, spec) is not None
                and _value(right_key, pair, spec) is not None
                and _value(left_key, pair, spec) == _value(right_key, pair, spec)
                for left_key, right_key in query.on
            ):
                joined.append(pair)
                matched_right.add(index)
                matched = True
        if not matched and query.join_kind in {"left", "full"}:
            joined.append((left, null_right))
    if query.join_kind in {"right", "full"}:
        joined.extend(
            (null_left, right) for index, right in enumerate(world[1]) if index not in matched_right
        )
    if query.where is not None:
        joined = [row for row in joined if _truth(query.where, row, spec) is True]
    if not query.group_by:
        agg = query.projections[0].aggregate
        assert agg is not None
        return ((_aggregate(agg, joined, spec),),)
    groups: dict[tuple[Any, ...], list[tuple[tuple[Any, ...], tuple[Any, ...]]]] = {}
    for row in joined:
        key = tuple(
            _value(ref, row, spec) if isinstance(ref, Ref) else _scalar_value(ref, row, spec)
            for ref in query.group_by
        )
        groups.setdefault(key, []).append(row)
    result: list[tuple[Any, ...]] = []
    for key, members in groups.items():
        output: list[Any] = []
        for projection in query.projections:
            if projection.ref is not None:
                output.append(key[query.group_by.index(projection.ref)])
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
