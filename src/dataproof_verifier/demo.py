"""Installed, offline demonstration of finite information loss.

The independent 16-world check below uses DuckDB SQL and itertools, not the
DataProof solver, parser, or finite reference enumerator.
"""

from __future__ import annotations

import itertools
import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

DAY = "2026-10-01"
TABLE = "exchange_volume_polls"
METRIC = f"SELECT MAX(volume_24h_kusdt) AS peak_reported_24h_volume FROM {TABLE}"
VIEW = (
    f"SELECT day, COUNT(*) AS sample_count, SUM(volume_24h_kusdt) "
    f"AS sampled_volume_total FROM {TABLE} GROUP BY day"
)
REPAIRED_VIEW = (
    f"SELECT day, COUNT(*) AS sample_count, SUM(volume_24h_kusdt) "
    f"AS sampled_volume_total, MAX(volume_24h_kusdt) AS retained_peak "
    f"FROM {TABLE} GROUP BY day"
)


def specification(repaired: bool) -> dict[str, Any]:
    return {
        "table": {
            "name": TABLE,
            "columns": [
                {"name": "day", "type": "DATE", "nullable": False, "domain": [DAY]},
                {"name": "poll_id", "type": "INTEGER", "nullable": False, "domain": [1, 2]},
                {
                    "name": "volume_24h_kusdt",
                    "type": "INTEGER",
                    "nullable": False,
                    "domain": [10, 15, 20],
                },
            ],
            "primary_key": ["poll_id"],
            "unique": [],
        },
        "views": [REPAIRED_VIEW if repaired else VIEW],
        "metric": METRIC,
        "max_rows": 2,
        "timeout_ms": 10000,
        "seed": 19,
    }


def _call(args: list[str], code: int) -> str:
    result = subprocess.run(args, text=True, capture_output=True, check=False, timeout=60)
    if result.returncode != code:
        raise RuntimeError(
            f"Expected exit {code}, got {result.returncode}: {args[3:]}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout


def _status(args: list[str], expected: str, code: int) -> None:
    payload = json.loads(_call(args, code))
    if payload.get("status") != expected:
        raise RuntimeError(f"Expected {expected}, got {payload.get('status')}")


def _query(
    world: tuple[tuple[date, int, int], ...], view: str
) -> tuple[Counter[tuple[object, ...]], int | None]:
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute(
            "CREATE TABLE exchange_volume_polls (day DATE NOT NULL, "
            "poll_id INTEGER PRIMARY KEY, volume_24h_kusdt INTEGER NOT NULL)"
        )
        if world:
            con.executemany("INSERT INTO exchange_volume_polls VALUES (?, ?, ?)", world)
        rows = Counter(tuple(row) for row in con.execute(view).fetchall())
        metric = con.execute(METRIC).fetchone()
        if metric is None or len(metric) != 1:
            raise RuntimeError("DuckDB metric did not return a scalar")
        value = metric[0]
        if value is not None and type(value) is not int:
            raise RuntimeError("Unexpected metric type")
        return rows, value
    finally:
        con.close()


def exhaustive_counts() -> tuple[int, int, int]:
    day = date.fromisoformat(DAY)
    worlds: list[tuple[tuple[date, int, int], ...]] = [()]
    for size in (1, 2):
        for ids in itertools.combinations((1, 2), size):
            for values in itertools.product((10, 15, 20), repeat=size):
                worlds.append(tuple((day, i, v) for i, v in zip(ids, values, strict=True)))
    original = [_query(world, VIEW) for world in worlds]
    repaired = [_query(world, REPAIRED_VIEW) for world in worlds]

    def count_pairs(results: list[tuple[Counter[tuple[object, ...]], int | None]]) -> int:
        return sum(
            results[i][0] == results[j][0] and results[i][1] != results[j][1]
            for i, j in itertools.combinations(range(len(results)), 2)
        )

    return len(worlds), count_pairs(original), count_pairs(repaired)


def _run(output: Path) -> None:
    cli = [sys.executable, "-m", "dataproof_verifier"]
    loss_spec, repair_spec = output / "loss-spec.json", output / "repair-spec.json"
    loss_spec.write_text(json.dumps(specification(False), indent=2), encoding="utf-8")
    repair_spec.write_text(json.dumps(specification(True), indent=2), encoding="utf-8")
    print("Retained: day, sample COUNT, SUM of rolling-24h reported-volume snapshots.")
    print("Question: can that summary recover the largest reported snapshot (MAX)?")
    for spec in (loss_spec, repair_spec):
        _status(cli + ["preflight", "no-undo", str(spec), "--json"], "ELIGIBLE", 0)
    print("Both finite contracts: ELIGIBLE")
    loss = output / "loss"
    _status(
        cli + ["check", str(loss_spec), "--output", str(loss), "--json"], "COUNTEREXAMPLE_FOUND", 0
    )
    witness = loss / "witness.json"
    _status(cli + ["replay", str(witness), "--json"], "COUNTEREXAMPLE_FOUND", 0)
    explanation = _call(cli + ["explain", str(witness)], 0)
    for line in explanation.splitlines():
        if not line.startswith(("Evidence:", "Result:", "Replay SQL:", "Recheck:")):
            print(line)
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        replay = con.execute((loss / "replay.sql").read_text(encoding="utf-8")).fetchall()
    finally:
        con.close()
    if replay != [("REPLAY_OK",)]:
        raise RuntimeError(f"Separate DuckDB replay failed: {replay}")
    print("Independent DuckDB replay.sql: REPLAY_OK")
    repair = output / "repair"
    _status(
        cli + ["check", str(repair_spec), "--output", str(repair), "--json"],
        "BOUNDED_NO_COUNTEREXAMPLE",
        3,
    )
    if (repair / "witness.json").exists():
        raise RuntimeError("A bounded-negative result unexpectedly has a witness")
    count = exhaustive_counts()
    if count != (16, 2, 0):
        raise RuntimeError(f"Independent finite oracle disagreed: {count}")
    print("Repaired summary adds MAX: BOUNDED_NO_COUNTEREXAMPLE (exit 3).")
    print("DuckDB exhaustive oracle: 16 legal worlds; 2 original loss pairs; 0 repaired pairs.")
    print("Golden illustration: (2026-10-01, 2, 30) retained in both; peaks 20 vs 15.")
    print("PASS: finite synthetic information loss and bounded repair verified.")
    print("Not actual daily traded volume, a production defect, or a universal proof.")
    print("Evidence files: loss/witness.json, loss/replay.sql, repair/result.json")


def run(output_dir: Path | None) -> int:
    try:
        if output_dir is None:
            with tempfile.TemporaryDirectory(prefix="dataproof-demo-") as name:
                _run(Path(name))
            print("Temporary artifacts removed. Use --output-dir to preserve them.")
            return 0
        if output_dir.is_symlink() or output_dir.exists():
            print("Demo output directory must not already exist.", file=sys.stderr)
            return 2
        output_dir.mkdir(parents=True)
        _run(output_dir)
        print(f"Preserved artifacts in: {output_dir}")
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"DEMO FAILED: {exc}", file=sys.stderr)
        return 1
    return 0
