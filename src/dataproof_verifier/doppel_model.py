"""Versioned, fail-closed input contract for one-dataset test adequacy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dataproof_verifier.ir import Query
from dataproof_verifier.models import Spec, SpecError, UnsupportedError, load_raw_spec, parse_spec
from dataproof_verifier.parser import parse_query

_ID = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
_OPS = frozenset({"=", "!=", "<", "<=", ">", ">="})


@dataclass(frozen=True)
class Assertion:
    id: str
    sql: str
    op: str
    value: int
    query: Query
    rationale: str | None = None


@dataclass(frozen=True)
class DoppelSpec:
    table: Spec  # Reuses only the validated schema, finite bounds and resource limits.
    tests: tuple[Assertion, ...]
    invariant: Assertion
    output_dir: Path


def _mapping(value: Any, label: str, allowed: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpecError(f"{label} must be a mapping")
    extra = set(value) - allowed
    if extra:
        raise SpecError(f"unknown {label} fields: {sorted(extra)}")
    return value


def _assertion(raw: Any, table: Spec, *, invariant: bool) -> Assertion:
    item = _mapping(
        raw,
        "invariant" if invariant else "test",
        {"id", "sql", "op", "value", "rationale"} if invariant else {"id", "sql", "op", "value"},
    )
    identity = item.get("id")
    if not isinstance(identity, str) or not _ID.fullmatch(identity):
        raise SpecError("assertion id must be a simple identifier")
    sql = item.get("sql")
    if not isinstance(sql, str) or not sql:
        raise SpecError("assertion sql must be a nonempty string")
    op = item.get("op")
    if not isinstance(op, str) or op not in _OPS:
        raise UnsupportedError("unsupported assertion comparison")
    value = item.get("value")
    if type(value) is not int or not -(2**31) <= value < 2**31:
        raise SpecError("assertion value must be a 32-bit integer")
    rationale = item.get("rationale")
    if invariant and (
        not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 1000
    ):
        raise SpecError("invariant requires a nonempty rationale of at most 1000 characters")
    return Assertion(identity, sql, op, value, parse_query(sql, table, metric=True), rationale)


def parse_doppel_spec(raw: Any, source: Path | None = None) -> DoppelSpec:
    item = _mapping(
        raw,
        "spec",
        {
            "schema_version",
            "table",
            "max_rows",
            "timeout_ms",
            "max_memory_mb",
            "seed",
            "output_dir",
            "tests",
            "invariant",
        },
    )
    if type(item.get("schema_version")) is not int or item["schema_version"] != 1:
        raise SpecError("schema_version must be 1")
    out = item.get("output_dir", "artifacts/doppelganger")
    if not isinstance(out, str) or not out:
        raise SpecError("output_dir must be a nonempty path")
    output = Path(out)
    if source is not None and not output.is_absolute():
        output = (source.parent / output).resolve()
    # The NoUndo input model already validates the shared table/domain/key fragment.
    # Placeholder queries are never parsed or executed by Doppelgänger.
    table = parse_spec(
        {
            "table": item.get("table"),
            "views": ["SELECT placeholder, COUNT(*) AS n FROM placeholder GROUP BY placeholder"],
            "metric": "SELECT COUNT(*) AS n FROM placeholder",
            "max_rows": item.get("max_rows"),
            "timeout_ms": item.get("timeout_ms", 10000),
            "max_memory_mb": item.get("max_memory_mb", 256),
            "seed": item.get("seed", 0),
            "output_dir": str(output),
        },
        source,
    )
    tests_raw = item.get("tests")
    if not isinstance(tests_raw, list) or not 1 <= len(tests_raw) <= 4:
        raise SpecError("tests must contain 1 to 4 assertions")
    tests = tuple(_assertion(entry, table, invariant=False) for entry in tests_raw)
    inv = _assertion(item.get("invariant"), table, invariant=True)
    identities = [test.id for test in tests] + [inv.id]
    if len(set(identities)) != len(identities):
        raise SpecError("assertion ids must be distinct")
    return DoppelSpec(table, tests, inv, output)


def load_doppel_spec(path: Path) -> DoppelSpec:
    return parse_doppel_spec(load_raw_spec(path), path)


def doppel_mapping(spec: DoppelSpec) -> dict[str, Any]:
    from dataproof_verifier.models import spec_mapping

    base = spec_mapping(spec.table)
    base.pop("views")
    base.pop("metric")
    base["schema_version"] = 1
    base["output_dir"] = str(spec.output_dir)

    def assertion(a: Assertion) -> dict[str, Any]:
        data: dict[str, Any] = {"id": a.id, "sql": a.sql, "op": a.op, "value": a.value}
        if a.rationale is not None:
            data["rationale"] = a.rationale
        return data

    base["tests"] = [assertion(test) for test in spec.tests]
    base["invariant"] = assertion(spec.invariant)
    return base
