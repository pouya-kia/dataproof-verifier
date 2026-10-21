"""Independent DuckDB replay and fail-closed serialized join evidence."""

from __future__ import annotations

import hashlib
import json
import stat
from collections import Counter
from pathlib import Path
from typing import Any

from dataproof_verifier import replay
from dataproof_verifier.artifacts import MARKER
from dataproof_verifier.join_model import (
    JoinSpec,
    World,
    canonical_spec,
    legal_join_world,
    parse_join_query,
    parse_join_spec,
    serialize_world,
)
from dataproof_verifier.join_reference import check_pair_duckdb
from dataproof_verifier.models import serial_value


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _internal(label: str, kind: str) -> str:
    # A colon cannot occur in the admitted source identifier grammar.
    return f'"__dataproof::{label}_{kind}"'


def make_replay_sql(spec: JoinSpec, pair: tuple[World, World]) -> str:
    kinds = {
        parse_join_query(sql, spec, metric=is_metric).join_kind
        for sql, is_metric in ((spec.view_sql, False), (spec.metric_sql, True))
    }
    label = "INNER JOIN" if kinds == {"inner"} else "INNER/LEFT JOIN"
    lines = [f"-- DataProof bounded two-table {label} replay"]
    lines.extend(replay._create_table(table) + ";" for table in spec.tables)
    for label, world in (("d1", pair[0]), ("d2", pair[1])):
        for table, rows in zip(spec.tables, world, strict=True):
            lines.append(f'DELETE FROM "{table.table}";')
            lines.extend(statement + ";" for statement in replay._insert_sql(table, rows))
            lines.append(
                f"SELECT CASE WHEN COUNT(*) <= {table.max_rows} THEN 1 "
                f"ELSE error('row bound violated') END FROM \"{table.table}\";"
            )
        # Put the delimiter on a new line so an admitted trailing SQL comment
        # cannot swallow it in the exported replay script.
        lines.append(f"CREATE TABLE {_internal(label, 'view')} AS {spec.view_sql}\n;")
        lines.append(f"CREATE TABLE {_internal(label, 'metric')} AS {spec.metric_sql}\n;")
    left_view, right_view = _internal("d1", "view"), _internal("d2", "view")
    left_metric, right_metric = _internal("d1", "metric"), _internal("d2", "metric")
    lines.append(
        "SELECT CASE WHEN (SELECT COUNT(*) FROM ("
        f"(SELECT * FROM {left_view} EXCEPT ALL SELECT * FROM {right_view}) "
        f"UNION ALL (SELECT * FROM {right_view} EXCEPT ALL SELECT * FROM {left_view})"
        ")) = 0 AND "
        f"(SELECT * FROM {left_metric}) IS DISTINCT FROM (SELECT * FROM {right_metric}) "
        "THEN 'REPLAY_OK' ELSE error('witness assertion failed') END AS replay_status;"
    )
    return "\n".join(lines) + "\n"


def _read_regular(path: Path) -> bytes:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("evidence must be a regular file")
    if path.stat().st_size > 128_000:
        raise ValueError("evidence exceeds 128 KiB")
    return path.read_bytes()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate evidence key")
        result[key] = value
    return result


def _ownership(path: Path) -> bool:
    marker = path.with_name(MARKER)
    if not marker.exists() and not marker.is_symlink():
        return True  # Initial staging validation precedes finish().
    data = json.loads(_read_regular(marker), object_pairs_hook=_unique_pairs)
    if not isinstance(data, dict):
        return False
    files = data.get("files")
    if data.get("schema_version") != 1 or not isinstance(files, dict):
        return False
    for name in ("witness.json", "result.json", "replay.sql"):
        candidate = path.with_name(name)
        if files.get(name) != hashlib.sha256(_read_regular(candidate)).hexdigest():
            return False
    return True


def _world(raw: Any, spec: JoinSpec) -> World:
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError("world must contain two table bags")
    world = (replay._rows(raw[0], spec.tables[0]), replay._rows(raw[1], spec.tables[1]))
    if not legal_join_world(spec, world):
        raise ValueError("world violates declared constraints")
    return world


def _serial_views(views: tuple[tuple[tuple[Any, ...], ...], ...]) -> list[list[list[Any]]]:
    return [[[serial_value(value) for value in row] for row in bag] for bag in views]


def validate_serialized(path: Path, *, require_ownership: bool = True) -> tuple[bool, str]:
    """Reparse, reexecute, and compare every owned sidecar; never trust status alone."""
    try:
        witness = json.loads(_read_regular(path), object_pairs_hook=_unique_pairs)
        result = json.loads(
            _read_regular(path.with_name("result.json")), object_pairs_hook=_unique_pairs
        )
        replay_sql = _read_regular(path.with_name("replay.sql")).decode("utf-8")
        if require_ownership and not _ownership(path):
            return False, "artifact ownership mismatch"
        if not isinstance(witness, dict) or not isinstance(result, dict):
            return False, "invalid evidence object"
        if (
            witness.get("module") != "join-no-undo"
            or witness.get("status") != "COUNTEREXAMPLE_FOUND"
        ):
            return False, "wrong witness module or status"
        if witness.get("result") != result or result.get("status") != "COUNTEREXAMPLE_FOUND":
            return False, "result/witness mismatch"
        if witness.get("input_sha256") != result.get("input_sha256"):
            return False, "input digest mismatch"
        raw_spec = witness.get("spec")
        spec = parse_join_spec(raw_spec)
        parse_join_query(spec.view_sql, spec, metric=False)
        parse_join_query(spec.metric_sql, spec, metric=True)
        if raw_spec != canonical_spec(spec) or witness.get("spec_sha256") != digest(raw_spec):
            return False, "specification hash mismatch"
        worlds = witness.get("worlds")
        if not isinstance(worlds, dict) or set(worlds) != {"D1", "D2"}:
            return False, "invalid world identities"
        if witness.get("worlds_sha256") != digest(worlds):
            return False, "world hash mismatch"
        pair = (_world(worlds["D1"], spec), _world(worlds["D2"], spec))
        valid, views, metrics = check_pair_duckdb(spec, pair)
        if not valid:
            return False, "DuckDB does not confirm the witness"
        recorded = witness.get("view_rows")
        expected = _serial_views(views)
        if (
            not isinstance(recorded, list)
            or len(recorded) != 2
            or any(
                Counter(map(tuple, actual)) != Counter(map(tuple, target))
                for actual, target in zip(recorded, expected, strict=True)
            )
            or witness.get("metric_values") != [serial_value(value) for value in metrics]
        ):
            return False, "recorded SQL outputs mismatch"
        if witness.get("replay_sql_sha256") != hashlib.sha256(replay_sql.encode()).hexdigest():
            return False, "replay SQL hash mismatch"
        if replay_sql != make_replay_sql(spec, pair):
            return False, "replay SQL content mismatch"
        con = replay._connection()
        try:
            if con.execute(replay_sql).fetchall() != [("REPLAY_OK",)]:
                return False, "replay SQL did not pass"
        finally:
            con.close()
        if worlds != {"D1": serialize_world(pair[0]), "D2": serialize_world(pair[1])}:
            return False, "serialized world normalization mismatch"
        return True, "REPLAY_OK"
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return False, f"invalid evidence: {type(exc).__name__}"
