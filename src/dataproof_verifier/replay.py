"""Independent DuckDB execution of candidate worlds and serialized replay SQL."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from dataproof_verifier.models import Row, Spec, Value, legal_world, parse_spec, serial_value
from dataproof_verifier.parser import parse_query


@dataclass(frozen=True)
class ReplayResult:
    valid: bool
    views: tuple[tuple[tuple[Any, ...], ...], tuple[tuple[Any, ...], ...]]
    metrics: tuple[Any, Any]
    reason: str | None


def _connection() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:", config={"enable_external_access": "false"})


def _quoted(name: str) -> str:
    return f'"{name}"'


def _replay_table(label: str, kind: str) -> str:
    # ':' is excluded by the input identifier grammar, so a legal source table
    # cannot collide with an internal replay table in the same schema.
    return _quoted(f"__dataproof::{label}_{kind}")


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, date):
        return f"DATE '{value.isoformat()}'"
    if type(value) is int:
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise ValueError("unsupported synthetic value")


def _create_table(spec: Spec) -> str:
    columns: list[str] = []
    for col in spec.columns:
        nonnull = [v for v in col.domain if v is not None]
        domain = (
            f"{_quoted(col.name)} IN ({', '.join(_literal(x) for x in nonnull)})"
            if nonnull
            else "FALSE"
        )
        if col.nullable:
            domain = f"({_quoted(col.name)} IS NULL OR {domain})"
        columns.append(
            f"{_quoted(col.name)} {'VARCHAR' if col.type == 'STRING' else col.type} "
            f"{'' if col.nullable else 'NOT NULL '}CHECK ({domain})"
        )
    if spec.primary_key:
        columns.append(f"PRIMARY KEY ({', '.join(_quoted(x) for x in spec.primary_key)})")
    for key in spec.unique:
        columns.append(f"UNIQUE ({', '.join(_quoted(x) for x in key)})")
    return f"CREATE TABLE {_quoted(spec.table)} ({', '.join(columns)})"


def _insert_sql(spec: Spec, rows: tuple[Row, ...]) -> list[str]:
    return [
        f"INSERT INTO {_quoted(spec.table)} VALUES ({', '.join(_literal(x) for x in row)})"
        for row in rows
    ]


def _load(con: duckdb.DuckDBPyConnection, spec: Spec, rows: tuple[Row, ...]) -> None:
    con.execute(f"DELETE FROM {_quoted(spec.table)}")
    for sql in _insert_sql(spec, rows):
        con.execute(sql)


def validate(spec: Spec, left: tuple[Row, ...], right: tuple[Row, ...]) -> ReplayResult:
    if not legal_world(spec, left) or not legal_world(spec, right):
        return ReplayResult(False, ((), ()), (None, None), "world violates declared constraints")
    # Parse again at the independent execution boundary, then execute the source SQL.
    parse_query(spec.views[0], spec, metric=False)
    parse_query(spec.metric, spec, metric=True)
    con = _connection()
    try:
        con.execute(_create_table(spec))
        results: list[tuple[tuple[tuple[Any, ...], ...], Any]] = []
        for rows in (left, right):
            _load(con, spec, rows)
            view = tuple(tuple(row) for row in con.execute(spec.views[0]).fetchall())
            metric_rows = con.execute(spec.metric).fetchall()
            if len(metric_rows) != 1 or len(metric_rows[0]) != 1:
                return ReplayResult(False, ((), ()), (None, None), "metric is not scalar")
            results.append((view, metric_rows[0][0]))
        views = (results[0][0], results[1][0])
        metrics = (results[0][1], results[1][1])
        if Counter(views[0]) != Counter(views[1]):
            return ReplayResult(False, views, metrics, "retained views differ")
        if metrics[0] == metrics[1]:
            return ReplayResult(False, views, metrics, "metrics do not differ")
        return ReplayResult(True, views, metrics, None)
    except duckdb.Error as exc:
        return ReplayResult(False, ((), ()), (None, None), f"DuckDB error: {exc}")
    finally:
        con.close()


def make_replay_sql(spec: Spec, left: tuple[Row, ...], right: tuple[Row, ...]) -> str:
    lines = ["-- DataProof synthetic, in-memory DuckDB replay", _create_table(spec) + ";"]
    for label, rows in (("d1", left), ("d2", right)):
        lines.append(f"DELETE FROM {_quoted(spec.table)};")
        lines.extend(sql + ";" for sql in _insert_sql(spec, rows))
        lines.append(
            f"SELECT CASE WHEN COUNT(*) <= {spec.max_rows} THEN 1 "
            f"ELSE error('row bound violated') END FROM {_quoted(spec.table)};"
        )
        lines.append(f"CREATE TABLE {_replay_table(label, 'view')} AS {spec.views[0]};")
        lines.append(f"CREATE TABLE {_replay_table(label, 'metric')} AS {spec.metric};")
    d1_view = _replay_table("d1", "view")
    d2_view = _replay_table("d2", "view")
    d1_metric = _replay_table("d1", "metric")
    d2_metric = _replay_table("d2", "metric")
    lines.append(
        "SELECT CASE WHEN "
        "(SELECT COUNT(*) FROM ("
        f"(SELECT * FROM {d1_view} EXCEPT ALL SELECT * FROM {d2_view}) "
        f"UNION ALL (SELECT * FROM {d2_view} EXCEPT ALL SELECT * FROM {d1_view})"
        ")) = 0 AND "
        f"(SELECT * FROM {d1_metric}) IS DISTINCT FROM (SELECT * FROM {d2_metric}) "
        "THEN 'REPLAY_OK' ELSE error('witness assertion failed') END AS replay_status;"
    )
    return "\n".join(lines) + "\n"


def _rows(raw: Any, spec: Spec) -> tuple[Row, ...]:
    if not isinstance(raw, list):
        raise ValueError("world rows must be a list")
    rows: list[Row] = []
    for item in raw:
        if not isinstance(item, list) or len(item) != len(spec.columns):
            raise ValueError("invalid serialized row")
        converted: list[Value] = []
        for value, col in zip(item, spec.columns, strict=True):
            if value is None:
                converted.append(None)
            elif col.type == "DATE" and isinstance(value, str):
                converted.append(date.fromisoformat(value))
            elif col.type == "INTEGER" and type(value) is int:
                converted.append(value)
            elif col.type == "STRING" and isinstance(value, str):
                converted.append(value)
            else:
                raise ValueError("invalid serialized value type")
        rows.append(tuple(converted))
    return tuple(rows)


def validate_serialized(path: Path) -> ReplayResult:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "COUNTEREXAMPLE_FOUND":
        return ReplayResult(False, ((), ()), (None, None), "witness status is not validated")
    canonical = json.dumps(data["worlds"], sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(canonical).hexdigest() != data.get("worlds_sha256"):
        return ReplayResult(False, ((), ()), (None, None), "world hash mismatch")
    spec = parse_spec(data["spec"])
    left = _rows(data["worlds"]["D1"], spec)
    right = _rows(data["worlds"]["D2"], spec)
    result = validate(spec, left, right)
    if not result.valid:
        return result
    expected_views = [
        [[serial_value(value) for value in row] for row in view_rows] for view_rows in result.views
    ]
    recorded_views = data.get("view_rows")
    views_match = (
        isinstance(recorded_views, list)
        and len(recorded_views) == 2
        and all(
            Counter(map(tuple, recorded)) == Counter(map(tuple, expected))
            for recorded, expected in zip(recorded_views, expected_views, strict=True)
        )
    )
    if not views_match or data.get("metric_values") != list(result.metrics):
        return ReplayResult(False, result.views, result.metrics, "recorded SQL outputs mismatch")
    replay_text = path.with_name("replay.sql").read_text(encoding="utf-8")
    if replay_text != make_replay_sql(spec, left, right):
        return ReplayResult(False, result.views, result.metrics, "replay.sql mismatch")
    con = _connection()
    try:
        rows = con.execute(replay_text).fetchall()
        if rows != [("REPLAY_OK",)]:
            return ReplayResult(False, result.views, result.metrics, "SQL replay did not pass")
    except duckdb.Error as exc:
        return ReplayResult(False, result.views, result.metrics, f"SQL replay failed: {exc}")
    finally:
        con.close()
    return result


def serialize_rows(rows: tuple[Row, ...]) -> list[list[int | str | None]]:
    return [[serial_value(value) for value in row] for row in rows]
