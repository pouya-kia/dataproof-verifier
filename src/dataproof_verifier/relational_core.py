"""Versioned finite relational bag plan for the admitted joined SQL fragment.

The existing guarded parser supplies typed expressions.  This module is the
single Python semantic evaluator for that fragment; DuckDB executes the
untouched SQL independently at the validation boundary.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dataproof_verifier.join_model import (
    JoinAggregate,
    JoinPredicate,
    JoinProjection,
    JoinQuery,
    JoinScalar,
    JoinSpec,
    Ref,
    World,
)

PLAN_VERSION = 1
JoinedRow = tuple[tuple[Any, ...], ...]
Bag = tuple[JoinedRow, ...]


@dataclass(frozen=True)
class Scan:
    table: int
    output_tables: frozenset[int]


@dataclass(frozen=True)
class Join:
    left: PlanNode
    right: PlanNode
    kind: str
    on: tuple[tuple[Ref, Ref], ...]
    output_tables: frozenset[int]


@dataclass(frozen=True)
class Filter:
    source: PlanNode
    predicate: JoinPredicate
    output_tables: frozenset[int]


@dataclass(frozen=True)
class Aggregate:
    source: PlanNode
    group_by: tuple[Ref | JoinScalar, ...]
    projections: tuple[JoinProjection, ...]
    output_tables: frozenset[int]


PlanNode = Scan | Join | Filter | Aggregate


@dataclass(frozen=True)
class RelationalPlan:
    version: int
    root: PlanNode
    output_names: tuple[str, ...]
    source_names: tuple[str, ...]


def compile_join_query(query: JoinQuery, spec: JoinSpec) -> RelationalPlan:
    """Compatibility adapter after the existing fail-closed, typed SQL admission."""
    if len(spec.tables) != 2 or query.join_kind not in {"inner", "left", "right", "full"}:
        raise ValueError("unsupported relational plan source or join kind")
    if not query.on or any(a.table != 0 or b.table != 1 for a, b in query.on):
        raise ValueError("join plan keys must be scope-checked left/right references")
    both = frozenset({0, 1})
    source: PlanNode = Join(
        Scan(0, frozenset({0})), Scan(1, frozenset({1})), query.join_kind, query.on, both
    )
    if query.where is not None:
        source = Filter(source, query.where, both)
    root = Aggregate(source, query.group_by, query.projections, both)
    return RelationalPlan(
        PLAN_VERSION,
        root,
        tuple(p.name for p in query.projections),
        tuple(t.table for t in spec.tables),
    )


def _value(ref: Ref, row: JoinedRow, spec: JoinSpec) -> Any:
    return row[ref.table][spec.tables[ref.table].names.index(ref.column)]


def _scalar(value: JoinScalar, row: JoinedRow, spec: JoinSpec) -> Any:
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
        return _scalar(value.args[0], row, spec)
    if value.kind in {"add", "sub"}:
        left, right = (_scalar(child, row, spec) for child in value.args)
        if left is None or right is None:
            return None
        return left + right if value.kind == "add" else left - right
    if value.kind == "case":
        base, arms, default = value.args
        base_value = _scalar(base, row, spec) if base is not None else None
        for condition, result in arms:
            if base is None:
                assert isinstance(condition, JoinPredicate)
                selected = _truth(condition, row, spec) is True
            else:
                assert isinstance(condition, JoinScalar)
                candidate = _scalar(condition, row, spec)
                selected = (
                    base_value is not None and candidate is not None and base_value == candidate
                )
            if selected:
                return _scalar(result, row, spec)
        return _scalar(default, row, spec)
    raise ValueError("unknown admitted scalar kind")


def _truth(predicate: JoinPredicate, row: JoinedRow, spec: JoinSpec) -> bool | None:
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
        result = _truth(inner, row, spec)
        return None if result is None else not result
    if op == "is_null":
        ref = operands[0]
        assert isinstance(ref, Ref)
        return _value(ref, row, spec) is None
    left, right = operands
    if isinstance(left, JoinPredicate) or isinstance(right, JoinPredicate):
        raise ValueError("predicate operands must be scalar")
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
    raise ValueError("unknown admitted predicate kind")


def _aggregate(agg: JoinAggregate, rows: Bag, spec: JoinSpec) -> Any:
    if agg.kind == "count_star":
        return len(rows)
    assert agg.value is not None
    values = [_scalar(agg.value, row, spec) for row in rows]
    nonnull = [value for value in values if value is not None]
    if agg.kind == "count":
        return len(nonnull)
    if agg.kind == "count_distinct":
        return len(set(nonnull))
    if agg.kind == "sum":
        return sum(nonnull) if nonnull else None
    if agg.kind == "min":
        return min(nonnull) if nonnull else None
    if agg.kind == "max":
        return max(nonnull) if nonnull else None
    raise ValueError("unknown admitted aggregate kind")


def _eval(node: PlanNode, spec: JoinSpec, world: World) -> Bag | tuple[tuple[Any, ...], ...]:
    if isinstance(node, Scan):
        if not 0 <= node.table < len(spec.tables):
            raise ValueError("scan table is outside the declared schema")
        return tuple(
            tuple(
                row if index == node.table else (None,) * len(table.columns)
                for index, table in enumerate(spec.tables)
            )
            for row in world[node.table]
        )
    if isinstance(node, Join):
        left = _eval(node.left, spec, world)
        right = _eval(node.right, spec, world)
        joined_rows: list[JoinedRow] = []
        matched_right: set[int] = set()
        for a in left:
            matched = False
            for index, b in enumerate(right):
                combined = tuple(
                    a[table] if table in node.left.output_tables else b[table]
                    for table in range(len(spec.tables))
                )
                if all(
                    _value(k1, combined, spec) is not None
                    and _value(k2, combined, spec) is not None
                    and _value(k1, combined, spec) == _value(k2, combined, spec)
                    for k1, k2 in node.on
                ):
                    joined_rows.append(combined)
                    matched = True
                    matched_right.add(index)
            if not matched and node.kind in {"left", "full"}:
                joined_rows.append(a)
        if node.kind in {"right", "full"}:
            joined_rows.extend(b for index, b in enumerate(right) if index not in matched_right)
        return tuple(joined_rows)
    if isinstance(node, Filter):
        return tuple(
            row
            for row in _eval(node.source, spec, world)
            if _truth(node.predicate, row, spec) is True
        )
    if isinstance(node, Aggregate):
        source = _eval(node.source, spec, world)
        if not node.group_by:
            agg = node.projections[0].aggregate
            assert agg is not None
            return ((_aggregate(agg, source, spec),),)
        groups: dict[tuple[Any, ...], list[JoinedRow]] = {}
        for row in source:
            key = tuple(
                _value(ref, row, spec) if isinstance(ref, Ref) else _scalar(ref, row, spec)
                for ref in node.group_by
            )
            groups.setdefault(key, []).append(row)
        result: list[tuple[Any, ...]] = []
        for key, members in groups.items():
            output = []
            for projection in node.projections:
                if projection.ref is not None:
                    output.append(key[node.group_by.index(projection.ref)])
                else:
                    assert projection.aggregate is not None
                    output.append(_aggregate(projection.aggregate, tuple(members), spec))
            result.append(tuple(output))
        return tuple(result)
    raise ValueError("unknown relational plan node")


def evaluate(plan: RelationalPlan, spec: JoinSpec, world: World) -> tuple[tuple[Any, ...], ...]:
    if plan.version != PLAN_VERSION or plan.source_names != tuple(t.table for t in spec.tables):
        raise ValueError("relational plan version or source schema mismatch")
    result = _eval(plan.root, spec, world)
    return tuple(result)
