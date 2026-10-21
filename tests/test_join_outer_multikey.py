"""Independent tiny-world checks of composite equijoins and RIGHT/FULL null extension."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import pytest

from dataproof_verifier import join_cli, join_reference, replay
from dataproof_verifier.join_model import all_join_worlds, parse_join_query, parse_join_spec
from dataproof_verifier.join_replay import validate_serialized
from dataproof_verifier.models import UnsupportedError


def test_public_right_example_replays(tmp_path: Path) -> None:
    example = Path(__file__).resolve().parents[1] / "examples/join/right_missing_match.json"
    out = tmp_path / "right"
    assert join_cli.preflight(example, True) == 0
    assert join_cli.check(example, out, True) == 0
    assert validate_serialized(out / "witness.json") == (True, "REPLAY_OK")


def _raw(kind: str = "FULL OUTER JOIN") -> dict[str, object]:
    return {
        "tables": [
            {
                "name": "orders",
                "max_rows": 2,
                "columns": [
                    {"name": "id", "type": "INTEGER", "domain": [1, 2]},
                    {"name": "k", "type": "INTEGER", "domain": [7]},
                    {"name": "region", "type": "STRING", "nullable": True, "domain": ["N"]},
                ],
            },
            {
                "name": "customers",
                "max_rows": 2,
                "columns": [
                    {"name": "k", "type": "INTEGER", "domain": [7]},
                    {"name": "region", "type": "STRING", "nullable": True, "domain": ["N"]},
                ],
            },
        ],
        "view": (
            "SELECT c.region AS region, COUNT(*) AS n, COUNT(o.id) AS matched "
            f"FROM orders AS o {kind} customers AS c "
            "ON o.k = c.k AND o.region = c.region GROUP BY c.region"
        ),
        "metric": (
            "SELECT COUNT(o.id) AS n "
            f"FROM orders AS o {kind} customers AS c "
            "ON o.k = c.k AND o.region = c.region"
        ),
    }


@pytest.mark.parametrize("kind", ["INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL OUTER JOIN"])
def test_composite_join_all_legal_worlds_agree_with_duckdb(kind: str) -> None:
    spec = parse_join_spec(_raw(kind))
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        worlds = all_join_worlds(spec)
        assert len(worlds) > 20  # includes empty, duplicates and nullable keys
        for world in worlds:
            expected_view = join_reference.evaluate_python(view, spec, world)
            expected_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            actual_view, actual_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(expected_view) == Counter(actual_view)
            assert expected_metric == actual_metric
    finally:
        con.close()


@pytest.mark.parametrize("kind", ["RIGHT JOIN", "FULL JOIN"])
def test_outer_join_positive_witness_and_replay(tmp_path: Path, kind: str) -> None:
    raw = _raw(kind)
    raw["view"] = (
        "SELECT c.k AS k, COUNT(*) AS n "
        f"FROM orders AS o {kind} customers AS c ON o.k = c.k "
        "GROUP BY c.k"
    )
    raw["metric"] = f"SELECT COUNT(o.id) AS n FROM orders AS o {kind} customers AS c ON o.k = c.k"
    # The full join can produce an extra NULL-key group from unmatched left rows.
    source = tmp_path / "spec.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    out = tmp_path / "out"
    code = join_cli.check(source, out, True)
    assert code == 0
    result = json.loads((out / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "COUNTEREXAMPLE_FOUND"
    assert validate_serialized(out / "witness.json") == (True, "REPLAY_OK")


@pytest.mark.parametrize("kind", ["RIGHT JOIN", "FULL OUTER JOIN"])
def test_empty_input_is_complete_bounded_negative(kind: str) -> None:
    raw = _raw(kind)
    for table in raw["tables"]:  # type: ignore[union-attr]
        table["max_rows"] = 0  # type: ignore[index]
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    deadline = time.monotonic() + 10
    found = join_reference.search_python(spec, view, metric, deadline)
    reference = join_reference.search_duckdb(spec, deadline)
    assert found.status == reference.status == "BOUNDED_NO_COUNTEREXAMPLE"
    assert found.worlds_checked == reference.worlds_checked == 1


def test_on_vs_where_placement_is_not_collapsed() -> None:
    raw = _raw("RIGHT JOIN")
    spec = parse_join_spec(raw)
    query = parse_join_query(spec.view_sql, spec, metric=False)
    world = (((1, 7, "N"),), ((7, "N"), (7, None)))
    all_rows = join_reference.evaluate_python(query, spec, world)
    filtered = parse_join_query(
        spec.view_sql.replace("GROUP BY c.region", "WHERE o.id IS NULL GROUP BY c.region"),
        spec,
        metric=False,
    )
    after_where = join_reference.evaluate_python(filtered, spec, world)
    assert Counter(all_rows) != Counter(after_where)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        assert Counter(all_rows) == Counter(join_reference.evaluate_duckdb(con, spec, world)[0])
    finally:
        con.close()


def test_two_sided_null_grouping_and_reversed_key_order() -> None:
    raw = _raw("FULL JOIN")
    raw["view"] = (
        "SELECT o.region AS left_region, c.region AS right_region, COUNT(*) AS n "
        "FROM orders AS o FULL JOIN customers AS c "
        "ON c.region = o.region AND c.k = o.k "
        "GROUP BY o.region, c.region"
    )
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            expected = join_reference.evaluate_python(view, spec, world)
            join_reference._load(con, spec, world)
            actual = tuple(tuple(row) for row in con.execute(spec.view_sql).fetchall())
            assert Counter(expected) == Counter(actual)
    finally:
        con.close()


@pytest.mark.parametrize(
    "on",
    [
        "o.k = c.k OR o.region = c.region",
        "o.k = c.k AND o.region = c.region AND o.id = c.k",
        "o.k = c.k AND o.k = c.k",
        "o.k = c.k AND o.id = 1",
        "o.k = o.id",
    ],
)
def test_unsupported_on_fails_closed(on: str) -> None:
    raw = _raw()
    raw["metric"] = str(raw["metric"]).replace("o.k = c.k AND o.region = c.region", on)
    spec = parse_join_spec(raw)
    with pytest.raises(UnsupportedError):
        parse_join_query(spec.metric_sql, spec, metric=True)
