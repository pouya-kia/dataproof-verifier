"""Versioned, fail-closed export of Doppelgänger witnesses to regression fixtures."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlglot
import yaml
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError

from dataproof_verifier.doppel_model import DoppelSpec, doppel_mapping, parse_doppel_spec
from dataproof_verifier.doppel_replay import _evaluate, validate, validate_serialized
from dataproof_verifier.models import Row, SpecError, UnsupportedError, legal_world
from dataproof_verifier.parser import _predicate
from dataproof_verifier.replay import _connection, _create_table, _insert_sql, _rows, serialize_rows

FORMAT_VERSION = 1
_ARTIFACT_LIMIT = 128_000


class ExportConflict(ValueError):
    """The requested output cannot be written without touching user-owned files."""


@dataclass(frozen=True)
class TargetContract:
    model_name: str
    expected_rows: tuple[Row, ...]
    expected_behavior: str
    dbt_model_sql: str | None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_file(path: Path, limit: int) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise SpecError("input must be a regular file, not a symlink")
    if path.stat().st_size > limit:
        raise SpecError("input exceeds size limit")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise SpecError("input must be a JSON object")
    return value, raw


def _source(path: Path) -> tuple[DoppelSpec, tuple[Row, ...], str]:
    witness, raw = _json_file(path, _ARTIFACT_LIMIT)
    if (
        type(witness.get("schema_version")) is not int
        or witness.get("schema_version") != 1
        or witness.get("module") != "doppelganger"
        or witness.get("status") != "BLIND_SPOT_FOUND"
    ):
        raise UnsupportedError("only validated Doppelgänger witness schema 1 is supported")
    checked = validate_serialized(path)
    if not checked.valid:
        raise SpecError(f"independent witness replay failed: {checked.reason}")
    spec = parse_doppel_spec(witness["spec"])
    rows = _rows(witness["rows"], spec.table)
    return spec, rows, _sha(raw)


def _contract(path: Path, spec: DoppelSpec) -> tuple[TargetContract, str]:
    data, raw = _json_file(path, 64_000)
    required = {"schema_version", "target_kind", "model_name", "expected_rows", "expected_behavior"}
    if not required <= set(data) or set(data) - required - {"dbt_model_sql"}:
        raise SpecError("target contract fields do not match version 1")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise UnsupportedError("unsupported target contract version")
    if data["target_kind"] != "single_table_sql":
        raise UnsupportedError("unsupported target kind")
    model_name = data["model_name"]
    if (
        not isinstance(model_name, str)
        or not model_name.isascii()
        or not model_name.isidentifier()
        or model_name == spec.table.table
    ):
        raise SpecError("model_name must be a distinct simple ASCII identifier")
    behavior = data["expected_behavior"]
    if not isinstance(behavior, str) or not behavior.strip() or len(behavior) > 1000:
        raise SpecError("expected_behavior must be a nonempty rationale of at most 1000 chars")
    rows = _rows(data["expected_rows"], spec.table)
    if not legal_world(spec.table, rows):
        raise SpecError("expected rows violate declared table constraints")
    if _invariant_truth(spec, rows) is not True:
        raise SpecError("declared expected rows do not make the business invariant SQL TRUE")
    dbt_sql = data.get("dbt_model_sql")
    if dbt_sql is not None and not isinstance(dbt_sql, str):
        raise SpecError("dbt_model_sql must be SQL text")
    return TargetContract(model_name, rows, behavior, dbt_sql), _sha(raw)


def _invariant_truth(spec: DoppelSpec, rows: tuple[Row, ...]) -> bool | None:
    con = _connection()
    try:
        con.execute(_create_table(spec.table))
        for statement in _insert_sql(spec.table, rows):
            con.execute(statement)
        return _evaluate(con, spec.invariant).truth
    finally:
        con.close()


def validate_target_sql(sql: str, spec: DoppelSpec) -> None:
    """Admit only a same-schema, one-table SELECT; no user SQL reaches DuckDB first."""
    if len(sql) > 4096:
        raise UnsupportedError("target SQL exceeds 4096 characters")
    try:
        statements = sqlglot.parse(sql, read="duckdb", error_level=ErrorLevel.RAISE)
    except ParseError as exc:
        raise UnsupportedError("target SQL cannot be parsed") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsupportedError("target must be exactly one SELECT")
    node = statements[0]
    clauses = {"expressions", "from_", "where"}
    if any(value for key, value in node.args.items() if key not in clauses):
        raise UnsupportedError("target SELECT has an unsupported clause")
    source = node.args.get("from_")
    if not isinstance(source, exp.From) or not isinstance(source.this, exp.Table):
        raise UnsupportedError("target must read one direct source table")
    table = source.this
    if table.name != spec.table.table or table.db or table.catalog or table.alias:
        raise UnsupportedError("target must read the declared source table")
    where = node.args.get("where")
    if where is not None:
        if not isinstance(where, exp.Where) or where.this is None:
            raise UnsupportedError("unsupported target WHERE clause")
        _predicate(where.this, spec.table)
    if len(node.expressions) != len(spec.table.columns):
        raise UnsupportedError("target must project every declared column in order")
    for expression, column in zip(node.expressions, spec.table.columns, strict=True):
        actual = expression.this if isinstance(expression, exp.Alias) else expression
        name = expression.alias if isinstance(expression, exp.Alias) else actual.name
        if name != column.name:
            raise UnsupportedError("target output columns must match source schema in order")
        if isinstance(actual, exp.Column):
            if actual.name != column.name or actual.table or actual.db or actual.catalog:
                raise UnsupportedError("target projection must be a direct declared column")
            continue
        if (
            isinstance(actual, exp.Greatest)
            and column.type == "INTEGER"
            and isinstance(actual.this, exp.Column)
            and actual.this.name == column.name
            and not (actual.this.table or actual.this.db or actual.this.catalog)
            and len(actual.expressions) == 1
            and isinstance(actual.expressions[0], exp.Literal)
            and actual.expressions[0].is_int
            and actual.expressions[0].this == "0"
        ):
            continue
        raise UnsupportedError("target projection is outside direct-column/GREATEST(column, 0)")


def _target_rows(spec: DoppelSpec, rows: tuple[Row, ...], sql: str) -> tuple[Row, ...]:
    validate_target_sql(sql, spec)
    con = _connection()
    timer = threading.Timer(5.0, con.interrupt)
    try:
        con.execute("SET memory_limit = '128MB'")
        con.execute(_create_table(spec.table))
        for statement in _insert_sql(spec.table, rows):
            con.execute(statement)
        timer.start()
        try:
            cursor = con.execute(sql)
            if tuple(item[0] for item in cursor.description) != spec.table.names:
                raise AssertionError("target output columns differ from the declared schema")
            return tuple(tuple(item) for item in cursor.fetchall())
        finally:
            timer.cancel()
    finally:
        con.close()


def assert_generated_case(fixture_path: Path, target_sql_path: Path, fixture_sha256: str) -> None:
    """Execute an exported fixture; target path is deliberately supplied at test time."""
    fixture, raw = _json_file(fixture_path, _ARTIFACT_LIMIT)
    assert _sha(raw) == fixture_sha256, "generated fixture integrity mismatch"
    assert fixture.get("schema_version") == FORMAT_VERSION
    assert fixture.get("module") == "proof2test"
    spec = parse_doppel_spec(fixture["source_spec"])
    source_rows = _rows(fixture["source_rows"], spec.table)
    assert validate(spec, source_rows).valid, "source witness no longer validates"
    expected = _rows(fixture["expected_rows"], spec.table)
    assert legal_world(spec.table, expected), "expected output violates declared schema"
    assert _invariant_truth(spec, expected) is True, "expected invariant is not SQL TRUE"
    if target_sql_path.is_symlink() or not target_sql_path.is_file():
        raise AssertionError("target SQL must be a regular file")
    if target_sql_path.stat().st_size > 4096:
        raise UnsupportedError("target SQL exceeds 4096 bytes")
    sql = target_sql_path.read_text(encoding="utf-8")
    actual = _target_rows(spec, source_rows, sql)
    assert legal_world(spec.table, actual), "target output violates declared schema"
    assert Counter(actual) == Counter(expected), (
        f"target output bag differs: actual={actual!r}, expected={expected!r}"
    )
    assert _invariant_truth(spec, actual) is True, "target business invariant is not SQL TRUE"


def _render_pytest(name: str, digest: str) -> str:
    return (
        '"""Generated DataProof regression; set DATAPROOF_TARGET_SQL to the model SQL file."""\n'
        "\nimport os\nfrom pathlib import Path\n\n"
        "from dataproof_verifier.proof2test import assert_generated_case\n\n\n"
        f"def test_proof2test_{name}() -> None:\n"
        '    target = os.environ.get("DATAPROOF_TARGET_SQL")\n'
        '    assert target, "DATAPROOF_TARGET_SQL must name the implementation SQL file"\n'
        "    assert_generated_case(\n"
        '        Path(__file__).with_name("fixture.json"),\n'
        "        Path(target),\n"
        f'        "{digest}",\n'
        "    )\n"
    )


def _public_source_spec(spec: DoppelSpec) -> dict[str, Any]:
    source = doppel_mapping(spec)
    source["output_dir"] = "artifacts/proof2test"
    source["invariant"]["rationale"] = "User-declared invariant; private rationale omitted."
    return source


def _publish(output: Path, files: dict[str, bytes]) -> None:
    unsafe = {Path.home().resolve(), Path.cwd().resolve(), Path("/")}
    if output.is_symlink() or output.parent.is_symlink() or output.resolve() in unsafe:
        raise ExportConflict("unsafe output directory")
    manifest = {
        "schema_version": FORMAT_VERSION,
        "module": "proof2test",
        "files": {name: _sha(content) for name, content in sorted(files.items())},
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    files = {**files, "manifest.json": manifest_bytes}
    if output.exists():
        if not output.is_dir():
            raise ExportConflict("output path is not a directory")
        existing = {p.name for p in output.iterdir()}
        if existing:
            if existing != set(files) or any(
                not (output / name).is_file()
                or (output / name).is_symlink()
                or (output / name).read_bytes() != content
                for name, content in files.items()
            ):
                raise ExportConflict("output contains unrelated or modified files")
            return
    else:
        output.mkdir(parents=True)
    for name, content in files.items():
        with (output / name).open("xb") as stream:
            stream.write(content)


def export_pytest(witness: Path, target: Path, output: Path) -> tuple[str, ...]:
    spec, rows, witness_hash = _source(witness)
    contract, contract_hash = _contract(target, spec)
    fixture = {
        "schema_version": FORMAT_VERSION,
        "module": "proof2test",
        "source_witness_sha256": witness_hash,
        "target_contract_sha256": contract_hash,
        "source_spec": _public_source_spec(spec),
        "source_rows": serialize_rows(rows),
        "expected_rows": serialize_rows(contract.expected_rows),
        "model_name": contract.model_name,
    }
    fixture_bytes = (json.dumps(fixture, indent=2, sort_keys=True) + "\n").encode()
    test_name = f"test_proof2test_{contract.model_name}_{witness_hash[:8]}.py"
    test = _render_pytest(f"{contract.model_name}_{witness_hash[:8]}", _sha(fixture_bytes))
    _publish(output, {"fixture.json": fixture_bytes, test_name: test.encode()})
    return (test_name, "fixture.json", "manifest.json")


def export_dbt(witness: Path, target: Path, output: Path) -> tuple[str, ...]:
    """Emit one dbt Core unit test for a local one-ref SQL model, not a full project."""
    spec, rows, witness_hash = _source(witness)
    contract, contract_hash = _contract(target, spec)
    if (
        any(col.type != "INTEGER" or col.nullable for col in spec.table.columns)
        or not rows
        or not contract.expected_rows
    ):
        raise UnsupportedError("dbt adapter supports nonempty non-NULL INTEGER fixtures only")
    template = f"{{{{ ref('{spec.table.table}') }}}}"
    model_sql = contract.dbt_model_sql
    if (
        model_sql is None
        or model_sql.count(template) != 1
        or "{{" in model_sql.replace(template, "")
        or "}}" in model_sql.replace(template, "")
    ):
        raise UnsupportedError("dbt adapter requires exactly one declared source ref")
    validate_target_sql(model_sql.replace(template, spec.table.table), spec)
    columns = spec.table.names

    def dictionaries(data: tuple[Row, ...]) -> list[dict[str, int]]:
        return [
            {name: value for name, value in zip(columns, row, strict=True) if type(value) is int}
            for row in data
        ]

    unit_name = f"proof2test_{contract.model_name}_{witness_hash[:8]}"
    document = {
        "version": 2,
        "unit_tests": [
            {
                "name": unit_name,
                "model": contract.model_name,
                "given": [
                    {
                        "input": f"ref('{spec.table.table}')",
                        "format": "dict",
                        "rows": dictionaries(rows),
                    }
                ],
                "expect": {"format": "dict", "rows": dictionaries(contract.expected_rows)},
            }
        ],
    }
    yaml_bytes = yaml.safe_dump(document, sort_keys=False, allow_unicode=False).encode()
    fixture = {
        "schema_version": FORMAT_VERSION,
        "module": "proof2test",
        "format": "dbt-core-unit-test",
        "source_witness_sha256": witness_hash,
        "target_contract_sha256": contract_hash,
        "source_spec": _public_source_spec(spec),
        "source_rows": serialize_rows(rows),
        "expected_rows": serialize_rows(contract.expected_rows),
        "model_name": contract.model_name,
        "unit_test_name": unit_name,
    }
    fixture_bytes = (json.dumps(fixture, indent=2, sort_keys=True) + "\n").encode()
    _publish(output, {"unit_tests.yml": yaml_bytes, "fixture.json": fixture_bytes})
    return ("unit_tests.yml", "fixture.json", "manifest.json")
