"""Seed-stable adversarial SQL properties against unchanged DuckDB queries.

DuckDB execution is independent of the reference evaluator; schema admission
and finite-domain assumptions are still shared and are not a formal proof.
"""

from __future__ import annotations

import itertools
import os
from collections import Counter
from datetime import date

import duckdb
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dataproof_verifier import reference_enumerator as reference
from dataproof_verifier.ir import Aggregate
from dataproof_verifier.models import Row, Spec, legal_world, parse_spec
from dataproof_verifier.parser import parse_query
from dataproof_verifier.replay import validate
from dataproof_verifier.solver import search

DAY = date(2026, 10, 1)
EXAMPLES = 150 if os.environ.get("DATAPROOF_STRESS") == "1" else 24
GROUPED = (
    "SELECT day AS bucket, COUNT(*) AS n, COUNT(v) AS present, "
    "COUNT(DISTINCT v) AS distinct_v, SUM(v) AS total, "
    "MIN(v) AS lo, MAX(v) AS hi FROM t GROUP BY day"
)
SCALARS = (
    "SELECT COUNT(*) AS n FROM t",
    "SELECT COUNT(v) AS n FROM t",
    "SELECT COUNT(DISTINCT v) AS n FROM t",
    "SELECT SUM(v) AS n FROM t",
    "SELECT MIN(v) AS n FROM t",
    "SELECT MAX(v) AS n FROM t",
    "SELECT COUNT(*) AS n FROM t WHERE v = 1",
    "SELECT COUNT(v) AS n FROM t WHERE v IS NULL",
    "SELECT COUNT(*) AS n FROM t WHERE v IS NOT NULL",
)


def _raw(*, keyed: bool = False) -> dict[str, object]:
    if keyed:
        columns = [
            {"name": "id", "type": "INTEGER", "domain": [1, 2]},
            {"name": "u", "type": "INTEGER", "nullable": True, "domain": [7, None]},
        ]
    else:
        columns = [
            {"name": "day", "type": "DATE", "nullable": True, "domain": ["2026-10-01", None]},
            {"name": "v", "type": "INTEGER", "nullable": True, "domain": [-1, 0, 1, None]},
        ]
    return {
        "table": {
            "name": "t",
            "columns": columns,
            "primary_key": ["id"] if keyed else [],
            "unique": [["u"]] if keyed else [],
        },
        "views": [GROUPED if not keyed else "SELECT id, COUNT(*) AS n FROM t GROUP BY id"],
        "metric": "SELECT COUNT(*) AS n FROM t",
        "max_rows": 3,
    }


def _duckdb_rows(world: tuple[tuple[object, ...], ...], sql: str) -> Counter[tuple[object, ...]]:
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE t (day DATE, v INTEGER)")
        if world:
            con.executemany("INSERT INTO t VALUES (?, ?)", world)
        return Counter(tuple(row) for row in con.execute(sql).fetchall())
    finally:
        con.close()


def _assert_reference_matches(world: tuple[tuple[object, ...], ...], sql: str) -> None:
    spec = parse_spec(_raw())
    query = parse_query(sql, spec, metric="GROUP BY" not in sql)
    assert Counter(reference.evaluate_for_test(query, world, spec)) == _duckdb_rows(world, sql)


@settings(max_examples=EXAMPLES, derandomize=True, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from([DAY, None]), st.sampled_from([-1, 0, 1, None])),
        min_size=0,
        max_size=3,
    )
)
def test_generated_null_bag_aggregate_differential(rows: list[tuple[object, object]]) -> None:
    world = tuple(rows)
    for sql in (GROUPED, *SCALARS):
        _assert_reference_matches(world, sql)
    # Row permutation is semantics-preserving for these unordered bag queries.
    spec = parse_spec(_raw())
    query = parse_query(GROUPED, spec, metric=False)
    assert Counter(reference.evaluate_for_test(query, world, spec)) == Counter(
        reference.evaluate_for_test(query, world[::-1], spec)
    )
    assert _duckdb_rows(world, GROUPED) == _duckdb_rows(world[::-1], GROUPED)
    assert _duckdb_rows(world, "SELECT COUNT(*) AS n FROM t") == Counter({(len(world),): 1})


