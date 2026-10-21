"""Separate exhaustive tiny-domain reference, implemented without SMT."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations_with_replacement, product

from dataproof_verifier.ir import Aggregate, Query
from dataproof_verifier.models import Row, Spec, Value, legal_world


@dataclass(frozen=True)
class ReferenceResult:
    status: str
    worlds_checked: int
    witness: tuple[tuple[Row, ...], tuple[Row, ...]] | None


def _agg(agg: Aggregate, rows: tuple[Row, ...], spec: Spec) -> int | None:
    if agg.kind == "count_star":
        return len(rows)
    assert agg.column is not None
    index = spec.names.index(agg.column)
    values = [row[index] for row in rows if row[index] is not None]
    if agg.kind == "count":
        return len(values)
    if agg.kind == "count_distinct":
        return len(set(values))
    if agg.kind == "sum":
        return sum(values) if values else None  # type: ignore[arg-type]
    if agg.kind == "min":
        integers = [value for value in values if type(value) is int]
        assert len(integers) == len(values)
        return min(integers) if integers else None
    if agg.kind == "max":
        integers = [value for value in values if type(value) is int]
        assert len(integers) == len(values)
        return max(integers) if integers else None
    raise AssertionError(f"unexpected IR aggregate: {agg.kind}")


def _evaluate(query: Query, rows: tuple[Row, ...], spec: Spec) -> tuple[tuple[Value, ...], ...]:
    if query.predicate is not None:
        predicate = query.predicate
        index = spec.names.index(predicate.column)
        if predicate.kind == "eq":
            rows = tuple(
                row for row in rows if row[index] is not None and row[index] == predicate.value
            )
        elif predicate.kind == "is_null":
            rows = tuple(row for row in rows if row[index] is None)
        elif predicate.kind == "is_not_null":
            rows = tuple(row for row in rows if row[index] is not None)
        else:
            raise AssertionError(f"unexpected IR predicate: {predicate.kind}")
    if query.group_by is None:
        assert len(query.projections) == 1 and query.projections[0].aggregate is not None
        return ((_agg(query.projections[0].aggregate, rows, spec),),)
    index = spec.names.index(query.group_by)
    groups: dict[Value, list[Row]] = {}
    for row in rows:
        groups.setdefault(row[index], []).append(row)
    output = []
    for key, members in groups.items():
        group_rows = tuple(members)
        output.append(
            tuple(
                (
                    key
                    if projection.aggregate is None
                    else _agg(projection.aggregate, group_rows, spec)
                )
                for projection in query.projections
            )
        )
    return tuple(output)


def all_worlds(spec: Spec) -> list[tuple[Row, ...]]:
    possible_rows = list(product(*(col.domain for col in spec.columns)))
    worlds: list[tuple[Row, ...]] = []
    for size in range(spec.max_rows + 1):
        for rows in combinations_with_replacement(possible_rows, size):
            if legal_world(spec, rows):
                worlds.append(rows)
                if len(worlds) > 10000:
                    raise ValueError("reference enumeration exceeds 10000 worlds")
    return worlds


def reference_search(spec: Spec, view: Query, metric: Query) -> ReferenceResult:
    worlds = all_worlds(spec)
    seen: dict[frozenset[tuple[tuple[Value, ...], int]], tuple[int | None, tuple[Row, ...]]] = {}
    for world in worlds:
        key = frozenset(Counter(_evaluate(view, world, spec)).items())
        value = _evaluate(metric, world, spec)[0][0]
        assert value is None or type(value) is int
        if key in seen and seen[key][0] != value:
            return ReferenceResult("COUNTEREXAMPLE_FOUND", len(worlds), (seen[key][1], world))
        seen.setdefault(key, (value, world))
    return ReferenceResult("BOUNDED_NO_COUNTEREXAMPLE", len(worlds), None)


def evaluate_for_test(
    query: Query, rows: tuple[Row, ...], spec: Spec
) -> tuple[tuple[Value, ...], ...]:
    """Expose reference values for differential tests against DuckDB."""
    return _evaluate(query, rows, spec)
