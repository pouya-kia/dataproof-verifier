"""Isolated CLI workflow for complete tiny two-table equijoin checks."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from dataproof_verifier.artifacts import ArtifactConflict, finish, prepare
from dataproof_verifier.join_model import (
    JoinSpec,
    analytical_world_bound,
    canonical_spec,
    parse_join_query,
    parse_join_spec,
    serialize_world,
)
from dataproof_verifier.join_reference import check_pair_duckdb, search_duckdb, search_python
from dataproof_verifier.join_replay import digest, make_replay_sql, validate_serialized
from dataproof_verifier.models import SpecError, UnsupportedError, load_raw_spec, serial_value
from dataproof_verifier.status import EXIT_CODES


def _emit(result: dict[str, Any], machine: bool) -> None:
    if machine:
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        print(result["status"])
        if result.get("reason"):
            print(result["reason"])
        if result.get("witness_path"):
            print(f"witness: {result['witness_path']}")


def _load(path: Path) -> JoinSpec:
    spec = parse_join_spec(load_raw_spec(path), path)
    parse_join_query(spec.view_sql, spec, metric=False)
    parse_join_query(spec.metric_sql, spec, metric=True)
    return spec


def _fragment_limits() -> dict[str, Any]:
    return {
        "tables": 2,
        "rows_per_table": 2,
        "columns_per_table": 3,
        "effective_values_per_column": 3,
        "analytical_combined_worlds": 500,
        "string_collation": "ASCII_BINARY_CASE_SENSITIVE",
        "string_length": [1, 32],
        "integer_arithmetic": "ADD_SUB_SIGNED_32_BIT_NO_POSSIBLE_OVERFLOW",
        "case_when_arms": 3,
        "join_forms": ["INNER", "LEFT", "RIGHT", "FULL"],
        "equality_keys_per_join": [1, 2],
    }


def preflight(path: Path, machine: bool) -> int:
    try:
        spec = _load(path)
        result = {
            "status": "ELIGIBLE",
            "backend": "complete_python_finite_with_duckdb_reference",
            "analytical_world_bound": analytical_world_bound(spec),
            "max_rows_per_table": [table.max_rows for table in spec.tables],
            "fragment_limits": _fragment_limits(),
        }
        code = 0
    except UnsupportedError as exc:
        result = {"status": "UNSUPPORTED", "reason": str(exc)}
        code = EXIT_CODES["UNSUPPORTED"]
    except (SpecError, OSError, ValueError) as exc:
        result = {"status": "INVALID_INPUT", "reason": str(exc)}
        code = EXIT_CODES["INVALID_INPUT"]
    _emit(result, machine)
    return code


def _write_result(directory: Path, result: dict[str, Any]) -> None:
    (directory / "result.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _serial_views(views: tuple[tuple[tuple[Any, ...], ...], ...]) -> list[list[list[Any]]]:
    return [[[serial_value(value) for value in row] for row in bag] for bag in views]


def _run(spec: JoinSpec, path: Path, result: dict[str, Any]) -> tuple[dict[str, Any], int]:
    deadline = time.monotonic() + spec.timeout_ms / 1000
    view = parse_join_query(spec.view_sql, spec, metric=False)
    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    candidate = search_python(spec, view, metric, deadline)
    result["worlds_examined"] = candidate.worlds_checked
    if candidate.status == "INCONCLUSIVE":
        result.update(
            status="INCONCLUSIVE", reason_code="TIMEOUT", reason="finite search timed out"
        )
        return result, EXIT_CODES["INCONCLUSIVE"]
    reference = search_duckdb(spec, deadline)
    result["reference_worlds_examined"] = reference.worlds_checked
    if reference.status == "INCONCLUSIVE":
        result.update(
            status="INCONCLUSIVE", reason_code="TIMEOUT", reason="DuckDB reference timed out"
        )
        return result, EXIT_CODES["INCONCLUSIVE"]
    if candidate.status != reference.status:
        result.update(
            status="INCONCLUSIVE",
            reason_code="REFERENCE_DISAGREEMENT",
            reason=f"Python {candidate.status}; DuckDB {reference.status}",
        )
        return result, EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    if candidate.witness is None:
        if candidate.status != "BOUNDED_NO_COUNTEREXAMPLE" or reference.witness is not None:
            result.update(status="INCONCLUSIVE", reason_code="INCONSISTENT_BACKEND")
            return result, EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
        result.update(status="BOUNDED_NO_COUNTEREXAMPLE", bounded_exhaustion_complete=True)
        return result, EXIT_CODES["BOUNDED_NO_COUNTEREXAMPLE"]
    if reference.witness is None:
        result.update(status="INCONCLUSIVE", reason_code="INCONSISTENT_REFERENCE")
        return result, EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    valid, views, metrics = check_pair_duckdb(spec, candidate.witness)
    if not valid:
        result.update(
            status="INVALID_CANDIDATE", reason="candidate failed independent DuckDB check"
        )
        return result, EXIT_CODES["INVALID_CANDIDATE"]
    result.update(
        status="COUNTEREXAMPLE_FOUND",
        bounded_exhaustion_complete=False,
        witness_path=str(spec.output_dir / "witness.json"),
        replay_sql_path=str(spec.output_dir / "replay.sql"),
        view_rows=_serial_views(views),
        metric_values=[serial_value(value) for value in metrics],
    )
    pair = candidate.witness
    if hashlib.sha256(path.read_bytes()).hexdigest() != result["input_sha256"]:
        raise ValueError("input changed during this run")
    worlds = {"D1": serialize_world(pair[0]), "D2": serialize_world(pair[1])}
    spec_raw = canonical_spec(spec)
    sql = make_replay_sql(spec, pair)
    witness = {
        "schema_version": 1,
        "module": "join-no-undo",
        "status": "COUNTEREXAMPLE_FOUND",
        "input_sha256": result["input_sha256"],
        "spec": spec_raw,
        "spec_sha256": digest(spec_raw),
        "worlds": worlds,
        "worlds_sha256": digest(worlds),
        "view_rows": result["view_rows"],
        "metric_values": result["metric_values"],
        "replay_sql_sha256": hashlib.sha256(sql.encode()).hexdigest(),
        "result": result,
    }
    (spec.output_dir / "replay.sql").write_text(sql, encoding="utf-8")
    (spec.output_dir / "witness.json").write_text(
        json.dumps(witness, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_result(spec.output_dir, result)
    validated, reason = validate_serialized(
        spec.output_dir / "witness.json", require_ownership=False
    )
    if not validated:
        result.pop("witness_path", None)
        result.pop("replay_sql_path", None)
        result.update(status="INVALID_CANDIDATE", reason=reason)
        return result, EXIT_CODES["INVALID_CANDIDATE"]
    return result, EXIT_CODES["COUNTEREXAMPLE_FOUND"]


def check(path: Path, output: Path | None, machine: bool) -> int:
    try:
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        spec = _load(path)
        input_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if before != input_digest:
            raise SpecError("input changed during validation")
        if output is not None:
            spec = replace(spec, output_dir=output.absolute())
    except UnsupportedError as exc:
        _emit({"status": "UNSUPPORTED", "reason": str(exc)}, machine)
        return EXIT_CODES["UNSUPPORTED"]
    except (SpecError, OSError, ValueError) as exc:
        _emit({"status": "INVALID_INPUT", "reason": str(exc)}, machine)
        return EXIT_CODES["INVALID_INPUT"]
    if spec.output_dir.exists() or spec.output_dir.is_symlink():
        _emit({"status": "INVALID_INPUT", "reason": "join output directory must be new"}, machine)
        return EXIT_CODES["INVALID_INPUT"]
    try:
        prepare(spec.output_dir)
    except (ArtifactConflict, OSError) as exc:
        _emit({"status": "INVALID_INPUT", "reason": str(exc)}, machine)
        return EXIT_CODES["INVALID_INPUT"]
    result: dict[str, Any] = {
        "schema_version": 1,
        "module": "join-no-undo",
        "backend": "complete_python_finite",
        "reference_backend": "duckdb_finite",
        "status": "INCONCLUSIVE",
        "analytical_world_bound": analytical_world_bound(spec),
        "fragment_limits": _fragment_limits(),
        "input_sha256": input_digest,
        "result_path": str(spec.output_dir / "result.json"),
    }
    try:
        result, code = _run(spec, path, result)
    except Exception as exc:
        result.pop("witness_path", None)
        result.pop("replay_sql_path", None)
        result.update(
            status="INCONCLUSIVE",
            reason_code="BACKEND_ERROR",
            reason=f"backend error: {type(exc).__name__}",
        )
        code = EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    try:
        _write_result(spec.output_dir, result)
        finish(spec.output_dir)
    except (ArtifactConflict, OSError, ValueError) as exc:
        _emit(
            {
                "status": "INCONCLUSIVE",
                "reason_code": "ARTIFACT_ERROR",
                "reason": type(exc).__name__,
            },
            machine,
        )
        return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    if code == EXIT_CODES["COUNTEREXAMPLE_FOUND"]:
        try:
            validated, reason = validate_serialized(spec.output_dir / "witness.json")
        except Exception as exc:
            validated, reason = False, f"final replay error: {type(exc).__name__}"
        if not validated:
            try:
                prepare(spec.output_dir)
            except (ArtifactConflict, OSError):
                _emit({"status": "INCONCLUSIVE", "reason_code": "ARTIFACT_CONFLICT"}, machine)
                return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
            result.pop("witness_path", None)
            result.pop("replay_sql_path", None)
            result.update(status="INVALID_CANDIDATE", reason=reason)
            try:
                _write_result(spec.output_dir, result)
                finish(spec.output_dir)
            except (ArtifactConflict, OSError, ValueError):
                _emit({"status": "INCONCLUSIVE", "reason_code": "ARTIFACT_ERROR"}, machine)
                return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
            code = EXIT_CODES["INVALID_CANDIDATE"]
    _emit(result, machine)
    return code


def replay_witness(path: Path, machine: bool) -> int:
    try:
        valid, reason = validate_serialized(path)
    except Exception as exc:
        _emit(
            {
                "status": "INCONCLUSIVE",
                "reason_code": "BACKEND_ERROR",
                "reason": type(exc).__name__,
            },
            machine,
        )
        return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    status = "COUNTEREXAMPLE_FOUND" if valid else "INVALID_CANDIDATE"
    _emit({"status": status, "reason": reason}, machine)
    return EXIT_CODES[status]


def explain_witness(path: Path) -> int:
    try:
        valid, reason = validate_serialized(path)
    except Exception as exc:
        print(f"EXPLANATION_UNAVAILABLE: backend error ({type(exc).__name__})")
        return EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    if not valid:
        print(f"EXPLANATION_UNAVAILABLE: {reason}")
        return EXIT_CODES["INVALID_CANDIDATE"]
    evidence = json.loads(path.read_text(encoding="utf-8"))
    spec = parse_join_spec(evidence["spec"])
    view = parse_join_query(spec.view_sql, spec, metric=False)

    def bag_lines(rows: list[list[Any]], names: tuple[str, ...]) -> list[str]:
        counts = Counter(tuple(row) for row in rows)
        lines = ["  columns: " + ", ".join(names)]
        if not counts:
            return lines + ["  (empty bag)"]
        for row in sorted(counts, key=lambda item: json.dumps(item)):
            cells = ", ".join("NULL" if value is None else json.dumps(value) for value in row)
            lines.append(f"  ({cells}) x {counts[row]}")
        return lines

    metric = parse_join_query(spec.metric_sql, spec, metric=True)
    label = (
        "INNER JOIN"
        if view.join_kind == metric.join_kind == "inner"
        else "INNER/LEFT/RIGHT/FULL JOIN"
    )
    print(f"NoUndo — bounded two-table {label} counterexample")
    for index, label in enumerate(("D1", "D2")):
        print(f"{label}:")
        for table, rows in zip(spec.tables, evidence["worlds"][label], strict=True):
            print(f"  {table.table}:")
            print("\n".join(bag_lines(rows, table.names)))
        print(f"Retained view V({label}):")
        print(
            "\n".join(
                bag_lines(
                    evidence["view_rows"][index], tuple(item.name for item in view.projections)
                )
            )
        )
    print("The retained view bags are equal, including duplicate multiplicity.")
    print(f"Different scalar KPI values: {evidence['metric_values']}")
    print("Finite scope only; source and join duplicates are bags; no universal claim.")
    print(f"Replay: dataproof-verifier join replay {path}")
    return 0
