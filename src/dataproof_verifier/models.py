"""Strict finite input model for the Phase 1 NoUndo fragment."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

Value = int | date | None
Row = tuple[Value, ...]
_NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")


class SpecError(ValueError):
    """Malformed schema, bound or input."""


class UnsupportedError(ValueError):
    """SQL or schema semantics outside the admitted fragment."""


class InvalidSqlError(SpecError):
    """SQL text cannot be parsed at all."""


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    nullable: bool
    domain: tuple[Value, ...]


@dataclass(frozen=True)
class Spec:
    table: str
    columns: tuple[Column, ...]
    primary_key: tuple[str, ...]
    unique: tuple[tuple[str, ...], ...]
    views: tuple[str, ...]
    metric: str
    max_rows: int
    timeout_ms: int
    max_memory_mb: int
    seed: int
    output_dir: Path

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(col.name for col in self.columns)

    def column(self, name: str) -> Column:
        for col in self.columns:
            if col.name == name:
                return col
        raise SpecError(f"unknown column: {name}")


def _keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(value) - allowed
    if extra:
        raise SpecError(f"unknown {label} fields: {sorted(extra)}")


def _name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise SpecError(f"{label} must be a simple SQL identifier")
    return value


def _value(raw: Any, typ: str) -> Value:
    if raw is None:
        return None
    if typ == "INTEGER" and type(raw) is int and -(2**31) <= raw < 2**31:
        return raw
    if typ == "DATE" and isinstance(raw, str):
        try:
            parsed = date.fromisoformat(raw)
            if parsed.isoformat() == raw:
                return parsed
        except ValueError:
            pass
    raise SpecError(f"invalid {typ} domain value: {raw!r}")


def parse_spec(raw: Any, source: Path | None = None) -> Spec:
    if not isinstance(raw, dict):
        raise SpecError("spec must be a mapping")
    _keys(
        raw,
        {
            "table",
            "views",
            "metric",
            "max_rows",
            "timeout_ms",
            "max_memory_mb",
            "seed",
            "output_dir",
        },
        "spec",
    )
    table_raw = raw.get("table")
    if not isinstance(table_raw, dict):
        raise SpecError("table must be a mapping")
    if "foreign_keys" in table_raw:
        raise UnsupportedError("foreign keys are outside the Phase 1 fragment")
    _keys(table_raw, {"name", "columns", "primary_key", "unique"}, "table")
    table = _name(table_raw.get("name"), "table name")
    cols_raw = table_raw.get("columns")
    if not isinstance(cols_raw, list) or not 1 <= len(cols_raw) <= 4:
        raise SpecError("columns must contain 1 to 4 entries")
    columns: list[Column] = []
    for item in cols_raw:
        if not isinstance(item, dict):
            raise SpecError("column must be a mapping")
        _keys(item, {"name", "type", "nullable", "domain"}, "column")
        name = _name(item.get("name"), "column name")
        typ = item.get("type")
        if typ not in ("INTEGER", "DATE"):
            raise UnsupportedError(f"unsupported column type: {typ!r}")
        nullable = item.get("nullable", False)
        if type(nullable) is not bool:
            raise SpecError("nullable must be boolean")
        domain_raw = item.get("domain")
        if not isinstance(domain_raw, list) or not 1 <= len(domain_raw) <= 4:
            raise SpecError("domain must contain 1 to 4 values")
        domain = tuple(_value(x, typ) for x in domain_raw)
        if len(set(domain)) != len(domain):
            raise SpecError(f"duplicate domain value: {name}")
        if None in domain and not nullable:
            raise SpecError(f"NULL in non-nullable domain: {name}")
        if nullable and None not in domain:
            domain += (None,)
        columns.append(Column(name, typ, nullable, domain))
    names = [col.name for col in columns]
    if len(names) != len(set(names)):
        raise SpecError("duplicate column name")

    def constraint_names(value: Any, label: str) -> tuple[str, ...]:
        if not isinstance(value, list) or not value or not all(isinstance(x, str) for x in value):
            raise SpecError(f"{label} must be a nonempty list of column names")
        result = tuple(value)
        if len(result) != len(set(result)) or any(x not in names for x in result):
            raise SpecError(f"invalid {label} columns")
        return result

    pk_raw = table_raw.get("primary_key", [])
    if not isinstance(pk_raw, list):
        raise SpecError("primary_key must be a list")
    pk = constraint_names(pk_raw, "primary_key") if pk_raw else ()
    if any(next(c for c in columns if c.name == name).nullable for name in pk):
        raise SpecError("primary key columns cannot be nullable")
    unique_raw = table_raw.get("unique", [])
    if not isinstance(unique_raw, list):
        raise SpecError("unique must be a list")
    unique = tuple(constraint_names(x, "unique") for x in unique_raw)
    views = raw.get("views")
    if not isinstance(views, list) or not views or not all(isinstance(x, str) for x in views):
        raise SpecError("views must contain SQL strings")
    if len(views) != 1:
        raise UnsupportedError("Phase 1 supports exactly one retained view")
    metric = raw.get("metric")
    if not isinstance(metric, str):
        raise SpecError("metric must be SQL")
    max_rows = raw.get("max_rows")
    timeout_ms = raw.get("timeout_ms", 10000)
    max_memory_mb = raw.get("max_memory_mb", 256)
    seed = raw.get("seed", 0)
    if type(max_rows) is not int or not 0 <= max_rows <= 3:
        raise SpecError("max_rows must be 0..3")
    if type(timeout_ms) is not int or not 1 <= timeout_ms <= 30000:
        raise SpecError("timeout_ms must be 1..30000")
    if type(max_memory_mb) is not int or not 32 <= max_memory_mb <= 1024:
        raise SpecError("max_memory_mb must be 32..1024")
    if type(seed) is not int or not 0 <= seed < 2**31:
        raise SpecError("seed must be a nonnegative 31-bit integer")
    out = raw.get("output_dir", "artifacts/no_undo")
    if not isinstance(out, str) or not out:
        raise SpecError("output_dir must be a nonempty path")
    output_dir = Path(out)
    if not output_dir.is_absolute() and source is not None:
        output_dir = (source.parent / output_dir).resolve()
    return Spec(
        table,
        tuple(columns),
        pk,
        unique,
        tuple(views),
        metric,
        max_rows,
        timeout_ms,
        max_memory_mb,
        seed,
        output_dir,
    )


def load_raw_spec(path: Path) -> Any:
    if path.stat().st_size > 64_000:
        raise SpecError("spec exceeds 64 KiB")
    content = path.read_text(encoding="utf-8")
    try:
        return json.loads(content) if path.suffix.lower() == ".json" else yaml.safe_load(content)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SpecError(f"cannot parse spec: {exc}") from exc


def output_dir_hint(path: Path) -> Path | None:
    """Find an output path without accepting an otherwise invalid specification."""
    try:
        raw = load_raw_spec(path)
    except (OSError, SpecError, UnicodeError):
        return None
    if not isinstance(raw, dict):
        return None
    value = raw.get("output_dir", "artifacts/no_undo")
    if not isinstance(value, str) or not value:
        return None
    directory = Path(value)
    return directory if directory.is_absolute() else (path.parent / directory).resolve()


def load_spec(path: Path) -> Spec:
    return parse_spec(load_raw_spec(path), path)


def legal_world(spec: Spec, rows: tuple[Row, ...]) -> bool:
    if len(rows) > spec.max_rows:
        return False
    for row in rows:
        if len(row) != len(spec.columns):
            return False
        if any(
            not any(
                type(value) is type(candidate) and value == candidate for candidate in col.domain
            )
            for value, col in zip(row, spec.columns, strict=True)
        ):
            return False
    for key in ((spec.primary_key,) if spec.primary_key else ()) + spec.unique:
        indices = [spec.names.index(x) for x in key]
        seen: set[tuple[Value, ...]] = set()
        for row in rows:
            selected = tuple(row[i] for i in indices)
            if None in selected and key != spec.primary_key:
                continue
            if None in selected or selected in seen:
                return False
            seen.add(selected)
    return True


def serial_value(value: Value) -> int | str | None:
    return value.isoformat() if isinstance(value, date) else value


def spec_mapping(spec: Spec) -> dict[str, Any]:
    return {
        "table": {
            "name": spec.table,
            "columns": [
                {
                    "name": col.name,
                    "type": col.type,
                    "nullable": col.nullable,
                    "domain": [serial_value(value) for value in col.domain],
                }
                for col in spec.columns
            ],
            "primary_key": list(spec.primary_key),
            "unique": [list(key) for key in spec.unique],
        },
        "views": list(spec.views),
        "metric": spec.metric,
        "max_rows": spec.max_rows,
        "timeout_ms": spec.timeout_ms,
        "max_memory_mb": spec.max_memory_mb,
        "seed": spec.seed,
        "output_dir": str(spec.output_dir),
    }
