"""One-world bounded Z3 search for declared test blind spots."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

import z3

from dataproof_verifier.doppel_model import Assertion, DoppelSpec
from dataproof_verifier.models import Row
from dataproof_verifier.solver import _aggregate, _scope, _sum, _unknown_code, _world


@dataclass(frozen=True)
class DoppelSearchResult:
    status: str
    rows: tuple[Row, ...] | None
    reason: str | None = None
    reason_code: str | None = None
    row_minimal_verified: bool = False


def _comparison(value: z3.ArithRef, op: str, expected: int) -> z3.BoolRef:
    if op == "=":
        return value == expected
    if op == "!=":
        return value != expected
    if op == "<":
        return value < expected
    if op == "<=":
        return value <= expected
    if op == ">":
        return value > expected
    if op == ">=":
        return value >= expected
    raise AssertionError("unvalidated assertion operator")


def search(spec: DoppelSpec) -> DoppelSearchResult:
    try:
        return _search(spec)
    except MemoryError:
        return DoppelSearchResult("INCONCLUSIVE", None, "solver memory exhausted", "MEMORY_LIMIT")
    except Exception as exc:
        return DoppelSearchResult(
            "INCONCLUSIVE", None, f"solver error: {type(exc).__name__}", "SOLVER_ERROR"
        )


def _search(spec: DoppelSpec) -> DoppelSearchResult:
    base = spec.table
    z3.set_param("memory_max_size", base.max_memory_mb)
    solver = z3.Optimize()
    solver.set("priority", "lex")
    deadline = monotonic() + base.timeout_ms / 1000

    def checked() -> z3.CheckSatResult:
        remaining = int((deadline - monotonic()) * 1000)
        if remaining <= 0:
            return z3.unknown
        solver.set("timeout", remaining)
        return solver.check()

    world = _world(solver, base, "dataset")

    def truth(assertion: Assertion) -> tuple[z3.BoolRef, z3.BoolRef]:
        agg = assertion.query.projections[0].aggregate
        assert agg is not None
        is_null, value = _aggregate(base, world, _scope(base, world, assertion.query, None), agg)
        nonnull = z3.Not(is_null)
        return z3.And(nonnull, _comparison(value, assertion.op, assertion.value)), z3.And(
            nonnull, z3.Not(_comparison(value, assertion.op, assertion.value))
        )

    for test in spec.tests:
        passed, _ = truth(test)
        solver.add(passed)
    outcome = checked()
    if outcome == z3.unsat:
        return DoppelSearchResult("INCONSISTENT_TESTS", None)
    if outcome == z3.unknown:
        reason = "timeout" if monotonic() >= deadline else solver.reason_unknown()
        return DoppelSearchResult("INCONCLUSIVE", None, reason, _unknown_code(reason))
    if outcome != z3.sat:
        return DoppelSearchResult("INCONCLUSIVE", None, "unexpected solver result", "SOLVER_ERROR")

    _, failed = truth(spec.invariant)
    solver.add(failed)
    solver.minimize(_sum([z3.If(active, 1, 0) for active in world.active]))
    for row in world.cells:
        for cell in row:
            solver.minimize(cell)
    outcome = checked()
    if outcome == z3.unsat:
        return DoppelSearchResult("BOUNDED_NO_BLIND_SPOT", None)
    if outcome == z3.unknown:
        reason = "timeout" if monotonic() >= deadline else solver.reason_unknown()
        return DoppelSearchResult("INCONCLUSIVE", None, reason, _unknown_code(reason))
    if outcome != z3.sat:
        return DoppelSearchResult("INCONCLUSIVE", None, "unexpected solver result", "SOLVER_ERROR")
    model = solver.model()
    rows: list[Row] = []
    for active, cells in zip(world.active, world.cells, strict=True):
        if z3.is_true(model.eval(active, model_completion=True)):
            rows.append(
                tuple(
                    column.domain[model.eval(cell, model_completion=True).as_long()]
                    for column, cell in zip(base.columns, cells, strict=True)
                )
            )
    solver.push()
    solver.add(_sum([z3.If(active, 1, 0) for active in world.active]) < len(rows))
    smaller = checked()
    smaller_reason = (
        ("timeout" if monotonic() >= deadline else solver.reason_unknown())
        if smaller == z3.unknown
        else None
    )
    solver.pop()
    if smaller == z3.unknown:
        assert smaller_reason is not None
        reason = smaller_reason
        return DoppelSearchResult("INCONCLUSIVE", None, reason, _unknown_code(reason))
    if smaller != z3.unsat:
        return DoppelSearchResult(
            "INCONCLUSIVE", None, "row-minimality check disagreed with optimizer", "SOLVER_ERROR"
        )
    return DoppelSearchResult("CANDIDATE", tuple(rows), row_minimal_verified=True)
