"""End-to-end synthetic retention scenario with a separate DuckDB finite oracle."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import duckdb

from examples.use_cases.exchange_volume_retention.oracle import evaluate_fixture, execute, worlds

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/use_cases/exchange_volume_retention"


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "dataproof_verifier", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _normalized_world(raw: list[list[object]]) -> tuple[tuple[date, int, int], ...]:
    rows: list[tuple[date, int, int]] = []
    for day, poll_id, volume in raw:
        assert isinstance(day, str) and type(poll_id) is int and type(volume) is int
        rows.append((date.fromisoformat(day), poll_id, volume))
    return tuple(sorted(rows, key=lambda row: row[1]))


def test_independent_exhaustive_duckdb_oracle() -> None:
    result = evaluate_fixture()
    assert result["worlds"] == 16
    assert result["original_witness_pairs"] == 2
    assert result["repaired_witness_pairs"] == 0
    assert result["golden_original_view_equal"] is True
    assert result["golden_metric_values"] == [20, 15]


def test_positive_cli_witness_agrees_with_independent_duckdb(tmp_path: Path) -> None:
    spec_path = EXAMPLE / "loss.json"
    preflight = _cli("preflight", "no-undo", str(spec_path), "--json")
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    assert json.loads(preflight.stdout)["status"] == "ELIGIBLE"
    output = tmp_path / "positive"
    result = _cli("check", str(spec_path), "--output", str(output), "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "COUNTEREXAMPLE_FOUND"
    witness_path = output / "witness.json"
    replay = _cli("replay", str(witness_path))
    assert replay.returncode == 0, replay.stdout + replay.stderr
    assert "COUNTEREXAMPLE_FOUND" in replay.stdout
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        assert con.execute((output / "replay.sql").read_text()).fetchall() == [("REPLAY_OK",)]
    finally:
        con.close()
    explain = _cli("explain", str(witness_path))
    assert explain.returncode == 0, explain.stdout + explain.stderr
    witness = json.loads(witness_path.read_text())
    left = _normalized_world(witness["worlds"]["D1"])
    right = _normalized_world(witness["worlds"]["D2"])
    assert left != right and left in worlds() and right in worlds()
    spec = json.loads(spec_path.read_text())
    left_bag, left_kpi = execute(left, spec["views"][0], spec["metric"])
    right_bag, right_kpi = execute(right, spec["views"][0], spec["metric"])
    assert isinstance(left_bag, Counter) and left_bag == right_bag
    assert left_kpi != right_kpi


def test_repaired_cli_bounded_negative_agrees_with_complete_oracle(tmp_path: Path) -> None:
    spec_path = EXAMPLE / "repaired.json"
    preflight = _cli("preflight", "no-undo", str(spec_path), "--json")
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr
    output = tmp_path / "repaired"
    result = _cli("check", str(spec_path), "--output", str(output), "--json")
    assert result.returncode == 3, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "BOUNDED_NO_COUNTEREXAMPLE"
    assert json.loads((output / "result.json").read_text())["status"] == (
        "BOUNDED_NO_COUNTEREXAMPLE"
    )
    assert not (output / "witness.json").exists()
    assert evaluate_fixture()["repaired_witness_pairs"] == 0
