from __future__ import annotations

import json
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path

import duckdb
import pytest
from conftest import BASE
from hypothesis import given, settings
from hypothesis import strategies as st

from dataproof_verifier.cli import check
from dataproof_verifier.models import UnsupportedError, parse_spec
from dataproof_verifier.parser import parse_query
from dataproof_verifier.reference_enumerator import all_worlds, evaluate_for_test, reference_search
from dataproof_verifier.replay import validate, validate_serialized
from dataproof_verifier.solver import search


@pytest.mark.parametrize(
    "clause",
    [
        "customer_id = 1",
        "customer_id = -1",
        "customer_id = 99",
        "customer_id IS NULL",
        "customer_id IS NOT NULL",
    ],
)
def test_filter_reference_matches_duckdb_on_every_tiny_world(
    base_spec: dict[str, object], clause: str
) -> None:
    raw = deepcopy(base_spec)
    raw["table"]["columns"][1]["nullable"] = True
    raw["table"]["columns"][1]["domain"].append(None)
    raw["table"]["columns"][1]["domain"].append(-1)
    spec = parse_spec(raw)
    sqls = (
        "SELECT day, COUNT(*) AS n, COUNT(DISTINCT customer_id) AS d "
        f"FROM orders WHERE {clause} GROUP BY day",
        f"SELECT COUNT(*) AS n FROM orders WHERE {clause}",
        f"SELECT SUM(amount) AS n FROM orders WHERE {clause}",
    )
    queries = [parse_query(sql, spec, metric=i != 0) for i, sql in enumerate(sqls)]
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE orders (day DATE, customer_id INTEGER, amount INTEGER)")
        for world in all_worlds(spec):
            con.execute("DELETE FROM orders")
            if world:
                con.executemany("INSERT INTO orders VALUES (?, ?, ?)", world)
            for i, (sql, query) in enumerate(zip(sqls, queries, strict=True)):
                actual = con.execute(sql).fetchall()
                expected = evaluate_for_test(query, world, spec)
                assert Counter(actual) == Counter(expected) if i == 0 else actual == list(expected)
    finally:
        con.close()


@settings(max_examples=10, derandomize=True, deadline=None)
@given(
    st.sampled_from(["customer_id = 1", "customer_id IS NULL", "customer_id IS NOT NULL"]),
    st.booleans(),
)
def test_filter_solver_reference_agreement(clause: str, unique: bool) -> None:
    raw = deepcopy(BASE)
    raw["table"]["columns"][1]["nullable"] = True
    raw["table"]["columns"][1]["domain"].append(None)
    raw["table"]["unique"] = [["customer_id"]] if unique else []
    raw["views"] = [f"SELECT day, COUNT(*) AS n FROM orders WHERE {clause} GROUP BY day"]
    raw["metric"] = "SELECT COUNT(*) AS n FROM orders"
    spec = parse_spec(raw)
    view = parse_query(spec.views[0], spec, metric=False)
    metric = parse_query(spec.metric, spec, metric=True)
    result = search(spec, view, metric)
    reference = reference_search(spec, view, metric)
    assert result.status != "INCONCLUSIVE"
    assert (result.worlds is not None) == (reference.witness is not None)
    if result.worlds is not None:
        assert validate(spec, *result.worlds).valid


@pytest.mark.parametrize(
    "clause",
    [
        "customer_id = NULL",
        "customer_id < 2",
        "customer_id = 1 OR amount = 10",
        "customer_id = 1 AND amount = 10",
        "customer_id IN (1, 2)",
        "day = 1",
        "customer_id = 1.0",
        "customer_id = amount",
        "TRUE",
        "random() > 0",
    ],
)
def test_unsupported_filter_fails_closed(base_spec: dict[str, object], clause: str) -> None:
    spec = parse_spec(base_spec)
    with pytest.raises(UnsupportedError):
        parse_query(
            f"SELECT day, COUNT(*) AS n FROM orders WHERE {clause} GROUP BY day", spec, metric=False
        )


def test_filtered_cli_witness_replays(base_spec: dict[str, object], tmp_path: Path) -> None:
    raw = deepcopy(base_spec)
    raw["views"] = ["SELECT day, COUNT(*) AS n FROM orders WHERE customer_id = 1 GROUP BY day"]
    raw["metric"] = "SELECT COUNT(*) AS n FROM orders"
    raw["output_dir"] = str(tmp_path / "out")
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == 0
    result = json.loads((tmp_path / "out/result.json").read_text())
    assert result["status"] == "COUNTEREXAMPLE_FOUND"
    assert validate_serialized(tmp_path / "out/witness.json").valid


def test_filter_bag_null_and_row_order_metamorphism(base_spec: dict[str, object]) -> None:
    raw = deepcopy(base_spec)
    raw["table"]["columns"][1]["nullable"] = True
    raw["table"]["columns"][1]["domain"].append(None)
    spec = parse_spec(raw)
    rows = (
        (date(2026, 1, 1), 1, 10),
        (date(2026, 1, 1), None, 10),
        (date(2026, 1, 1), None, 10),
    )
    for sql, expected in (
        ("SELECT COUNT(*) AS n FROM orders WHERE customer_id IS NULL", 2),
        ("SELECT COUNT(*) AS n FROM orders WHERE customer_id IS NOT NULL", 1),
        ("SELECT COUNT(*) AS n FROM orders WHERE customer_id = 1", 1),
        ("SELECT COUNT(*) AS n FROM orders WHERE customer_id = 99", 0),
    ):
        query = parse_query(sql, spec, metric=True)
        assert evaluate_for_test(query, rows, spec) == ((expected,),)
        assert evaluate_for_test(query, rows[::-1], spec) == ((expected,),)


def test_filter_mutation_is_caught_by_duckdb(
    base_spec: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataproof_verifier.reference_enumerator as reference

    spec = parse_spec(base_spec)
    sql = "SELECT COUNT(*) AS n FROM orders WHERE customer_id = 1"
    query = parse_query(sql, spec, metric=True)
    world = ((date(2026, 1, 1), 2, 10),)
    assert evaluate_for_test(query, world, spec) == ((0,),)
    original = reference._evaluate
    monkeypatch.setattr(
        reference,
        "_evaluate",
        lambda q, rows, parsed: original(replace(q, predicate=None), rows, parsed),
    )
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE orders (day DATE, customer_id INTEGER, amount INTEGER)")
        con.execute("INSERT INTO orders VALUES (?, ?, ?)", world[0])
        assert con.execute(sql).fetchall() == [(0,)]
        assert evaluate_for_test(query, world, spec) != ((0,),)
    finally:
        con.close()
