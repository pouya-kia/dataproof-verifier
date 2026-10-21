"""Offline Doppelgänger check and replay commands."""

from __future__ import annotations

import json
import os
import shlex
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from dataproof_verifier.artifacts import ArtifactConflict, finish, prepare
from dataproof_verifier.doppel_model import DoppelSpec, doppel_mapping, load_doppel_spec
from dataproof_verifier.doppel_replay import (
    DoppelReplayResult,
    evaluation_mapping,
    make_replay_sql,
    rows_hash,
    validate,
    validate_serialized,
)
from dataproof_verifier.doppel_solver import search
from dataproof_verifier.models import SpecError, UnsupportedError, load_raw_spec
from dataproof_verifier.replay import serialize_rows
from dataproof_verifier.report import sha256_file, versions, write_result

EXIT_CODES = {
    "BLIND_SPOT_FOUND": 0,
    "BOUNDED_NO_BLIND_SPOT": 3,
    "INCONSISTENT_TESTS": 9,
    "INCONCLUSIVE": 8,
    "UNSUPPORTED": 5,
    "INVALID_INPUT": 6,
    "INVALID_CANDIDATE": 7,
}


def _emit(result: dict[str, Any], machine: bool) -> None:
    if machine:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        print(result["status"])
        if result.get("reason"):
            print(result["reason"])
        if result.get("witness_path"):
            print(f"witness: {result['witness_path']}")
            print(f"replay SQL: {result['replay_sql_path']}")


def _hint(path: Path) -> Path | None:
    try:
        raw = load_raw_spec(path)
    except (OSError, SpecError, UnicodeError):
        return None
    if not isinstance(raw, dict):
        return None
    value = raw.get("output_dir", "artifacts/doppelganger")
    if not isinstance(value, str) or not value:
        return None
    output = Path(value)
    return output if output.is_absolute() else (path.parent / output).resolve()


