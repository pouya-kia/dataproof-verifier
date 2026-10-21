"""Versioned authored full-contract tasks; never count as original-user successes."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from pathlib import Path

import pytest

from dataproof_verifier import join_cli, join_reference, replay
from dataproof_verifier.join_model import all_join_worlds, parse_join_spec
from dataproof_verifier.relational_core import evaluate
from dataproof_verifier.relational_pipeline import admit_query

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "examples/full_contract/tasks.json"
TASKS = json.loads(MANIFEST.read_text(encoding="utf-8"))["tasks"]


def _input(task: dict[str, str]) -> dict[str, object]:
    path = ROOT / task["case"]
    assert path.is_file() and not path.is_symlink()
    content = path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == task["sha256"]
    raw = json.loads(content)
    if "view_sql" in task:
        raw["view"] = task["view_sql"]
    if "metric_sql" in task:
        raw["metric"] = task["metric_sql"]
    return raw


def test_full_contract_manifest_identity_and_provenance() -> None:
    metadata = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert metadata["suite_version"] == 1
    assert metadata["origin"] == "RESEARCHER_AUTHORED_ENGINEERING"
    assert len(TASKS) == 12
    assert {task["id"] for task in TASKS} == {f"FC{index:02d}" for index in range(1, 13)}
    for task in TASKS:
        assert task["decision"] and task["simpler"]
        assert task["hypothesis"] in {"SAT", "BOUNDED_NEGATIVE"}
        _input(task)


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task["id"])
def test_authored_full_contract_task(
    task: dict[str, str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = _input(task)
    spec = parse_join_spec(raw)
    view = admit_query(spec.view_sql, spec, metric=False)
    metric = admit_query(spec.metric_sql, spec, metric=True)
    worlds = all_join_worlds(spec)
    assert 0 < len(worlds) <= 500

    # DuckDB executes each admitted original SQL over every declared legal
    # world. The plan is compared independently of the search stopping point.
    con = replay._connection()
    try:
        for table in spec.tables:
            con.execute(replay._create_table(table))
        for world in worlds:
            db_view, db_metric = join_reference.evaluate_duckdb(con, spec, world)
            assert Counter(evaluate(view, spec, world)) == Counter(db_view)
            assert evaluate(metric, spec, world) == ((db_metric,),)
    finally:
        con.close()

    reference = join_reference.search_duckdb(spec, time.monotonic() + 30)
    assert reference.status != "INCONCLUSIVE"
    expected = (
        "COUNTEREXAMPLE_FOUND" if task["hypothesis"] == "SAT" else "BOUNDED_NO_COUNTEREXAMPLE"
    )
    assert reference.status == expected
    source = tmp_path / "input.json"
    source.write_text(json.dumps(raw), encoding="utf-8")
    output = tmp_path / "result"
    assert join_cli.preflight(source, True) == 0
    assert join_cli.check(source, output, True) == (0 if reference.witness else 3)
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == reference.status
    assert result["analytical_world_bound"] <= 500
    if reference.witness is None:
        assert reference.worlds_checked == len(worlds)
        assert result["bounded_exhaustion_complete"] is True
        assert not (output / "witness.json").exists()
    else:
        assert join_reference.check_pair_duckdb(spec, reference.witness)[0]
        assert join_cli.replay_witness(output / "witness.json", True) == 0
    capsys.readouterr()
