"""Read-only, replay-verified terminal explanations of positive witnesses."""

from __future__ import annotations

import hashlib
import json
import shlex
import stat
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from dataproof_verifier import doppel_replay, replay
from dataproof_verifier.artifacts import MARKER
from dataproof_verifier.doppel_model import parse_doppel_spec
from dataproof_verifier.models import Spec, parse_spec
from dataproof_verifier.parser import parse_query
from dataproof_verifier.status import EXIT_CODES


class ExplanationError(ValueError):
    """Evidence cannot support a trustworthy explanation."""

    def __init__(self, message: str, code: int = EXIT_CODES["INVALID_INPUT"]) -> None:
        super().__init__(message)
        self.code = code


def _regular(path: Path) -> None:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ExplanationError(f"not a regular evidence file: {path}")


def _json_object(path: Path) -> dict[str, Any]:
    _regular(path)
    if path.stat().st_size > 128_000:
        raise ExplanationError(f"evidence file exceeds 128 KiB: {path}")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ExplanationError(f"duplicate evidence key: {key}")
            result[key] = value
        return result

    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    if not isinstance(data, dict):
        raise ExplanationError(f"invalid evidence object: {path}")
    return data


def _sidecars(path: Path, witness: dict[str, Any], module: str) -> None:
    result_path = path.with_name("result.json")
    replay_path = path.with_name("replay.sql")
    result = _json_object(result_path)
    _regular(replay_path)
    if replay_path.stat().st_size > 128_000:
        raise ExplanationError("replay.sql exceeds 128 KiB")
    extras = (
        {"replay_command", "rows", "rows_sha256"}
        if module == "doppelganger"
        else {"replay_command", "worlds", "worlds_sha256"}
    )
    if result != {key: value for key, value in witness.items() if key not in extras}:
        raise ExplanationError("result.json does not match the witness from this run")
    marker_path = path.with_name(MARKER)
    if marker_path.exists() or marker_path.is_symlink():
        marker = _json_object(marker_path)
        files = marker.get("files")
        if (
            type(marker.get("schema_version")) is not int
            or marker["schema_version"] != 1
            or not isinstance(files, dict)
        ):
            raise ExplanationError("invalid artifact ownership record")
        for name, evidence in (
            ("witness.json", path),
            ("result.json", result_path),
            ("replay.sql", replay_path),
        ):
            digest = files.get(name)
            if (
                not isinstance(digest, str)
                or hashlib.sha256(evidence.read_bytes()).hexdigest() != digest
            ):
                raise ExplanationError(f"artifact ownership mismatch: {name}")


def _cell(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, date):
        return f"DATE {json.dumps(value.isoformat())}"
    if type(value) is int:
        return str(value)
    # Keep readable Unicode, but escape controls, bidi formatting and line separators.
    quoted = json.dumps(value, ensure_ascii=False)
    return "".join(
        json.dumps(char, ensure_ascii=True)[1:-1]
        if unicodedata.category(char) in {"Cc", "Cf", "Zl", "Zp"}
        else char
        for char in quoted
    )


def _bag(rows: tuple[tuple[Any, ...], ...], names: tuple[str, ...]) -> list[str]:
    counts = Counter(rows)
    lines = ["  columns: " + ", ".join(names)]
    if not counts:
        return lines + ["  (empty bag)"]
    for row in sorted(counts, key=lambda item: json.dumps([_cell(v) for v in item])):
        lines.append("  (" + ", ".join(_cell(value) for value in row) + f") x {counts[row]}")
    return lines


def _scope(spec: Spec) -> str:
    domains = ", ".join(f"{col.name}={len(col.domain)}" for col in spec.columns)
    columns = f"{len(spec.columns)} column{'s' if len(spec.columns) != 1 else ''}"
    return (
        f"one synthetic table; 0..{spec.max_rows} rows per dataset; "
        f"{columns}; declared domain sizes: {domains}; "
        "declared keys/nullability apply"
    )


def _evidence(path: Path, module: str) -> list[str]:
    command = (
        "dataproof-verifier doppelganger replay"
        if module == "doppelganger"
        else "dataproof-verifier replay"
    )
    literal = (
        shlex.quote(str(path))
        if all(32 <= ord(char) < 127 for char in str(path))
        else "<witness path above>"
    )
    return [
        "Replay: DuckDB validation passed for the serialized witness and replay.sql (REPLAY_OK).",
        f"Evidence: {_cell(str(path))}",
        f"Result: {_cell(str(path.with_name('result.json')))}",
        f"Replay SQL: {_cell(str(path.with_name('replay.sql')))}",
        f"Recheck: {command} {literal}",
    ]


