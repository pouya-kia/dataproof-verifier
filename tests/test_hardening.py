"""Phase 2 adversarial, metamorphic, differential and golden checks."""

from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import duckdb
import pytest
from conftest import BASE, ROOT
from hypothesis import given, settings
from hypothesis import strategies as st

from dataproof_verifier.cli import check
from dataproof_verifier.models import parse_spec
from dataproof_verifier.parser import parse_query
from dataproof_verifier.reference_enumerator import all_worlds, evaluate_for_test, reference_search
from dataproof_verifier.replay import validate_serialized
from dataproof_verifier.solver import search


def _raw(base: dict[str, Any], *, nullable: bool, key: bool, aggregate: str) -> dict[str, Any]:
    raw = deepcopy(base)
    raw["max_rows"] = 2
    raw["table"]["columns"][2]["domain"] = [-1, 0]
    if nullable:
        for index in (1, 2):
            raw["table"]["columns"][index]["nullable"] = True
            raw["table"]["columns"][index]["domain"].append(None)
    if key:
        raw["table"]["unique"] = [["customer_id"]]
    raw["views"] = [f"SELECT day, {aggregate} AS observed FROM orders GROUP BY day"]
    raw["metric"] = "SELECT COUNT(DISTINCT customer_id) AS answer FROM orders"
    return raw


@pytest.mark.parametrize(
    "nullable,key", [(False, False), (True, False), (False, True), (True, True)]
)
@pytest.mark.parametrize(
    "aggregate", ["COUNT(*)", "COUNT(customer_id)", "COUNT(DISTINCT customer_id)", "SUM(amount)"]
)
def test_tiny_worlds_reference_duckdb_and_solver_agree(
    base_spec: dict[str, Any], nullable: bool, key: bool, aggregate: str
) -> None:
    spec = parse_spec(_raw(base_spec, nullable=nullable, key=key, aggregate=aggregate))
    view = parse_query(spec.views[0], spec, metric=False)
    metric = parse_query(spec.metric, spec, metric=True)
    worlds = all_worlds(spec)
    assert worlds
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE orders (day DATE, customer_id INTEGER, amount INTEGER)")
        for world in worlds:
            con.execute("DELETE FROM orders")
            for row in world:
                con.execute("INSERT INTO orders VALUES (?, ?, ?)", row)
            assert Counter(con.execute(spec.views[0]).fetchall()) == Counter(
                evaluate_for_test(view, world, spec)
            )
            assert con.execute(spec.metric).fetchall() == list(
                evaluate_for_test(metric, world, spec)
            )
    finally:
        con.close()
    found = search(spec, view, metric)
    reference = reference_search(spec, view, metric)
    assert found.status != "INCONCLUSIVE", found.reason
    assert (found.worlds is not None) == (reference.witness is not None)


@settings(max_examples=10, derandomize=True, deadline=None)
@given(st.permutations([1, 2]), st.permutations([-1, 0]))
def test_domain_permutation_preserves_existence(customers: list[int], amounts: list[int]) -> None:
    raw = _raw(BASE, nullable=False, key=False, aggregate="COUNT(*)")
    raw["table"]["columns"][1]["domain"] = customers
    raw["table"]["columns"][2]["domain"] = amounts
    spec = parse_spec(raw)
    view = parse_query(spec.views[0], spec, metric=False)
    metric = parse_query(spec.metric, spec, metric=True)
    found = search(spec, view, metric)
    reference = reference_search(spec, view, metric)
    assert found.status != "INCONCLUSIVE", found.reason
    assert (found.worlds is not None) == (reference.witness is not None)


@pytest.mark.parametrize(
    "view_sql",
    [
        "select day, count(*) as observed from orders group by day",
        "SELECT  day , COUNT ( * ) AS observed FROM orders GROUP BY day",
    ],
)
def test_query_formatting_is_metamorphic(base_spec: dict[str, Any], view_sql: str) -> None:
    raw = _raw(base_spec, nullable=False, key=False, aggregate="COUNT(*)")
    original = parse_spec(raw)
    raw["views"] = [view_sql]
    variant = parse_spec(raw)
    original_result = search(
        original,
        parse_query(original.views[0], original, metric=False),
        parse_query(original.metric, original, metric=True),
    )
    variant_result = search(
        variant,
        parse_query(variant.views[0], variant, metric=False),
        parse_query(variant.metric, variant, metric=True),
    )
    assert original_result.status == variant_result.status
    assert original_result.worlds == variant_result.worlds


def test_distinct_semantic_mutation_is_caught_by_duckdb(
    base_spec: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataproof_verifier.reference_enumerator as reference

    spec = parse_spec(base_spec)
    query = parse_query(spec.metric, spec, metric=True)
    row = (spec.columns[0].domain[0], 1, 10)
    world = (row, row)
    assert evaluate_for_test(query, world, spec) == ((1,),)
    original = reference._agg

    def broken(agg: Any, rows: Any, parsed: Any) -> Any:
        if agg.kind == "count_distinct":
            return len(rows)
        return original(agg, rows, parsed)

    monkeypatch.setattr(reference, "_agg", broken)
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE orders (day DATE, customer_id INTEGER, amount INTEGER)")
        for item in world:
            con.execute("INSERT INTO orders VALUES (?, ?, ?)", item)
        assert con.execute(spec.metric).fetchall() == [(1,)]
        assert evaluate_for_test(query, world, spec) != ((1,),)
    finally:
        con.close()


def test_integer_sum_beyond_32_bit_is_exact(base_spec: dict[str, Any]) -> None:
    raw = deepcopy(base_spec)
    raw["max_rows"] = 3
    raw["table"]["columns"][2]["domain"] = [2**31 - 1, -(2**31)]
    raw["metric"] = "SELECT SUM(amount) AS total FROM orders"
    spec = parse_spec(raw)
    query = parse_query(spec.metric, spec, metric=True)
    day = spec.columns[0].domain[0]
    world = ((day, 1, 2**31 - 1), (day, 1, 2**31 - 1), (day, 1, 2**31 - 1))
    expected = 3 * (2**31 - 1)
    assert evaluate_for_test(query, world, spec) == ((expected,),)
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE orders (day DATE, customer_id INTEGER, amount INTEGER)")
        for row in world:
            con.execute("INSERT INTO orders VALUES (?, ?, ?)", row)
        assert con.execute(spec.metric).fetchall() == [(expected,)]
    finally:
        con.close()


def test_versioned_golden_witness_regenerates(base_spec: dict[str, Any], tmp_path: Path) -> None:
    raw = deepcopy(base_spec)
    raw["output_dir"] = str(tmp_path / "out")
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == 0
    generated = tmp_path / "out/witness.json"
    assert validate_serialized(generated).valid
    golden = ROOT / "examples/no_undo/evidence/witness.json"
    expected = json.loads(golden.read_text())
    actual = json.loads(generated.read_text())
    assert actual["worlds"] == expected["worlds"]
    assert actual["worlds_sha256"] == expected["worlds_sha256"]
    # GROUP BY without ORDER BY has bag semantics, not a stable output order.
    assert [Counter(map(tuple, rows)) for rows in actual["view_rows"]] == [
        Counter(map(tuple, rows)) for rows in expected["view_rows"]
    ]
    assert actual["metric_values"] == expected["metric_values"]
    assert (tmp_path / "out/replay.sql").read_text() == (
        ROOT / "examples/no_undo/evidence/replay.sql"
    ).read_text()
