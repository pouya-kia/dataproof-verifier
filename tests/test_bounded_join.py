"""Adversarial and differential checks for the separate tiny join workflow."""

from __future__ import annotations

import json
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from dataproof_verifier import join_cli, join_reference, replay
from dataproof_verifier.join_model import (
    all_join_worlds,
    legal_join_world,
    parse_join_query,
    parse_join_spec,
)
from dataproof_verifier.join_replay import validate_serialized
from dataproof_verifier.models import SpecError, UnsupportedError

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "join"
SELECT = "SELECT o.cid AS cid, COUNT(*) AS n"
INNER = "FROM orders AS o INNER JOIN customers AS c ON o.cid = c.cid"


def _raw(name: str = "fanout") -> dict[str, object]:
    return json.loads((EXAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def _file(tmp_path: Path, raw: dict[str, object]) -> Path:
    path = tmp_path / "input.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_positive_and_replay_explanation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _file(tmp_path, _raw())
    out = tmp_path / "run"
    assert join_cli.preflight(source, True) == 0
    assert join_cli.check(source, out, True) == 0
    result = json.loads((out / "result.json").read_text())
    assert result["status"] == "COUNTEREXAMPLE_FOUND"
    assert result["metric_values"] == [1, 2]
    assert result["view_rows"] == [[[7, 2]], [[7, 2]]]
    assert result["reference_backend"] == "duckdb_finite"
    assert validate_serialized(out / "witness.json") == (True, "REPLAY_OK")
    assert join_cli.replay_witness(out / "witness.json", True) == 0
    assert join_cli.explain_witness(out / "witness.json") == 0
    assert "NoUndo — bounded two-table INNER JOIN" in capsys.readouterr().out
    assert (out / ".dataproof-owned.json").is_file()


def test_keyed_bounded_negative_is_complete(tmp_path: Path) -> None:
    source = _file(tmp_path, _raw("keyed_negative"))
    out = tmp_path / "run"
    assert join_cli.check(source, out, True) == 3
    result = json.loads((out / "result.json").read_text())
    assert result["status"] == "BOUNDED_NO_COUNTEREXAMPLE"
    assert result["bounded_exhaustion_complete"] is True
    assert result["worlds_examined"] == result["reference_worlds_examined"] == 8
    assert not (out / "witness.json").exists()
    assert not (out / "replay.sql").exists()


def test_both_tables_empty_is_bounded_negative(tmp_path: Path) -> None:
    raw = _raw()
    for table in raw["tables"]:  # type: ignore[union-attr]
        table["max_rows"] = 0  # type: ignore[index]
    source = _file(tmp_path, raw)
    out = tmp_path / "empty"
    assert join_cli.check(source, out, True) == 3
    result = json.loads((out / "result.json").read_text())
    assert result["worlds_examined"] == result["reference_worlds_examined"] == 1
    assert not (out / "witness.json").exists()


def test_existing_output_is_never_cleaned(tmp_path: Path) -> None:
    source = _file(tmp_path, _raw())
    out = tmp_path / "run"
    out.mkdir()
    sentinel = out / "user.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    assert join_cli.check(source, out, True) == 6
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert list(out.iterdir()) == [sentinel]


def test_symlink_output_is_rejected_without_following_it(tmp_path: Path) -> None:
    source = _file(tmp_path, _raw())
    target = tmp_path / "user-dir"
    target.mkdir()
    (target / "keep.txt").write_text("safe", encoding="utf-8")
    link = tmp_path / "run-link"
    link.symlink_to(target, target_is_directory=True)
    assert join_cli.check(source, link, True) == 6
    assert (target / "keep.txt").read_text(encoding="utf-8") == "safe"
    assert not (target / "result.json").exists()


def test_preflight_rejects_unsupported_and_invalid_without_artifacts(tmp_path: Path) -> None:
    raw = _raw()
    raw["view"] = str(raw["view"]).replace("INNER JOIN", "CROSS JOIN")
    unsupported = _file(tmp_path, raw)
    assert join_cli.preflight(unsupported, True) == 5
    assert join_cli.check(unsupported, tmp_path / "unsupported-out", True) == 5
    assert not (tmp_path / "unsupported-out").exists()
    raw = _raw()
    raw["tables"][0]["columns"][0]["domain"] = [1, 1]  # type: ignore[index]
    invalid = _file(tmp_path, raw)
    assert join_cli.preflight(invalid, True) == 6
    assert join_cli.check(invalid, tmp_path / "invalid-out", True) == 6
    assert not (tmp_path / "invalid-out").exists()


def test_replay_tamper_and_sidecar_mismatch(tmp_path: Path) -> None:
    source = _file(tmp_path, _raw())
    out = tmp_path / "run"
    assert join_cli.check(source, out, True) == 0
    witness = out / "witness.json"
    result = json.loads(witness.read_text())
    result["worlds"]["D1"][0][0][0] = 2
    witness.write_text(json.dumps(result), encoding="utf-8")
    assert validate_serialized(witness)[0] is False
    assert join_cli.replay_witness(witness, True) == 7
    assert join_cli.explain_witness(witness) == 7


def test_result_sidecar_and_duplicate_json_keys_are_rejected(tmp_path: Path) -> None:
    source = _file(tmp_path, _raw())
    out = tmp_path / "run"
    assert join_cli.check(source, out, True) == 0
    result_path = out / "result.json"
    result = json.loads(result_path.read_text())
    result["metric_values"] = [1, 1]
    result_path.write_text(json.dumps(result), encoding="utf-8")
    assert validate_serialized(out / "witness.json")[0] is False
    duplicate = '{"a":1,"a":2}'
    (out / "witness.json").write_text(duplicate, encoding="utf-8")
    assert validate_serialized(out / "witness.json")[0] is False


def test_replay_sql_tamper_and_backend_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _file(tmp_path, _raw())
    out = tmp_path / "run"
    assert join_cli.check(source, out, True) == 0
    replay_sql = out / "replay.sql"
    replay_sql.write_text(replay_sql.read_text() + "-- tampered\n", encoding="utf-8")
    assert validate_serialized(out / "witness.json")[0] is False

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic replay error")

    monkeypatch.setattr(join_cli, "validate_serialized", broken)
    assert join_cli.replay_witness(out / "witness.json", True) == 8
    assert join_cli.explain_witness(out / "witness.json") == 8


def test_repeatable_witness_but_isolated_run_paths(tmp_path: Path) -> None:
    source = _file(tmp_path, _raw())
    for name in ("first", "second"):
        assert join_cli.check(source, tmp_path / name, True) == 0
    left = json.loads((tmp_path / "first" / "witness.json").read_text())
    right = json.loads((tmp_path / "second" / "witness.json").read_text())
    assert left["worlds"] == right["worlds"]
    assert left["worlds_sha256"] == right["worlds_sha256"]
    assert left["result"]["witness_path"] != right["result"]["witness_path"]


def test_trailing_comment_preserves_replay_delimiter(tmp_path: Path) -> None:
    raw = _raw()
    raw["view"] = str(raw["view"]) + " -- synthetic comment"
    source = _file(tmp_path, raw)
    out = tmp_path / "run"
    assert join_cli.check(source, out, True) == 0
    assert validate_serialized(out / "witness.json") == (True, "REPLAY_OK")


def test_reference_disagreement_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _file(tmp_path, _raw())
    monkeypatch.setattr(
        join_cli,
        "search_duckdb",
        lambda spec, deadline: join_reference.FiniteResult("BOUNDED_NO_COUNTEREXAMPLE", 18, None),
    )
    out = tmp_path / "run"
    assert join_cli.check(source, out, True) == 8
    result = json.loads((out / "result.json").read_text())
    assert result["status"] == "INCONCLUSIVE"
    assert result["reason_code"] == "REFERENCE_DISAGREEMENT"
    assert not (out / "witness.json").exists()


def test_backend_error_and_timeout_are_durable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _file(tmp_path, _raw())

    def broken(*args: object) -> None:
        raise RuntimeError("synthetic backend error")

    monkeypatch.setattr(join_cli, "search_python", broken)
    assert join_cli.check(source, tmp_path / "broken", True) == 8
    failure = json.loads((tmp_path / "broken" / "result.json").read_text())
    assert failure["reason_code"] == "BACKEND_ERROR"
    assert not (tmp_path / "broken" / "witness.json").exists()
    monkeypatch.setattr(
        join_cli,
        "search_python",
        lambda *args: join_reference.FiniteResult("INCONCLUSIVE", 2, None, "TIMEOUT"),
    )
    assert join_cli.check(source, tmp_path / "timeout", True) == 4
    timeout = json.loads((tmp_path / "timeout" / "result.json").read_text())
    assert timeout["reason_code"] == "TIMEOUT"


@pytest.mark.parametrize(
    "sql",
    [
        f"{SELECT} FROM orders AS o CROSS JOIN customers AS c ON o.cid = c.cid GROUP BY o.cid",
        f"{SELECT} FROM orders AS o JOIN customers AS c ON o.cid = c.cid GROUP BY o.cid",
        f"{SELECT} {INNER} WHERE ABS(o.id) = 1 GROUP BY o.cid",
        f"{SELECT} {INNER} OR o.id = c.cid GROUP BY o.cid",
        f"{SELECT} {INNER} GROUP BY o.cid, o.id, c.cid",
        f"{SELECT} {INNER} GROUP BY o.cid HAVING COUNT(*) > 1",
        f"{SELECT} {INNER} GROUP BY o.cid UNION SELECT 1, 2",
        f"{SELECT} {INNER} WHERE 1 = 1 GROUP BY o.cid",
        f"{SELECT} {INNER} WHERE o.id = '1' GROUP BY o.cid",
        f"{SELECT} {INNER} WHERE o.id + 1 = 2 GROUP BY o.cid",
        f"{SELECT} {INNER} WHERE o.id IN (1, 2) GROUP BY o.cid",
        f"{SELECT} {INNER} WHERE o.id = 2147483648 GROUP BY o.cid",
    ],
)
def test_unsupported_sql_fails_closed(sql: str) -> None:
    spec = parse_join_spec(_raw())
    with pytest.raises(UnsupportedError):
        parse_join_query(sql, spec, metric=False)


def test_invalid_schema_and_world_cap() -> None:
    raw = _raw()
    raw["tables"][0]["columns"][0]["name"] = "Bad Name"  # type: ignore[index]
    with pytest.raises(SpecError):
        parse_join_spec(raw)
    large = _raw()
    for table in large["tables"]:  # type: ignore[union-attr]
        table["columns"] = [  # type: ignore[index]
            {"name": name, "type": "INTEGER", "nullable": False, "domain": [1, 2, 3]}
            for name in ("x", "y", "z")
        ]
    with pytest.raises(UnsupportedError, match="bound"):
        parse_join_spec(large)
    collision = _raw()
    collision["tables"][0]["name"] = "__dataproof::d1_view"  # type: ignore[index]
    with pytest.raises(SpecError):
        parse_join_spec(collision)
    alias = _raw()
    alias["view"] = str(alias["view"]).replace("customers AS c", "customers AS o")
    with pytest.raises(UnsupportedError):
        parse_join_query(str(alias["view"]), parse_join_spec(alias), metric=False)


def test_null_group_bags_duplicates_and_aggregate_order() -> None:
    raw = _raw()
    raw = deepcopy(raw)
    raw["tables"][0]["columns"].append(  # type: ignore[index]
        {"name": "grp", "type": "INTEGER", "nullable": True, "domain": [None, 3]}
    )
    raw["tables"][0]["columns"][1]["nullable"] = True  # type: ignore[index]
    raw["tables"][0]["columns"][1]["domain"] = [7, None]  # type: ignore[index]
    raw["tables"][1]["columns"][0]["nullable"] = True  # type: ignore[index]
    raw["tables"][1]["columns"][0]["domain"] = [7, None]  # type: ignore[index]
    raw["view"] = (
        "SELECT o.grp AS grp, SUM(o.id) AS sum_ids, COUNT(DISTINCT o.id) AS distinct_ids, "
        "MIN(o.id) AS smallest, MAX(o.id) AS largest, COUNT(*) AS joined "
        "FROM orders AS o INNER JOIN customers AS c ON o.cid = c.cid GROUP BY o.grp"
    )
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    world = (((1, 7, None), (1, 7, None)), ((7,), (None,)))
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        py = join_reference.evaluate_python(view, spec, world)
        db = join_reference.evaluate_duckdb(con, spec, world)[0]
        assert Counter(py) == Counter(db) == Counter({(None, 2, 1, 1, 1, 2): 1})
    finally:
        con.close()
    empty = ((), ())
    assert join_reference.evaluate_python(view, spec, empty) == ()


def test_nullable_unique_and_date_key_semantics() -> None:
    raw = _raw()
    raw["tables"][0]["columns"][0]["nullable"] = True  # type: ignore[index]
    raw["tables"][0]["columns"][0]["domain"] = [1, None]  # type: ignore[index]
    raw["tables"][0]["unique"] = [["id"]]  # type: ignore[index]
    spec = parse_join_spec(raw)
    assert legal_join_world(spec, (((None, 7), (None, 7)), ((7,),)))
    raw = _raw()
    for table, index in ((raw["tables"][0], 1), (raw["tables"][1], 0)):  # type: ignore[index]
        table["columns"][index]["type"] = "DATE"  # type: ignore[index]
        table["columns"][index]["domain"] = ["2024-01-01"]  # type: ignore[index]
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    for world in all_join_worlds(spec):
        con = replay._connection()
        try:
            for table in spec.tables:
                con.execute(replay._create_table(table))
            py = join_reference.evaluate_python(view, spec, world)
            db = join_reference.evaluate_duckdb(con, spec, world)[0]
            assert Counter(py) == Counter(db)
            assert (
                join_reference.evaluate_python(metric, spec, world)[0][0]
                == con.execute(spec.metric_sql).fetchone()[0]
            )
        finally:
            con.close()


@settings(max_examples=30, deadline=None)
@given(
    st.lists(st.tuples(st.sampled_from([1, 2]), st.sampled_from([7, None])), max_size=2),
    st.lists(st.tuples(st.sampled_from([7, None])), max_size=2),
)
def test_python_duckdb_property(
    orders: list[tuple[int, int | None]], customers: list[tuple[int | None]]
) -> None:
    raw = _raw()
    for table, index in ((raw["tables"][0], 1), (raw["tables"][1], 0)):  # type: ignore[index]
        table["columns"][index]["nullable"] = True  # type: ignore[index]
        table["columns"][index]["domain"] = [7, None]  # type: ignore[index]
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    world = (tuple(orders), tuple(customers))
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        py_view = join_reference.evaluate_python(view, spec, world)
        py_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
        db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
        assert Counter(py_view) == Counter(db_view)
        assert py_metric == db_metric
    finally:
        con.close()


def test_complete_methods_agree_on_small_worlds() -> None:
    spec = parse_join_spec(_raw())
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    deadline = time.monotonic() + 10
    assert len(all_join_worlds(spec)) == 18
    py = join_reference.search_python(spec, view, metric, deadline)
    db = join_reference.search_duckdb(spec, deadline)
    assert py.status == db.status == "COUNTEREXAMPLE_FOUND"
    assert py.witness is not None
    assert join_reference.check_pair_duckdb(spec, py.witness)[0]
    assert join_reference.search_python(spec, view, metric, 0).status == "INCONCLUSIVE"


@pytest.mark.parametrize(
    "condition",
    [
        "o.id = 1",
        "o.id != 1",
        "o.id > 0 AND NOT (o.id < 2)",
        "o.id = 1 OR o.id IS NULL",
        "NOT (o.id = 1 OR c.cid IS NULL)",
        "o.id <= c.cid",
        "o.id IS NOT NULL",
    ],
)
def test_where_three_valued_differential_for_every_world(condition: str) -> None:
    raw = _raw()
    raw["tables"][0]["columns"][0]["nullable"] = True  # type: ignore[index]
    raw["tables"][0]["columns"][0]["domain"] = [None, 1]  # type: ignore[index]
    raw["view"] = str(raw["view"]).replace(" GROUP BY", f" WHERE {condition} GROUP BY")
    raw["metric"] = str(raw["metric"]) + f" WHERE {condition}"
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            py_view = join_reference.evaluate_python(view, spec, world)
            py_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(py_view) == Counter(db_view)
            assert py_metric == db_metric
    finally:
        con.close()


def test_two_grouping_columns_projection_order_and_nulls(tmp_path: Path) -> None:
    raw = _raw()
    raw["tables"][0]["columns"][0]["nullable"] = True  # type: ignore[index]
    raw["tables"][0]["columns"][0]["domain"] = [None, 1]  # type: ignore[index]
    raw["view"] = (
        "SELECT o.id AS order_id, o.cid AS customer_id, COUNT(*) AS joined_rows "
        "FROM orders AS o INNER JOIN customers AS c ON o.cid = c.cid "
        "GROUP BY o.cid, o.id"
    )
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            py_view = join_reference.evaluate_python(view, spec, world)
            db_view = join_reference.evaluate_duckdb(con, spec, world)[0]
            assert Counter(py_view) == Counter(db_view)
    finally:
        con.close()
    source = _file(tmp_path, raw)
    out = tmp_path / "two-keys"
    assert join_cli.check(source, out, True) == 3
    assert json.loads((out / "result.json").read_text())["bounded_exhaustion_complete"] is True


def test_filtered_join_witness_replays(tmp_path: Path) -> None:
    raw = _raw()
    raw["view"] = str(raw["view"]).replace(" GROUP BY", " WHERE o.id > 0 GROUP BY")
    raw["metric"] = str(raw["metric"]) + " WHERE o.id > 0"
    source = _file(tmp_path, raw)
    out = tmp_path / "filtered"
    assert join_cli.check(source, out, True) == 0
    assert validate_serialized(out / "witness.json") == (True, "REPLAY_OK")


def test_date_column_where_comparison_differential() -> None:
    raw = _raw()
    raw["tables"][0]["columns"].append(  # type: ignore[index]
        {"name": "day", "type": "DATE", "nullable": True, "domain": [None, "2024-01-01"]}
    )
    raw["tables"][1]["columns"].append(  # type: ignore[index]
        {"name": "day", "type": "DATE", "nullable": True, "domain": [None, "2024-01-01"]}
    )
    raw["tables"][0]["max_rows"] = 1  # type: ignore[index]
    raw["tables"][1]["max_rows"] = 1  # type: ignore[index]
    raw["view"] = str(raw["view"]).replace(" GROUP BY", " WHERE o.day = c.day GROUP BY")
    raw["metric"] = str(raw["metric"]) + " WHERE o.day = c.day"
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            py_view = join_reference.evaluate_python(view, spec, world)
            py_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(py_view) == Counter(db_view)
            assert py_metric == db_metric
    finally:
        con.close()


@pytest.mark.parametrize("join_sql", ["LEFT JOIN", "LEFT OUTER JOIN"])
def test_left_join_complete_world_differential(join_sql: str) -> None:
    raw = _raw()
    for table, index in ((raw["tables"][0], 1), (raw["tables"][1], 0)):  # type: ignore[index]
        table["columns"][index]["nullable"] = True  # type: ignore[index]
        table["columns"][index]["domain"] = [7, None]  # type: ignore[index]
    raw["view"] = (
        "SELECT c.cid AS matched_key, COUNT(*) AS rows, COUNT(c.cid) AS matched, "
        "COUNT(DISTINCT o.id) AS order_count, SUM(o.id) AS total, MIN(o.id) AS lo, "
        "MAX(o.id) AS hi FROM orders AS o INNER JOIN customers AS c "
        "ON o.cid = c.cid GROUP BY c.cid"
    )
    raw["metric"] = (
        "SELECT COUNT(c.cid) AS matched FROM orders AS o INNER JOIN customers AS c ON o.cid = c.cid"
    )
    raw["view"] = str(raw["view"]).replace("INNER JOIN", join_sql)
    raw["metric"] = str(raw["metric"]).replace("INNER JOIN", join_sql)
    spec = parse_join_spec(raw)
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    assert view.join_kind == metric.join_kind == "left"
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in all_join_worlds(spec):
            py_view = join_reference.evaluate_python(view, spec, world)
            py_metric = join_reference.evaluate_python(metric, spec, world)[0][0]
            db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(py_view) == Counter(db_view)
            assert py_metric == db_metric
    finally:
        con.close()


def test_left_join_where_filters_null_extended_rows() -> None:
    raw = _raw()
    raw["view"] = str(raw["view"]).replace("INNER JOIN", "LEFT JOIN")
    spec = parse_join_spec(raw)
    world = (((1, 7),), ())
    without_filter = parse_join_query(spec.view_sql, spec, metric=False)
    with_filter = parse_join_query(
        spec.view_sql.replace(" GROUP BY", " WHERE c.cid IS NOT NULL GROUP BY"),
        spec,
        metric=False,
    )
    assert join_reference.evaluate_python(without_filter, spec, world) == ((7, 1),)
    assert join_reference.evaluate_python(with_filter, spec, world) == ()
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        assert Counter(join_reference.evaluate_duckdb(con, spec, world)[0]) == Counter({(7, 1): 1})
        assert (
            con.execute(
                spec.view_sql.replace(" GROUP BY", " WHERE c.cid IS NOT NULL GROUP BY")
            ).fetchall()
            == []
        )
    finally:
        con.close()


def test_left_join_positive_replay_and_empty_negative(tmp_path: Path) -> None:
    raw = _raw()
    raw["view"] = str(raw["view"]).replace("INNER JOIN", "LEFT JOIN")
    raw["metric"] = (
        "SELECT COUNT(c.cid) AS matched FROM orders AS o LEFT JOIN customers AS c ON o.cid = c.cid"
    )
    source = _file(tmp_path, raw)
    out = tmp_path / "left-positive"
    assert join_cli.check(source, out, True) == 0
    assert validate_serialized(out / "witness.json") == (True, "REPLAY_OK")
    result = json.loads((out / "result.json").read_text())
    assert result["metric_values"] == [0, 1]
    for table in raw["tables"]:  # type: ignore[union-attr]
        table["max_rows"] = 0  # type: ignore[index]
    empty_source = tmp_path / "empty.json"
    empty_source.write_text(json.dumps(raw))
    empty_out = tmp_path / "left-empty"
    assert join_cli.check(empty_source, empty_out, True) == 3
    assert json.loads((empty_out / "result.json").read_text())["bounded_exhaustion_complete"]


def test_compound_left_on_is_rejected_even_with_supported_where() -> None:
    raw = _raw()
    raw["view"] = str(raw["view"]).replace(
        "INNER JOIN customers AS c ON o.cid = c.cid",
        "LEFT JOIN customers AS c ON o.cid = c.cid AND o.id = 1",
    )
    spec = parse_join_spec(raw)
    with pytest.raises(UnsupportedError, match="JOIN ON"):
        parse_join_query(spec.view_sql, spec, metric=False)
