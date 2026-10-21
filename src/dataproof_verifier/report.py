"""Stable, synthetic-only JSON and SQL evidence artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from typing import Any

import duckdb
import z3

from dataproof_verifier import __version__
from dataproof_verifier.models import Row, Spec, spec_mapping
from dataproof_verifier.replay import make_replay_sql, serialize_rows


def _write(path: Path, data: Any) -> None:
    payload = json.dumps(data, indent=2, sort_keys=True, default=str) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix=".dataproof-write-", dir=path.parent, delete=False
    ) as stream:
        staged = Path(stream.name)
        stream.write(payload)
    try:
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def versions() -> dict[str, str]:
    return {
        "dataproof": __version__,
        "python": sys.version.split()[0],
        "duckdb": duckdb.__version__,
        "sqlglot": version("sqlglot"),
        "z3": z3.get_version_string(),
        "platform": platform.platform(),
    }


def result_data(spec: Spec, status: str, reason: str | None, input_hash: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "reason": reason,
        "input_sha256": input_hash,
        "assumptions": [
            "DuckDB SQL dialect",
            "one synthetic table and one grouped retained view",
            "bag source rows and unordered multiset view equality",
            "finite explicitly declared domains and row bound",
            "exact integer amounts, SQL NULL aggregates",
        ],
        "search": {
            "backend": "Z3 finite row slots",
            "max_rows_per_world": spec.max_rows,
            "timeout_ms": spec.timeout_ms,
            "max_memory_mb": spec.max_memory_mb,
            "seed": spec.seed,
            "domain_sizes": {c.name: len(c.domain) for c in spec.columns},
        },
        "versions": versions(),
        "spec": spec_mapping(spec),
    }


def write_result(spec: Spec, result: dict[str, Any]) -> Path:
    spec.output_dir.mkdir(parents=True, exist_ok=True)
    path = spec.output_dir / "result.json"
    _write(path, result)
    return path


def write_witness(
    spec: Spec,
    result: dict[str, Any],
    left: tuple[Row, ...],
    right: tuple[Row, ...],
    target_dir: Path | None = None,
) -> Path:
    directory = target_dir or spec.output_dir
    directory.mkdir(parents=True, exist_ok=True)
    worlds = {"D1": serialize_rows(left), "D2": serialize_rows(right)}
    canonical = json.dumps(worlds, sort_keys=True, separators=(",", ":")).encode()
    witness_hash = hashlib.sha256(canonical).hexdigest()
    witness = {
        **result,
        "worlds": worlds,
        "worlds_sha256": witness_hash,
        "replay_command": (
            f"dataproof-verifier replay {shlex.quote(str(spec.output_dir / 'witness.json'))}"
        ),
    }
    path = directory / "witness.json"
    _write(path, witness)
    (directory / "replay.sql").write_text(make_replay_sql(spec, left, right), encoding="utf-8")
    return path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