@settings(max_examples=EXAMPLES, derandomize=True, deadline=None)
@given(st.lists(st.tuples(st.sampled_from([1, 2]), st.sampled_from([7, None])), max_size=3))
def test_primary_and_nullable_unique_match_duckdb(rows: list[tuple[int, int | None]]) -> None:
    world = tuple(rows)
    spec = parse_spec(_raw(keyed=True))
    admitted = legal_world(spec, world)
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, u INTEGER UNIQUE)")
        try:
            for row in world:
                con.execute("INSERT INTO t VALUES (?, ?)", row)
            duckdb_admitted = True
        except duckdb.ConstraintException:
            duckdb_admitted = False
        assert admitted == duckdb_admitted
    finally:
        con.close()


@pytest.mark.parametrize(
    "metric",
    [
        "SELECT MAX(v) AS n FROM t",
        "SELECT MIN(v) AS n FROM t",
        "SELECT COUNT(DISTINCT v) AS n FROM t",
        "SELECT SUM(v) AS n FROM t",
    ],
)
def test_solver_verdict_matches_independent_finite_duckdb(metric: str) -> None:
    raw = _raw()
    raw["table"]["columns"][0]["nullable"] = False  # type: ignore[index]
    raw["table"]["columns"][0]["domain"] = ["2026-10-01"]  # type: ignore[index]
    raw["table"]["columns"][1]["nullable"] = False  # type: ignore[index]
    raw["table"]["columns"][1]["domain"] = [0, 1]  # type: ignore[index]
    raw["max_rows"] = 2
    raw["views"] = ["SELECT day, COUNT(*) AS n, SUM(v) AS total FROM t GROUP BY day"]
    raw["metric"] = metric
    spec = parse_spec(raw)
    view = parse_query(spec.views[0], spec, metric=False)
    query = parse_query(spec.metric, spec, metric=True)
    found = search(spec, view, query)
    universe = [()]
    possible = [(DAY, 0), (DAY, 1)]
    for size in (1, 2):
        universe.extend(itertools.combinations_with_replacement(possible, size))
    observations = [
        (_duckdb_rows(world, spec.views[0]), _duckdb_rows(world, spec.metric)) for world in universe
    ]
    independent_positive = any(
        observations[i][0] == observations[j][0] and observations[i][1] != observations[j][1]
        for i, j in itertools.combinations(range(len(universe)), 2)
    )
    assert found.status != "INCONCLUSIVE"
    assert (found.worlds is not None) == independent_positive
    if found.worlds is not None:
        assert validate(spec, *found.worlds).valid


@pytest.mark.parametrize(
    ("sql", "world", "mutant_kind"),
    [
        ("SELECT COUNT(v) AS n FROM t", ((DAY, None),), "count"),
        ("SELECT COUNT(DISTINCT v) AS n FROM t", ((DAY, 1), (DAY, 1)), "count_distinct"),
        ("SELECT SUM(v) AS n FROM t", (), "sum"),
    ],
)
def test_duckdb_differential_kills_local_aggregate_mutants(
    monkeypatch: pytest.MonkeyPatch,
    sql: str,
    world: tuple[tuple[object, ...], ...],
    mutant_kind: str,
) -> None:
    original = reference._agg

    def mutant(agg: Aggregate, rows: tuple[Row, ...], spec: Spec) -> int | None:
        if agg.kind == mutant_kind:
            if mutant_kind == "sum":
                return 0  # wrong empty SUM
            return len(rows)  # wrong NULL COUNT or DISTINCT count
        return original(agg, rows, spec)

    _assert_reference_matches(world, sql)
    monkeypatch.setattr(reference, "_agg", mutant)
    with pytest.raises(AssertionError):
        _assert_reference_matches(world, sql)


def test_duplicate_row_mutation_is_detected_by_unchanged_sql() -> None:
    world = ((DAY, 1), (DAY, 1))
    correct = _duckdb_rows(world, "SELECT COUNT(*) AS n FROM t")
    deduplicated_mutant = _duckdb_rows(tuple(set(world)), "SELECT COUNT(*) AS n FROM t")
    assert correct == Counter({(2,): 1})
    assert correct != deduplicated_mutant