def _input_failure(directory: Path | None, result: dict[str, Any]) -> None:
    if directory is None:
        return
    try:
        prepare(directory)
        directory.joinpath("result.json").write_text(
            json.dumps({"schema_version": 1, "module": "doppelganger", **result}, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        finish(directory, success_status="BLIND_SPOT_FOUND")
    except (ArtifactConflict, OSError):
        pass  # Unsafe directories retain all existing content.


def _result(spec: DoppelSpec, path: Path, status: str, reason: str | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "module": "doppelganger",
        "status": status,
        "reason": reason,
        "input_sha256": sha256_file(path),
        "spec": doppel_mapping(spec),
        "assumptions": [
            "one synthetic table with finite INTEGER/DATE domains",
            "bag rows and declared keys/nullability",
            "each existing test must be SQL TRUE",
            "the separately supplied invariant must be SQL FALSE",
            "bounded absence is not a universal proof",
        ],
        "search": {
            "backend": "Z3 one-world finite row slots",
            "max_rows": spec.table.max_rows,
            "timeout_ms": spec.table.timeout_ms,
            "max_memory_mb": spec.table.max_memory_mb,
            "seed": spec.table.seed,
            "reduction": "lexicographic row count then declared domain codes",
        },
        "versions": versions(),
    }


def _record_evaluations(result: dict[str, Any], checked: DoppelReplayResult) -> None:
    result["test_evaluations"] = [evaluation_mapping(item) for item in checked.tests]
    assert checked.invariant is not None
    result["invariant_evaluation"] = evaluation_mapping(checked.invariant)


def check(path: Path, output: Path | None, machine: bool) -> int:
    try:
        spec = load_doppel_spec(path)
        if output is not None:
            spec = replace(spec, output_dir=output, table=replace(spec.table, output_dir=output))
    except (UnsupportedError, SpecError, OSError, UnicodeError, ValueError) as exc:
        status = "UNSUPPORTED" if isinstance(exc, UnsupportedError) else "INVALID_INPUT"
        result = {"status": status, "reason": str(exc)}
        _input_failure(output or _hint(path), result)
        _emit(result, machine)
        return EXIT_CODES[status]
    try:
        prepare(spec.output_dir)
    except (ArtifactConflict, OSError) as exc:
        _emit({"status": "INVALID_INPUT", "reason": str(exc)}, machine)
        return EXIT_CODES["INVALID_INPUT"]
    try:
        try:
            return _check_backend(spec, path, machine)
        except Exception as exc:
            result = _result(spec, path, "INCONCLUSIVE", f"backend error: {type(exc).__name__}")
            result["reason_code"] = "BACKEND_ERROR"
            write_result(spec.table, result)
            _emit(result, machine)
            return EXIT_CODES["INCONCLUSIVE"]
    finally:
        finish(spec.output_dir, success_status="BLIND_SPOT_FOUND")


def _check_backend(spec: DoppelSpec, path: Path, machine: bool) -> int:
    found = search(spec)
    result = _result(spec, path, found.status, found.reason)
    if found.rows is None:
        if found.status not in {"BOUNDED_NO_BLIND_SPOT", "INCONSISTENT_TESTS", "INCONCLUSIVE"}:
            result["status"] = "INCONCLUSIVE"
            result["reason"] = "solver returned inconsistent status without rows"
            result["reason_code"] = "SOLVER_ERROR"
        elif found.status == "INCONCLUSIVE":
            result["reason_code"] = found.reason_code or "UNKNOWN"
        write_result(spec.table, result)
        _emit(result, machine)
        if result["status"] == "INCONCLUSIVE" and result.get("reason_code") in {
            "TIMEOUT",
            "MEMORY_LIMIT",
        }:
            return 4
        return EXIT_CODES[result["status"]]
    if found.status != "CANDIDATE":
        result["status"] = "INCONCLUSIVE"
        result["reason"] = "solver returned inconsistent status with rows"
        result["reason_code"] = "SOLVER_ERROR"
        write_result(spec.table, result)
        _emit(result, machine)
        return EXIT_CODES["INCONCLUSIVE"]
    checked = validate(spec, found.rows)
    if not checked.valid:
        result["status"] = "INVALID_CANDIDATE"
        result["reason"] = checked.reason
        write_result(spec.table, result)
        _emit(result, machine)
        return EXIT_CODES["INVALID_CANDIDATE"]
    result["status"] = "BLIND_SPOT_FOUND"
    result["search"]["row_minimal_verified"] = found.row_minimal_verified
    _record_evaluations(result, checked)
    result["witness_path"] = str(spec.output_dir / "witness.json")
    result["replay_sql_path"] = str(spec.output_dir / "replay.sql")
    with tempfile.TemporaryDirectory(prefix="candidate-", dir=spec.output_dir) as staging:
        stage = Path(staging)
        witness = {
            **result,
            "rows": serialize_rows(found.rows),
            "rows_sha256": rows_hash(found.rows),
            "replay_command": (
                f"dataproof-verifier doppelganger replay {shlex.quote(result['witness_path'])}"
            ),
        }
        (stage / "witness.json").write_text(
            json.dumps(witness, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (stage / "replay.sql").write_text(make_replay_sql(spec, found.rows), encoding="utf-8")
        validated = validate_serialized(stage / "witness.json")
        if not validated.valid:
            result["status"] = "INVALID_CANDIDATE"
            result["reason"] = validated.reason
            result.pop("witness_path")
            result.pop("replay_sql_path")
            write_result(spec.table, result)
            _emit(result, machine)
            return EXIT_CODES["INVALID_CANDIDATE"]
        os.replace(stage / "witness.json", spec.output_dir / "witness.json")
        os.replace(stage / "replay.sql", spec.output_dir / "replay.sql")
    final = validate_serialized(spec.output_dir / "witness.json")
    if not final.valid:
        result["status"] = "INVALID_CANDIDATE"
        result["reason"] = final.reason
        result.pop("witness_path")
        result.pop("replay_sql_path")
        write_result(spec.table, result)
        _emit(result, machine)
        return EXIT_CODES["INVALID_CANDIDATE"]
    write_result(spec.table, result)
    _emit(result, machine)
    return EXIT_CODES["BLIND_SPOT_FOUND"]


def replay(path: Path, machine: bool) -> int:
    try:
        checked = validate_serialized(path)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        _emit({"status": "INVALID_INPUT", "reason": str(exc)}, machine)
        return EXIT_CODES["INVALID_INPUT"]
    except Exception as exc:
        _emit(
            {
                "status": "INCONCLUSIVE",
                "reason": f"backend error: {type(exc).__name__}",
                "reason_code": "BACKEND_ERROR",
            },
            machine,
        )
        return EXIT_CODES["INCONCLUSIVE"]
    status = "BLIND_SPOT_FOUND" if checked.valid else "INVALID_CANDIDATE"
    _emit({"status": status, "reason": checked.reason}, machine)
    return EXIT_CODES[status]
