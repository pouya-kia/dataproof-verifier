"""End-to-end first-run demonstration and safe output behavior."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dataproof_verifier import demo
from dataproof_verifier.demo import exhaustive_counts, specification


def test_independent_oracle_and_contract() -> None:
    assert exhaustive_counts() == (16, 2, 0)
    original = specification(False)
    repaired = specification(True)
    assert original["table"] == repaired["table"]
    assert original["metric"] == repaired["metric"]
    assert "MAX(volume_24h_kusdt)" not in original["views"][0]
    assert "MAX(volume_24h_kusdt)" in repaired["views"][0]


def test_installed_module_demo_and_no_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "first-run"
    cmd = [sys.executable, "-m", "dataproof_verifier", "demo", "--output-dir", str(output)]
    first = subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=180)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "Independent DuckDB replay.sql: REPLAY_OK" in first.stdout
    assert "BOUNDED_NO_COUNTEREXAMPLE (exit 3)" in first.stdout
    assert "16 legal worlds; 2 original loss pairs; 0 repaired pairs" in first.stdout
    witness = json.loads((output / "loss" / "witness.json").read_text())
    assert witness["status"] == "COUNTEREXAMPLE_FOUND"
    assert witness["metric_values"][0] != witness["metric_values"][1]
    result = json.loads((output / "repair" / "result.json").read_text())
    assert result["status"] == "BOUNDED_NO_COUNTEREXAMPLE"
    assert not (output / "repair" / "witness.json").exists()
    marker = output / "user-note.txt"
    marker.write_text("keep me")
    second = subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=10)
    assert second.returncode == 2
    assert marker.read_text() == "keep me"


def test_demo_rejects_symlink_output(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    proc = subprocess.run(
        [sys.executable, "-m", "dataproof_verifier", "demo", "--output-dir", str(link)],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert proc.returncode == 2
    assert not list(target.iterdir())


@pytest.mark.parametrize("status", ["UNSUPPORTED", "INVALID_INPUT", "INCONCLUSIVE"])
def test_demo_does_not_relabel_unexpected_results(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    monkeypatch.setattr(demo, "_call", lambda _args, _code: json.dumps({"status": status}))
    with pytest.raises(RuntimeError, match=f"Expected ELIGIBLE, got {status}"):
        demo._status(["unused"], "ELIGIBLE", 0)
