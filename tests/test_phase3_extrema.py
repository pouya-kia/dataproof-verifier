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
from dataproof_verifier.models import UnsupportedError, parse_spec
from dataproof_verifier.parser import parse_query
from dataproof_verifier.reference_enumerator import all_worlds, evaluate_for_test, reference_search
from dataproof_verifier.replay import validate, validate_serialized
from dataproof_verifier.solver import search


@pytest.mark.parametrize("kind", ["MIN", "MAX"])
@pytest.mark.parametrize("filter_clause", ["", " WHERE customer_id IS NULL"])
def test_extrema_exhaustive_duckdb(
    base_spec: dict[str, object], kind: str, filter_clause: str
) -> None:
    raw = deepcopy(base_spec)
    raw["table"]["columns"][1]["nullable"] = True
    raw["table"]["columns"][1]["domain"].append(None)
    raw["table"]["columns"][2]["nullable"] = True
    raw["table"]["columns"][2]["domain"] = [-3, 10, None]
    spec = parse_spec(raw)
    sqls = (
        f"SELECT day, {kind}(amount) AS x FROM orders{filter_clause} GROUP BY day",
        f"SELECT {kind}(amount) AS x FROM orders{filter_clause}",
    )
    queries = [parse_query(sql, spec, metric=i == 1) for i, sql in enumerate(sqls)]
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


@settings(max_examples=12, derandomize=True, deadline=None)
@given(
    st.sampled_from(["MIN", "MAX"]),
    st.sampled_from(["MIN", "MAX", "COUNT"]),
    st.booleans(),
)
def test_extrema_solver_reference_agreement(kind: str, metric_kind: str, unique: bool) -> None:
    raw = deepcopy(BASE)
    raw["table"]["columns"][2]["nullable"] = True
    raw["table"]["columns"][2]["domain"] = [-3, 10, None]
    raw["table"]["unique"] = [["customer_id"]] if unique else []
    raw["views"] = [f"SELECT day, {kind}(amount) AS x FROM orders GROUP BY day"]
    raw["metric"] = (
        "SELECT COUNT(*) AS n FROM orders"
        if metric_kind == "COUNT"
        else f"SELECT {metric_kind}(amount) AS n FROM orders"
    )
    spec = parse_spec(raw)
    view = parse_query(spec.views[0], spec, metric=False)
    metric = parse_query(spec.metric, spec, metric=True)
    result = search(spec, view, metric)
    reference = reference_search(spec, view, metric)
    assert result.status != "INCONCLUSIVE"
    assert (result.worlds is not None) == (reference.witness is not None)
    if result.worlds is not None:
        assert validate(spec, *result.worlds).valid


@pytest.mark.parametrize("kind", ["MIN", "MAX"])
def test_extrema_reject_date(base_spec: dict[str, object], kind: str) -> None:
    spec = parse_spec(base_spec)
    with pytest.raises(UnsupportedError):
        parse_query(f"SELECT {kind}(day) AS x FROM orders", spec, metric=True)


@pytest.mark.parametrize("kind", ["MIN", "MAX"])
def test_extrema_reject_scalar_two_argument_form(base_spec: dict[str, object], kind: str) -> None:
    spec = parse_spec(base_spec)
    with pytest.raises(UnsupportedError):
        parse_query(f"SELECT {kind}(amount, 1) AS x FROM orders", spec, metric=True)


def test_extrema_cli_witness_replays(tmp_path: Path) -> None:
    raw = json.loads((ROOT / "examples/no_undo/integer_extrema.json").read_text())
    raw["output_dir"] = str(tmp_path / "out")
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert check(path, None, False) == 0
    assert validate_serialized(tmp_path / "out/witness.json").valid


def test_max_mutation_is_caught_by_duckdb(
    base_spec: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataproof_verifier.reference_enumerator as reference

    raw = deepcopy(base_spec)
    raw["table"]["columns"][2]["domain"] = [-3, 10]
    spec = parse_spec(raw)
    sql = "SELECT MAX(amount) AS x FROM orders"
    query = parse_query(sql, spec, metric=True)
    day = spec.columns[0].domain[0]
    world = ((day, 1, -3), (day, 2, 10))
    assert evaluate_for_test(query, world, spec) == ((10,),)
    original = reference._agg

    def broken(agg: Any, rows: Any, parsed: Any) -> Any:
        if agg.kind == "max":
            return -3
        return original(agg, rows, parsed)

    monkeypatch.setattr(reference, "_agg", broken)
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute("CREATE TABLE orders (day DATE, customer_id INTEGER, amount INTEGER)")
        con.executemany("INSERT INTO orders VALUES (?, ?, ?)", world)
        assert con.execute(sql).fetchall() == [(10,)]
        assert evaluate_for_test(query, world, spec) != ((10,),)
    finally:
        con.close()
