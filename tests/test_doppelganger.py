"""Acceptance cases for the one-dataset test-blind-spot obligation."""

from __future__ import annotations

import duckdb
import pytest

from dataproof_verifier.doppel_model import DoppelSpec, parse_doppel_spec
from dataproof_verifier.doppel_replay import make_replay_sql, validate
from dataproof_verifier.doppel_solver import search
from dataproof_verifier.models import SpecError, UnsupportedError


def example_spec() -> dict[str, object]:
    return {
        "schema_version": 1,
        "table": {
            "name": "orders",
            "columns": [
                {"name": "amount", "type": "INTEGER", "nullable": False, "domain": [-1, 0, 1]}
            ],
        },
        "max_rows": 2,
        "tests": [
            {"id": "has_orders", "sql": "SELECT COUNT(*) AS n FROM orders", "op": ">=", "value": 1}
        ],
        "invariant": {
            "id": "no_negative_amount",
            "sql": "SELECT COUNT(*) AS n FROM orders WHERE amount = -1",
            "op": "=",
            "value": 0,
            "rationale": "Settled orders must not carry a negative amount.",
        },
    }


def test_parse_independent_assertions() -> None:
    spec = parse_doppel_spec(example_spec())
    assert isinstance(spec, DoppelSpec)
    assert spec.tests[0].id == "has_orders"
    assert spec.invariant.id == "no_negative_amount"
    assert spec.invariant.query.predicate is not None
    assert spec.table.max_rows == 2


@pytest.mark.parametrize(
    "edit,error",
    [
        (lambda s: s.update(tests=[]), SpecError),
        (lambda s: s["invariant"].update(rationale=""), SpecError),  # type: ignore[union-attr]
        (lambda s: s["tests"][0].update(op="LIKE"), UnsupportedError),  # type: ignore[index,union-attr]
        (lambda s: s["tests"][0].update(op=[]), UnsupportedError),  # type: ignore[index,union-attr]
        (
            lambda s: s["tests"][0].update(sql="DELETE FROM orders"),  # type: ignore[index,union-attr]
            UnsupportedError,
        ),
    ],
)
def test_invalid_assertions_fail_closed(edit: object, error: type[Exception]) -> None:
    spec = example_spec()
    edit(spec)  # type: ignore[operator]
    with pytest.raises(error):
        parse_doppel_spec(spec)


def test_one_world_witness_is_row_reduced() -> None:
    spec = parse_doppel_spec(example_spec())
    result = search(spec)
    assert result.status == "CANDIDATE"
    assert result.rows == ((-1,),)
    checked = validate(spec, result.rows)
    assert checked.valid
    assert checked.tests[0].truth is True
    assert checked.invariant is not None and checked.invariant.truth is False
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        assert con.execute(make_replay_sql(spec, result.rows)).fetchall() == [("REPLAY_OK",)]
    finally:
        con.close()


def test_existing_test_prevents_violation() -> None:
    raw = example_spec()
    raw["tests"] = [raw["invariant"] | {"id": "prohibits_negative"}]
    raw["tests"][0].pop("rationale")  # type: ignore[index]
    assert search(parse_doppel_spec(raw)).status == "BOUNDED_NO_BLIND_SPOT"


def test_inconsistent_tests_are_distinct() -> None:
    raw = example_spec()
    raw["tests"] = [
        {"id": "impossible_count", "sql": "SELECT COUNT(*) AS n FROM orders", "op": ">", "value": 2}
    ]
    assert search(parse_doppel_spec(raw)).status == "INCONSISTENT_TESTS"


def test_unknown_invariant_is_not_false() -> None:
    raw = example_spec()
    raw["max_rows"] = 0
    raw["tests"] = [
        {"id": "empty", "sql": "SELECT COUNT(*) AS n FROM orders", "op": "=", "value": 0}
    ]
    raw["invariant"] = {
        "id": "sum_nonnegative",
        "sql": "SELECT SUM(amount) AS n FROM orders",
        "op": ">=",
        "value": 0,
        "rationale": "Explicitly declared but undefined on empty input.",
    }
    assert search(parse_doppel_spec(raw)).status == "BOUNDED_NO_BLIND_SPOT"