def _no_undo(path: Path, data: dict[str, Any]) -> str:
    checked = replay.validate_serialized(path)
    if not checked.valid:
        raise ExplanationError(checked.reason or "NoUndo witness failed DuckDB replay", 7)
    spec = parse_spec(data["spec"])
    view = parse_query(spec.views[0], spec, metric=False)
    metric = parse_query(spec.metric, spec, metric=True)
    worlds = data["worlds"]
    left = replay._rows(worlds["D1"], spec)
    right = replay._rows(worlds["D2"], spec)
    view_names = tuple(item.name for item in view.projections)
    lines = [
        "NoUndo — bounded information-loss counterexample",
        "The retained view has the same SQL bag for D1 and D2, but the declared KPI differs.",
        f"Source D1 ({len(left)} rows):",
        *_bag(left, spec.names),
        "Source D2 (" + str(len(right)) + " rows):",
        *_bag(right, spec.names),
        "Retained view V(D1):",
        *_bag(checked.views[0], view_names),
        "Retained view V(D2):",
        *_bag(checked.views[1], view_names),
        "EQUAL as unordered SQL bags, including multiplicities and NULL grouping.",
        f"KPI {metric.projections[0].name}: D1 = {_cell(checked.metrics[0])}; "
        f"D2 = {_cell(checked.metrics[1])} — DIFFERENT.",
        "Finite scope: " + _scope(spec) + ". No universal determinacy claim.",
        *_evidence(path, "no-undo"),
    ]
    return "\n".join(lines)


def _truth(value: bool | None) -> str:
    return "TRUE" if value is True else "FALSE" if value is False else "UNKNOWN"


def _doppel(path: Path, data: dict[str, Any]) -> str:
    checked = doppel_replay.validate_serialized(path)
    if not checked.valid or checked.invariant is None:
        raise ExplanationError(checked.reason or "Doppelgänger witness failed DuckDB replay", 7)
    spec = parse_doppel_spec(data["spec"])
    rows = replay._rows(data["rows"], spec.table)
    lines = [
        "Doppelgänger — bounded test blind spot",
        "This synthetic dataset passes all supplied existing assertions while violating",
        "the separately supplied invariant.",
        f"Source ({len(rows)} row{'s' if len(rows) != 1 else ''}):",
        *_bag(rows, spec.table.names),
        "Existing assertions (DuckDB SQL truth):",
    ]
    for assertion, evaluation in zip(spec.tests, checked.tests, strict=True):
        lines.append(
            f"  {assertion.id}: {_cell(evaluation.value)} {assertion.op} "
            f"{assertion.value} = {_truth(evaluation.truth)}"
        )
    invariant = spec.invariant
    evaluation = checked.invariant
    lines.extend(
        [
            "All existing assertions are TRUE; FALSE and UNKNOWN would not pass.",
            "Separately declared invariant:",
            f"  {invariant.id}: {_cell(evaluation.value)} {invariant.op} "
            f"{invariant.value} = {_truth(evaluation.truth)} — VIOLATED.",
            "  User-supplied rationale: " + _cell(invariant.rationale),
            "DataProof validates the declared predicate, not the real-world truth",
            "of that rationale.",
            "Finite scope: " + _scope(spec.table) + ". No universal test-adequacy claim.",
            *_evidence(path, "doppelganger"),
        ]
    )
    return "\n".join(lines)


def explain(path: Path) -> str:
    """Return an explanation only after sidecar consistency and independent DuckDB replay."""
    if path.name != "witness.json":
        raise ExplanationError("expected a witness.json evidence file")
    data = _json_object(path)
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ExplanationError("unsupported witness schema_version")
    module = data.get("module", "no-undo")
    status = data.get("status")
    expected = "BLIND_SPOT_FOUND" if module == "doppelganger" else "COUNTEREXAMPLE_FOUND"
    if module not in {"no-undo", "doppelganger"}:
        raise ExplanationError("unsupported witness module")
    if status != expected:
        raise ExplanationError(
            f"{_cell(status or 'unknown')} has no validated positive witness to explain; "
            "a bounded negative is not a universal proof"
        )
    _sidecars(path, data, module)
    return _doppel(path, data) if module == "doppelganger" else _no_undo(path, data)
