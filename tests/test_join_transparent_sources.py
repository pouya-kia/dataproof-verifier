"""Projection-only CTE/derived sources retain bags and source-column semantics."""

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


def _raw() -> dict[str, object]:
    return {
        "tables": [
            {
                "name": "orders",
                "max_rows": 2,
                "columns": [
                    {"name": "id", "type": "INTEGER", "domain": [1, 2]},
                    {"name": "cid", "type": "INTEGER", "nullable": True, "domain": [1]},
                ],
            },
            {
                "name": "customers",
                "max_rows": 1,
                "columns": [
                    {"name": "cid", "type": "INTEGER", "domain": [1]},
                ],
            },
        ],
        "view": (
            "WITH base AS (SELECT id AS order_id, cid AS customer_id FROM orders), "
            "renamed AS (SELECT order_id AS key_id, customer_id FROM base) "
            "SELECT o.customer_id AS customer, COUNT(o.key_id) AS n "
            "FROM renamed AS o LEFT JOIN customers AS c ON o.customer_id = c.cid "
            "GROUP BY o.customer_id"
        ),
        "metric": (
            "SELECT COUNT(o.order_id) AS n "
            "FROM (SELECT id AS order_id, cid FROM orders) AS o "
            "LEFT JOIN customers AS c ON o.cid = c.cid"
        ),
    }


def test_nested_cte_and_derived_all_worlds_match_original_duckdb() -> None:
    spec = parse_join_spec(_raw())
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        worlds = all_join_worlds(spec)
        assert len(worlds) > 10
        for world in worlds:
            py_view = join_reference.evaluate_python(view, spec, world)
            py_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(py_view) == Counter(db_view)
            assert py_metric == db_metric
    finally:
        con.close()


def test_cte_positive_and_bounded_negative_replay(tmp_path: Path) -> None:
    raw = _raw()
    raw["view"] = (
        "WITH x AS (SELECT id, cid AS customer FROM orders) "
        "SELECT c.cid AS cid, COUNT(*) AS n "
        "FROM x AS o RIGHT JOIN customers AS c ON o.customer = c.cid GROUP BY c.cid"
    )
    raw["metric"] = (
        "SELECT COUNT(o.id) AS n FROM (SELECT id, cid FROM orders) AS o "
        "RIGHT JOIN customers AS c ON o.cid = c.cid"
    )
    source = tmp_path / "case.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    output = tmp_path / "out"
    assert join_cli.preflight(source, True) == 0
    assert join_cli.check(source, output, True) == 0
    assert validate_serialized(output / "witness.json") == (True, "REPLAY_OK")
    for table in raw["tables"]:  # type: ignore[union-attr]
        table["max_rows"] = 0  # type: ignore[index]
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    deadline = time.monotonic() + 10
    assert join_reference.search_python(spec, view, metric, deadline).status == (
        "BOUNDED_NO_COUNTEREXAMPLE"
    )
    assert join_reference.search_duckdb(spec, deadline).status == "BOUNDED_NO_COUNTEREXAMPLE"


@pytest.mark.parametrize(
    "replacement",
    [
        "SELECT DISTINCT id AS order_id, cid FROM orders",
        "SELECT id AS order_id, cid FROM orders WHERE cid = 1",
        "SELECT id + 1 AS order_id, cid FROM orders",
        "SELECT id AS order_id, cid FROM secret",
        "SELECT id AS order_id, cid FROM orders LIMIT 1",
        "SELECT id AS order_id, cid FROM orders GROUP BY id, cid",
    ],
)
def test_nontransparent_derived_source_rejected(replacement: str) -> None:
    raw = _raw()
    raw["metric"] = (
        f"SELECT COUNT(o.order_id) AS n FROM ({replacement}) AS o "
        "LEFT JOIN customers AS c ON o.cid = c.cid"
    )
    spec = parse_join_spec(raw)
    with pytest.raises(UnsupportedError):
        parse_join_query(spec.metric_sql, spec, metric=True)


@pytest.mark.parametrize(
    "sql",
    [
        "WITH RECURSIVE x AS (SELECT id, cid FROM orders) SELECT COUNT(*) AS n "
        "FROM x AS o INNER JOIN customers AS c ON o.cid = c.cid",
        "WITH x AS (SELECT id, cid FROM orders) SELECT COUNT(*) AS n "
        "FROM (SELECT id, cid FROM x WHERE cid = 1) AS o "
        "INNER JOIN customers AS c ON o.cid = c.cid",
        "SELECT COUNT(*) AS n FROM (SELECT id FROM orders) AS o "
        "INNER JOIN customers AS c ON o.cid = c.cid",
        "SELECT (SELECT COUNT(*) FROM orders) AS n FROM orders AS o "
        "INNER JOIN customers AS c ON o.cid = c.cid",
        "WITH x(ident, customer) AS (SELECT id, cid FROM orders) "
        "SELECT COUNT(*) AS n FROM x AS o INNER JOIN customers AS c ON o.customer = c.cid",
        "SELECT COUNT(*) AS n FROM (SELECT id, cid FROM orders USING SAMPLE 50 PERCENT) AS o "
        "INNER JOIN customers AS c ON o.cid = c.cid",
    ],
)
def test_unsupported_cte_and_subquery_forms_rejected(sql: str) -> None:
    raw = _raw()
    spec = parse_join_spec(raw)
    with pytest.raises(UnsupportedError):
        parse_join_query(sql, spec, metric=True)
