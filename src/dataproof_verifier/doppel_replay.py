"""Independent DuckDB checks and exact serialized replay for one synthetic dataset."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from dataproof_verifier.doppel_model import Assertion, DoppelSpec, parse_doppel_spec
from dataproof_verifier.models import Row, legal_world, serial_value
from dataproof_verifier.replay import _connection, _create_table, _insert_sql, _rows, serialize_rows


@dataclass(frozen=True)
class Evaluation:
    id: str
    value: int | None
    truth: bool | None


@dataclass(frozen=True)
class DoppelReplayResult:
    valid: bool
    tests: tuple[Evaluation, ...]
    invariant: Evaluation | None
    reason: str | None


def _evaluate(con: duckdb.DuckDBPyConnection, assertion: Assertion) -> Evaluation:
    values = con.execute(assertion.sql).fetchall()
    if len(values) != 1 or len(values[0]) != 1:
        raise ValueError("accepted aggregate did not return one scalar")
    value = values[0][0]
    if value is not None and type(value) is not int:
        raise ValueError("accepted aggregate returned a noninteger value")
    truth = con.execute(f"SELECT (? {assertion.op} ?)", [value, assertion.value]).fetchone()
    if truth is None or len(truth) != 1 or type(truth[0]) not in (bool, type(None)):
        raise ValueError("comparison did not return SQL three-valued truth")
    return Evaluation(assertion.id, value, truth[0])


def validate(spec: DoppelSpec, rows: tuple[Row, ...]) -> DoppelReplayResult:
    if not legal_world(spec.table, rows):
        return DoppelReplayResult(False, (), None, "dataset violates declared constraints")
    con = _connection()
    try:
        con.execute(_create_table(spec.table))
        for statement in _insert_sql(spec.table, rows):
            con.execute(statement)
        tests = tuple(_evaluate(con, test) for test in spec.tests)
        invariant = _evaluate(con, spec.invariant)
        if any(test.truth is not True for test in tests):
            return DoppelReplayResult(False, tests, invariant, "an existing test does not pass")
        if invariant.truth is not False:
            return DoppelReplayResult(False, tests, invariant, "invariant is not SQL FALSE")
        return DoppelReplayResult(True, tests, invariant, None)
    finally:
        con.close()


def make_replay_sql(spec: DoppelSpec, rows: tuple[Row, ...]) -> str:
    base = spec.table
    lines = [
        "-- DataProof synthetic, in-memory DuckDB Doppelganger replay",
        _create_table(base) + ";",
    ]
    lines.extend(statement + ";" for statement in _insert_sql(base, rows))
    conditions = [f'(SELECT COUNT(*) FROM "{base.table}") <= {base.max_rows}']
    conditions.extend(f"(({test.sql}) {test.op} {test.value}) IS TRUE" for test in spec.tests)
    invariant = spec.invariant
    conditions.append(f"(({invariant.sql}) {invariant.op} {invariant.value}) IS FALSE")
    lines.append(
        "SELECT CASE WHEN "
        + " AND ".join(conditions)
        + " THEN 'REPLAY_OK' ELSE error('witness assertion failed') END AS replay_status;"
    )
    return "\n".join(lines) + "\n"


def rows_hash(rows: tuple[Row, ...]) -> str:
    payload = json.dumps(serialize_rows(rows), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _recorded_evaluation(raw: Any, expected: Evaluation) -> bool:
    return (
        isinstance(raw, dict)
        and {"id", "value", "truth"} <= raw.keys()
        and raw.get("id") == expected.id
        and type(raw.get("value")) is type(expected.value)
        and raw.get("value") == expected.value
        and type(raw.get("truth")) is type(expected.truth)
        and raw.get("truth") == expected.truth
    )


def validate_serialized(path: Path) -> DoppelReplayResult:
    if path.stat().st_size > 128_000:
        raise ValueError("witness exceeds 128 KiB")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("status") != "BLIND_SPOT_FOUND":
        return DoppelReplayResult(False, (), None, "witness status is not validated")
    spec = parse_doppel_spec(data["spec"])
    rows = _rows(data["rows"], spec.table)
    if rows_hash(rows) != data.get("rows_sha256"):
        return DoppelReplayResult(False, (), None, "row hash mismatch")
    result = validate(spec, rows)
    if not result.valid:
        return result
    recorded_tests = data.get("test_evaluations")
    if (
        not isinstance(recorded_tests, list)
        or len(recorded_tests) != len(result.tests)
        or any(
            not _recorded_evaluation(recorded, actual)
            for recorded, actual in zip(recorded_tests, result.tests, strict=True)
        )
        or result.invariant is None
        or not _recorded_evaluation(data.get("invariant_evaluation"), result.invariant)
    ):
        return DoppelReplayResult(
            False, result.tests, result.invariant, "recorded outputs mismatch"
        )
    sql = path.with_name("replay.sql").read_text(encoding="utf-8")
    if sql != make_replay_sql(spec, rows):
        return DoppelReplayResult(False, result.tests, result.invariant, "replay.sql mismatch")
    con = _connection()
    try:
        replay_result = con.execute(sql).fetchall()
        if replay_result != [("REPLAY_OK",)]:
            return DoppelReplayResult(
                False, result.tests, result.invariant, "SQL replay did not pass"
            )
    except duckdb.Error as exc:
        return DoppelReplayResult(
            False, result.tests, result.invariant, f"SQL replay failed: {exc}"
        )
    finally:
        con.close()
    return result


def evaluation_mapping(evaluation: Evaluation) -> dict[str, Any]:
    return {
        "id": evaluation.id,
        "value": serial_value(evaluation.value),
        "truth": evaluation.truth,
    }
