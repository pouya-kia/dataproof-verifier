"""Executable Proof2Test round trips and fail-closed export regressions."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from dataproof_verifier import proof2test
from dataproof_verifier.cli import export_test
from dataproof_verifier.doppel_cli import check as doppel_check
from dataproof_verifier.doppel_model import load_doppel_spec
from dataproof_verifier.models import SpecError, UnsupportedError

ROOT = Path(__file__).resolve().parents[1]
WITNESS = ROOT / "examples/doppelganger/evidence/witness.json"
CONTRACT = ROOT / "examples/proof2test/clamp_amount.contract.json"
BAD = ROOT / "examples/proof2test/defective.sql"
GOOD = ROOT / "examples/proof2test/corrected.sql"


def _generated_run(folder: Path, target: Path | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    if target is None:
        env.pop("DATAPROOF_TARGET_SQL", None)
    else:
        env["DATAPROOF_TARGET_SQL"] = str(target)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(next(folder.glob("test_*.py")))],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _copy_witness(tmp_path: Path) -> Path:
    witness = tmp_path / "witness.json"
    shutil.copyfile(WITNESS, witness)
    shutil.copyfile(WITNESS.with_name("replay.sql"), tmp_path / "replay.sql")
    return witness


def _contract_file(tmp_path: Path, **changes: object) -> Path:
    raw = json.loads(CONTRACT.read_text())
    raw.update(changes)
    path = tmp_path / "target.json"
    path.write_text(json.dumps(raw))
    return path


def test_real_generated_regression_defective_fails_corrected_passes(tmp_path: Path) -> None:
    out = tmp_path / "export"
    names = proof2test.export_pytest(WITNESS, CONTRACT, out)
    assert len(names) == 3
    ast.parse((out / names[0]).read_text())
    assert _generated_run(out, BAD).returncode == 1
    bad = _generated_run(out, BAD)
    assert "target output bag differs" in bad.stdout
    fixed = _generated_run(out, GOOD)
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert "1 passed" in fixed.stdout
    assert _generated_run(out, None).returncode == 1
    fixture = json.loads((out / "fixture.json").read_text())
    assert fixture["source_witness_sha256"] == hashlib.sha256(WITNESS.read_bytes()).hexdigest()
    assert fixture["target_contract_sha256"] == hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    assert "/Users/" not in json.dumps(fixture)


def test_repeat_is_identical_and_conflicts_preserve_user_files(tmp_path: Path) -> None:
    out = tmp_path / "export"
    proof2test.export_pytest(WITNESS, CONTRACT, out)
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    proof2test.export_pytest(WITNESS, CONTRACT, out)
    assert before == {p.name: p.read_bytes() for p in out.iterdir()}
    unrelated = out / "notes.txt"
    unrelated.write_text("keep me")
    with pytest.raises(proof2test.ExportConflict):
        proof2test.export_pytest(WITNESS, CONTRACT, out)
    assert unrelated.read_text() == "keep me"
    unrelated.unlink()
    (out / "fixture.json").write_text("modified")
    with pytest.raises(proof2test.ExportConflict):
        proof2test.export_pytest(WITNESS, CONTRACT, out)
    assert (out / "fixture.json").read_text() == "modified"


@pytest.mark.parametrize("format_name", ["pytest", "dbt"])
def test_versioned_golden_artifacts_regenerate_exactly(tmp_path: Path, format_name: str) -> None:
    out = tmp_path / "regenerated"
    exporter = proof2test.export_pytest if format_name == "pytest" else proof2test.export_dbt
    exporter(WITNESS, CONTRACT, out)
    golden = ROOT / "examples/proof2test" / f"generated_{format_name}"
    assert {p.name: p.read_bytes() for p in out.iterdir()} == {
        p.name: p.read_bytes() for p in golden.iterdir()
    }
    manifest = json.loads((out / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest


@settings(max_examples=30, deadline=None)
@given(st.lists(st.sampled_from([-1, 0, 1]), min_size=0, max_size=2))
def test_target_execution_matches_independent_bag_oracle(values: list[int]) -> None:
    spec = load_doppel_spec(ROOT / "examples/doppelganger/nonnegative_amount.json")
    rows = tuple((value,) for value in values)
    identity = proof2test._target_rows(spec, rows, "SELECT amount FROM orders")
    clamped = proof2test._target_rows(
        spec, rows, "SELECT GREATEST(amount, 0) AS amount FROM orders"
    )
    assert sorted(identity) == sorted(rows)
    assert sorted(clamped) == sorted((max(value, 0),) for value in values)
    assert sorted(proof2test._target_rows(spec, rows[::-1], "SELECT amount FROM orders")) == sorted(
        rows
    )


@pytest.mark.parametrize("change", ["rows", "sql", "evaluations", "replay", "version"])
def test_tampered_witness_cannot_export(tmp_path: Path, change: str) -> None:
    witness = _copy_witness(tmp_path)
    data = json.loads(witness.read_text())
    if change == "rows":
        data["rows"] = [[0]]
    elif change == "sql":
        data["spec"]["invariant"]["sql"] = "SELECT COUNT(*) AS n FROM orders"
    elif change == "evaluations":
        data["invariant_evaluation"]["truth"] = True
    elif change == "version":
        data["schema_version"] = 2
    else:
        (tmp_path / "replay.sql").write_text("SELECT 'not replay';")
    witness.write_text(json.dumps(data))
    with pytest.raises((SpecError, UnsupportedError, ValueError)):
        proof2test.export_pytest(witness, CONTRACT, tmp_path / "export")
    assert not (tmp_path / "export").exists()


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"schema_version": 2}, UnsupportedError),
        ({"target_kind": "python_callback"}, UnsupportedError),
        ({"expected_rows": [[-1]]}, SpecError),
        ({"expected_rows": [[None]]}, SpecError),
        ({"expected_behavior": ""}, SpecError),
        ({"model_name": "orders"}, SpecError),
    ],
)
def test_bad_contract_fails_closed(
    tmp_path: Path, changes: dict[str, object], error: type[Exception]
) -> None:
    target = _contract_file(tmp_path, **changes)
    with pytest.raises(error):
        proof2test.export_pytest(WITNESS, target, tmp_path / "export")
    assert not (tmp_path / "export").exists()


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE orders",
        "SELECT amount FROM other_table",
        "SELECT amount FROM orders; DELETE FROM orders",
        "SELECT amount + 1 AS amount FROM orders",
        "SELECT * FROM orders",
        "SELECT amount FROM orders ORDER BY amount",
        "SELECT amount FROM orders JOIN orders AS other ON TRUE",
    ],
)
def test_unsupported_target_sql_fails_generated_test(tmp_path: Path, sql: str) -> None:
    out = tmp_path / "export"
    proof2test.export_pytest(WITNESS, CONTRACT, out)
    target = tmp_path / "target.sql"
    target.write_text(sql)
    result = _generated_run(out, target)
    assert result.returncode == 1
    assert "UnsupportedError" in result.stdout or "AssertionError" in result.stdout


def test_fixture_tampering_and_symlink_output_rejected(tmp_path: Path) -> None:
    out = tmp_path / "export"
    proof2test.export_pytest(WITNESS, CONTRACT, out)
    fixture = out / "fixture.json"
    fixture.write_text(fixture.read_text().replace("clean_orders", "dirty_orders"))
    run = _generated_run(out, GOOD)
    assert run.returncode == 1
    assert "generated fixture integrity mismatch" in run.stdout
    link = tmp_path / "linked"
    link.symlink_to(out, target_is_directory=True)
    with pytest.raises(proof2test.ExportConflict):
        proof2test.export_pytest(WITNESS, CONTRACT, link)
    with pytest.raises(proof2test.ExportConflict):
        proof2test.export_pytest(WITNESS, CONTRACT, link / "child")
    with pytest.raises(proof2test.ExportConflict):
        proof2test.export_pytest(WITNESS, CONTRACT, ROOT)


def test_export_omits_private_source_and_contract_notes(tmp_path: Path) -> None:
    witness = _copy_witness(tmp_path)
    data = json.loads(witness.read_text())
    data["spec"]["output_dir"] = "/synthetic-private/output"
    data["spec"]["invariant"]["rationale"] = "SYNTHETIC_PRIVATE_MARKER"
    witness.write_text(json.dumps(data))
    target = _contract_file(
        tmp_path,
        expected_behavior="SYNTHETIC_PRIVATE_MARKER is not for export.",
    )
    out = tmp_path / "export"
    proof2test.export_pytest(witness, target, out)
    fixture = (out / "fixture.json").read_text()
    assert "/synthetic-private/output" not in fixture
    assert "SYNTHETIC_PRIVATE_MARKER" not in fixture
    assert "SELECT COUNT(*) AS n FROM orders WHERE amount = -1" in fixture


def test_target_backend_exception_never_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "export"
    proof2test.export_pytest(WITNESS, CONTRACT, out)
    digest = hashlib.sha256((out / "fixture.json").read_bytes()).hexdigest()

    def broken(*_args: object) -> None:
        raise RuntimeError("synthetic DuckDB failure")

    monkeypatch.setattr(proof2test, "_target_rows", broken)
    with pytest.raises(RuntimeError, match="synthetic DuckDB failure"):
        proof2test.assert_generated_case(out / "fixture.json", GOOD, digest)


def test_cli_status_and_no_undo_witness_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "export"
    assert export_test(WITNESS, CONTRACT, "pytest", out) == 0
    assert "EXPORTED" in capsys.readouterr().out
    no_undo = ROOT / "examples/no_undo/evidence/witness.json"
    assert export_test(no_undo, CONTRACT, "pytest", out) == 5
    assert "UNSUPPORTED" in capsys.readouterr().out
    assert export_test(WITNESS, CONTRACT, "dbt", tmp_path / "dbt") == 0


def test_null_bag_and_empty_output_round_trip(tmp_path: Path) -> None:
    spec = {
        "schema_version": 1,
        "table": {
            "name": "orders",
            "columns": [{"name": "amount", "type": "INTEGER", "nullable": True, "domain": [0]}],
        },
        "max_rows": 2,
        "tests": [
            {"id": "has_row", "sql": "SELECT COUNT(*) AS n FROM orders", "op": ">=", "value": 1},
            {
                "id": "all_null",
                "sql": "SELECT COUNT(amount) AS n FROM orders",
                "op": "=",
                "value": 0,
            },
        ],
        "invariant": {
            "id": "no_null",
            "sql": "SELECT COUNT(*) AS n FROM orders WHERE amount IS NULL",
            "op": "=",
            "value": 0,
            "rationale": "The target removes NULL amounts in this synthetic fixture.",
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    witness_dir = tmp_path / "found"
    assert doppel_check(spec_path, witness_dir, machine=False) == 0
    witness = witness_dir / "witness.json"
    assert json.loads(witness.read_text())["rows"] == [[None]]
    target = _contract_file(
        tmp_path,
        expected_rows=[],
        expected_behavior="Remove NULL rows from the target output for this fixture.",
    )
    out = tmp_path / "export"
    proof2test.export_pytest(witness, target, out)
    corrected = tmp_path / "corrected.sql"
    corrected.write_text("SELECT amount FROM orders WHERE amount = 0")
    assert _generated_run(out, corrected).returncode == 0
    assert _generated_run(out, BAD).returncode == 1
    with pytest.raises(UnsupportedError):
        proof2test.export_dbt(witness, target, tmp_path / "dbt")


def test_empty_source_with_false_expected_invariant_is_rejected(tmp_path: Path) -> None:
    spec = {
        "schema_version": 1,
        "table": {
            "name": "orders",
            "columns": [{"name": "amount", "type": "INTEGER", "domain": [0]}],
        },
        "max_rows": 1,
        "tests": [
            {"id": "no_rows", "sql": "SELECT COUNT(*) AS n FROM orders", "op": "=", "value": 0}
        ],
        "invariant": {
            "id": "has_rows",
            "sql": "SELECT COUNT(*) AS n FROM orders",
            "op": ">",
            "value": 0,
            "rationale": "This empty input violates the declared has-rows invariant.",
        },
    }
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    found = tmp_path / "found"
    assert doppel_check(path, found, machine=False) == 0
    assert json.loads((found / "witness.json").read_text())["rows"] == []
    target = _contract_file(
        tmp_path,
        expected_rows=[],
        expected_behavior="An empty output cannot satisfy the declared has-rows invariant.",
    )
    with pytest.raises(SpecError, match="SQL TRUE"):
        proof2test.export_pytest(found / "witness.json", target, tmp_path / "export")


def test_duplicate_bag_nullable_unique_and_primary_key_contracts(tmp_path: Path) -> None:
    spec = {
        "schema_version": 1,
        "table": {
            "name": "orders",
            "columns": [
                {"name": "id", "type": "INTEGER", "nullable": True, "domain": [None]},
                {"name": "amount", "type": "INTEGER", "nullable": False, "domain": [-1, 0]},
            ],
            "unique": [["id"]],
        },
        "max_rows": 2,
        "tests": [
            {"id": "two_rows", "sql": "SELECT COUNT(*) AS n FROM orders", "op": ">=", "value": 2}
        ],
        "invariant": {
            "id": "no_negative",
            "sql": "SELECT COUNT(*) AS n FROM orders WHERE amount = -1",
            "op": "=",
            "value": 0,
            "rationale": "This synthetic model clamps negative amounts to zero.",
        },
    }
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec))
    witness_dir = tmp_path / "found"
    assert doppel_check(spec_path, witness_dir, machine=False) == 0
    rows = json.loads((witness_dir / "witness.json").read_text())["rows"]
    assert rows == [[None, -1], [None, -1]]
    target = _contract_file(
        tmp_path,
        expected_rows=[[None, 0], [None, 0]],
        expected_behavior="Keep two nullable-unique rows and clamp their amounts.",
    )
    out = tmp_path / "export"
    proof2test.export_pytest(witness_dir / "witness.json", target, out)
    corrected = tmp_path / "corrected.sql"
    corrected.write_text("SELECT id, GREATEST(amount, 0) AS amount FROM orders")
    assert _generated_run(out, corrected).returncode == 0
    defective = tmp_path / "defective.sql"
    defective.write_text("SELECT id, amount FROM orders")
    assert _generated_run(out, defective).returncode == 1

    spec["table"]["primary_key"] = ["id"]
    spec["table"]["columns"][0]["nullable"] = False
    spec["table"]["columns"][0]["domain"] = [1, 2]
    spec["max_rows"] = 2
    spec_path.write_text(json.dumps(spec))
    pk_dir = tmp_path / "pk_found"
    assert doppel_check(spec_path, pk_dir, machine=False) == 0
    illegal_expected = _contract_file(
        tmp_path,
        expected_rows=[[1, 0], [1, 0]],
        expected_behavior="Duplicate primary keys are forbidden.",
    )
    with pytest.raises(SpecError, match="constraints"):
        proof2test.export_pytest(pk_dir / "witness.json", illegal_expected, tmp_path / "pk_export")


@pytest.mark.parametrize(
    "template",
    [
        None,
        "SELECT amount FROM {{ ref('orders') }} JOIN {{ ref('other') }} USING (amount)",
        "SELECT amount FROM {{ ref('orders') }} ORDER BY amount",
        "SELECT amount FROM {{ source('raw', 'orders') }}",
    ],
)
def test_dbt_adapter_rejects_unsupported_model_shapes(tmp_path: Path, template: str | None) -> None:
    raw = json.loads(CONTRACT.read_text())
    if template is None:
        raw.pop("dbt_model_sql")
    else:
        raw["dbt_model_sql"] = template
    target = tmp_path / "target.json"
    target.write_text(json.dumps(raw))
    with pytest.raises(UnsupportedError):
        proof2test.export_dbt(WITNESS, target, tmp_path / "export")
    assert not (tmp_path / "export").exists()


def test_dbt_adapter_executes_defective_then_corrected(tmp_path: Path) -> None:
    dbt = os.environ.get("DATAPROOF_DBT_BIN")
    if not dbt:
        pytest.skip("local dbt Core/duckdb executable not configured")
    exported = tmp_path / "exported"
    proof2test.export_dbt(WITNESS, CONTRACT, exported)
    unit = yaml.safe_load((exported / "unit_tests.yml").read_text())["unit_tests"][0]
    assert unit["given"][0]["rows"] == [{"amount": -1}]
    assert unit["expect"]["rows"] == [{"amount": 0}]
    project = tmp_path / "project"
    models = project / "models"
    models.mkdir(parents=True)
    (project / "dbt_project.yml").write_text(
        "name: proof2test_demo\nversion: '1.0'\nconfig-version: 2\n"
        "profile: proof2test_demo\nmodel-paths: ['models']\n"
    )
    (project / "profiles.yml").write_text(
        "proof2test_demo:\n  target: dev\n  outputs:\n    dev:\n"
        f"      type: duckdb\n      path: {project / 'test.duckdb'}\n"
        "      schema: main\n      threads: 1\n"
    )
    (models / "orders.sql").write_text("SELECT CAST(NULL AS INTEGER) AS amount WHERE FALSE\n")
    (models / "unit_tests.yml").write_bytes((exported / "unit_tests.yml").read_bytes())
    model = models / "clean_orders.sql"
    environment = os.environ.copy()
    environment["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
    environment["DO_NOT_TRACK"] = "1"

    def dbt_run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [dbt, *args, "--project-dir", str(project), "--profiles-dir", str(project)],
            cwd=project,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    model.write_text("SELECT amount FROM {{ ref('orders') }}\n")
    parent = dbt_run("run", "--select", "orders")
    assert parent.returncode == 0, parent.stdout + parent.stderr
    bad = dbt_run("test", "--select", unit["name"])
    assert bad.returncode != 0, bad.stdout + bad.stderr
    assert "FAIL" in bad.stdout
    model.write_text("SELECT GREATEST(amount, 0) AS amount FROM {{ ref('orders') }}\n")
    fixed = dbt_run("test", "--select", unit["name"])
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert "PASS" in fixed.stdout
