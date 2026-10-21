"""Complete finite row-slot Z3 encoding for the guarded aggregate IR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

import z3

from dataproof_verifier.ir import Aggregate, Query
from dataproof_verifier.models import Row, Spec, Value

ZBool: TypeAlias = z3.BoolRef
ZInt: TypeAlias = z3.ArithRef
ZValue: TypeAlias = tuple[ZBool, ZInt]


@dataclass(frozen=True)
class SearchResult:
    status: str
    worlds: tuple[tuple[Row, ...], tuple[Row, ...]] | None
    reason: str | None
    reason_code: str | None = None


@dataclass
class _World:
    active: list[ZBool]
    cells: list[list[ZInt]]


def _ors(items: list[ZBool]) -> ZBool:
    return z3.Or(*items) if items else z3.BoolVal(False)


def _sum(items: list[ZInt]) -> ZInt:
    return z3.Sum(*items) if items else z3.IntVal(0)


def _world(solver: z3.Optimize, spec: Spec, label: str) -> _World:
    active = [z3.Bool(f"{label}_active_{i}") for i in range(spec.max_rows)]
    cells = [
        [z3.Int(f"{label}_r{i}_c{j}") for j in range(len(spec.columns))]
        for i in range(spec.max_rows)
    ]
    for i, row in enumerate(cells):
        if i:
            solver.add(z3.Implies(active[i], active[i - 1]))
        for j, cell in enumerate(row):
            solver.add(cell >= 0, cell < len(spec.columns[j].domain))
            solver.add(z3.Implies(z3.Not(active[i]), cell == 0))
    for key in ((spec.primary_key,) if spec.primary_key else ()) + spec.unique:
        indices = [spec.names.index(name) for name in key]
        for i in range(spec.max_rows):
            for j in range(i + 1, spec.max_rows):
                nonnull = [
                    cells[i][k] != spec.columns[k].domain.index(None)
                    for k in indices
                    if None in spec.columns[k].domain
                ] + [
                    cells[j][k] != spec.columns[k].domain.index(None)
                    for k in indices
                    if None in spec.columns[k].domain
                ]
                distinct = _ors([cells[i][k] != cells[j][k] for k in indices])
                solver.add(z3.Implies(z3.And(active[i], active[j], *nonnull), distinct))
    return _World(active, cells)


def _scope(spec: Spec, world: _World, query: Query, group: tuple[str, Value] | None) -> list[ZBool]:
    mask = world.active
    if query.predicate is not None:
        predicate = query.predicate
        index = spec.names.index(predicate.column)
        domain = spec.columns[index].domain
        if predicate.kind == "eq":
            condition = (
                [row[index] == domain.index(predicate.value) for row in world.cells]
                if predicate.value in domain
                else [z3.BoolVal(False) for _ in world.cells]
            )
        elif predicate.kind == "is_null":
            condition = (
                [row[index] == domain.index(None) for row in world.cells]
                if None in domain
                else [z3.BoolVal(False) for _ in world.cells]
            )
        elif predicate.kind == "is_not_null":
            condition = (
                [row[index] != domain.index(None) for row in world.cells]
                if None in domain
                else [z3.BoolVal(True) for _ in world.cells]
            )
        else:
            raise AssertionError(f"unexpected IR predicate: {predicate.kind}")
        mask = [z3.And(on, pred) for on, pred in zip(mask, condition, strict=True)]
    if group is None:
        return mask
    name, value = group
    index = spec.names.index(name)
    code = spec.columns[index].domain.index(value)
    return [z3.And(on, row[index] == code) for on, row in zip(mask, world.cells, strict=True)]


def _aggregate(spec: Spec, world: _World, mask: list[ZBool], agg: Aggregate) -> ZValue:
    if agg.kind == "count_star":
        return z3.BoolVal(False), _sum([z3.If(on, 1, 0) for on in mask])
    assert agg.column is not None
    index = spec.names.index(agg.column)
    col = spec.columns[index]
    valid = [
        z3.And(on, row[index] != col.domain.index(None)) if None in col.domain else on
        for on, row in zip(mask, world.cells, strict=True)
    ]
    if agg.kind == "count":
        return z3.BoolVal(False), _sum([z3.If(on, 1, 0) for on in valid])
    if agg.kind == "count_distinct":
        hits = [
            _ors(
                [z3.And(on, row[index] == code) for on, row in zip(valid, world.cells, strict=True)]
            )
            for code, value in enumerate(col.domain)
            if value is not None
        ]
        return z3.BoolVal(False), _sum([z3.If(hit, 1, 0) for hit in hits])
    if agg.kind == "sum":
        assert all(value is None or type(value) is int for value in col.domain)
        terms = []
        for on, row in zip(valid, world.cells, strict=True):
            mapped = _sum(
                [
                    z3.If(row[index] == code, value, 0)
                    for code, value in enumerate(col.domain)
                    if type(value) is int
                ]
            )
            terms.append(z3.If(on, mapped, 0))
        return z3.Not(_ors(valid)), _sum(terms)
    if agg.kind in {"min", "max"}:
        assert all(value is None or type(value) is int for value in col.domain)
        ranked = sorted(
            ((value, code) for code, value in enumerate(col.domain) if type(value) is int),
            reverse=agg.kind == "min",
        )
        extremum: ZInt = z3.IntVal(0)
        for value, code in ranked:
            present = _ors(
                [z3.And(on, row[index] == code) for on, row in zip(valid, world.cells, strict=True)]
            )
            extremum = z3.If(present, value, extremum)
        return z3.Not(_ors(valid)), extremum
    raise AssertionError(f"unexpected IR aggregate: {agg.kind}")


def _equal(a: ZValue, b: ZValue) -> ZBool:
    return z3.And(a[0] == b[0], z3.Implies(z3.Not(a[0]), a[1] == b[1]))


def _different(a: ZValue, b: ZValue) -> ZBool:
    return z3.Not(_equal(a, b))


def _unknown_code(reason: str) -> str:
    normalized = reason.lower()
    if "memory" in normalized:
        return "MEMORY_LIMIT"
    if "timeout" in normalized or "canceled" in normalized:
        return "TIMEOUT"
    return "UNKNOWN"


def search(spec: Spec, view: Query, metric: Query) -> SearchResult:
    try:
        return _search(spec, view, metric)
    except MemoryError:
        return SearchResult("INCONCLUSIVE", None, "solver memory exhausted", "MEMORY_LIMIT")
    except Exception as exc:
        # Z3 may fail during setup, check, reason extraction, or model decoding.
        # None of these failures is evidence for either SAT or UNSAT.
        return SearchResult(
            "INCONCLUSIVE", None, f"solver error: {type(exc).__name__}", "SOLVER_ERROR"
        )


def _search(spec: Spec, view: Query, metric: Query) -> SearchResult:
    z3.set_param("memory_max_size", spec.max_memory_mb)
    solver = z3.Optimize()
    solver.set("timeout", spec.timeout_ms)
    solver.set("priority", "lex")
    left = _world(solver, spec, "left")
    right = _world(solver, spec, "right")
    assert view.group_by is not None
    group_col = spec.column(view.group_by)
    for key in group_col.domain:
        group = (view.group_by, key)
        lmask = _scope(spec, left, view, group)
        rmask = _scope(spec, right, view, group)
        lhas, rhas = _ors(lmask), _ors(rmask)
        solver.add(lhas == rhas)
        for proj in view.projections:
            if proj.aggregate is not None:
                lvalue = _aggregate(spec, left, lmask, proj.aggregate)
                rvalue = _aggregate(spec, right, rmask, proj.aggregate)
                solver.add(z3.Implies(lhas, _equal(lvalue, rvalue)))
    metric_agg = metric.projections[0].aggregate
    assert metric_agg is not None
    solver.add(
        _different(
            _aggregate(spec, left, _scope(spec, left, metric, None), metric_agg),
            _aggregate(spec, right, _scope(spec, right, metric, None), metric_agg),
        )
    )
    # Complete lexicographic objectives give a stable canonical witness for a
    # fixed finite spec. This also minimizes total source rows within the bound.
    solver.minimize(_sum([z3.If(on, 1, 0) for on in left.active + right.active]))
    solver.minimize(_sum([z3.If(on, 1, 0) for on in left.active]))
    for world in (left, right):
        for row in world.cells:
            for cell in row:
                solver.minimize(cell)
    outcome = solver.check()
    if outcome == z3.unsat:
        return SearchResult("BOUNDED_NO_COUNTEREXAMPLE", None, None)
    if outcome == z3.unknown:
        reason = solver.reason_unknown()
        return SearchResult("INCONCLUSIVE", None, reason, _unknown_code(reason))
    if outcome != z3.sat:
        return SearchResult("INCONCLUSIVE", None, "unexpected solver result", "SOLVER_ERROR")
    model = solver.model()

    def decode(world: _World) -> tuple[Row, ...]:
        rows: list[Row] = []
        for on, cells in zip(world.active, world.cells, strict=True):
            if z3.is_true(model.eval(on)):
                rows.append(
                    tuple(
                        col.domain[model.eval(cell).as_long()]
                        for col, cell in zip(spec.columns, cells, strict=True)
                    )
                )
        return tuple(rows)

    return SearchResult("CANDIDATE", (decode(left), decode(right)), None)
