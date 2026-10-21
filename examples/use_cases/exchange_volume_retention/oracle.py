"""Independent DuckDB/itertools oracle for the 16-world synthetic retention example.

This deliberately does not import DataProof's parser, evaluator or world generator.
The fixed finite universe is part of this example, not a general-purpose oracle.
"""

from __future__ import annotations

import itertools
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import duckdb

HERE = Path(__file__).resolve().parent
Row = tuple[date, int, int]
World = tuple[Row, ...]
Bag = Counter[tuple[object, ...]]


def worlds() -> tuple[World, ...]:
    day = date(2026, 10, 1)
    result: list[World] = [()]
    for size in (1, 2):
        for ids in itertools.combinations((1, 2), size):
            for volumes in itertools.product((10, 15, 20), repeat=size):
                result.append(
                    tuple(
                        (day, poll_id, volume) for poll_id, volume in zip(ids, volumes, strict=True)
                    )
                )
    assert len(result) == 16 and len(set(result)) == 16
    return tuple(result)


def execute(world: World, view_sql: str, metric_sql: str) -> tuple[Bag, int | None]:
    """Execute unchanged scenario SQL, once per world, in an isolated connection."""
    con = duckdb.connect(":memory:", config={"enable_external_access": "false"})
    try:
        con.execute(
            "CREATE TABLE exchange_volume_polls ("
            "day DATE NOT NULL, poll_id INTEGER PRIMARY KEY, volume_24h_kusdt INTEGER NOT NULL)"
        )
        if world:
            con.executemany("INSERT INTO exchange_volume_polls VALUES (?, ?, ?)", world)
        view = Counter(tuple(row) for row in con.execute(view_sql).fetchall())
        scalar_rows = con.execute(metric_sql).fetchall()
        assert len(scalar_rows) == 1 and len(scalar_rows[0]) == 1
        scalar = scalar_rows[0][0]
        assert scalar is None or type(scalar) is int
        return view, scalar
    finally:
        con.close()


def _load(name: str) -> dict[str, Any]:
    value = json.loads((HERE / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _world(raw: list[list[object]]) -> World:
    output: list[Row] = []
    for day, poll_id, volume in raw:
        assert isinstance(day, str) and type(poll_id) is int and type(volume) is int
        output.append((date.fromisoformat(day), poll_id, volume))
    return tuple(output)


def evaluate_fixture() -> dict[str, object]:
    loss = _load("loss.json")
    repaired = _load("repaired.json")
    golden = _load("golden_worlds.json")
    universe = worlds()
    metric = loss["metric"]
    assert metric == repaired["metric"]
    original = [execute(world, loss["views"][0], metric) for world in universe]
    fixed = [execute(world, repaired["views"][0], metric) for world in universe]
    positive_pairs = [
        (i, j)
        for i, j in itertools.combinations(range(len(universe)), 2)
        if original[i][0] == original[j][0] and original[i][1] != original[j][1]
    ]
    repaired_pairs = [
        (i, j)
        for i, j in itertools.combinations(range(len(universe)), 2)
        if fixed[i][0] == fixed[j][0] and fixed[i][1] != fixed[j][1]
    ]
    a, b = _world(golden["world_A"]), _world(golden["world_B"])
    expected_view = Counter(
        (date.fromisoformat(day), count, total)
        for day, count, total in golden["expected_retained_view_both"]
    )
    a_view, a_metric = execute(a, loss["views"][0], metric)
    b_view, b_metric = execute(b, loss["views"][0], metric)
    assert a in universe and b in universe
    assert a_view == b_view == expected_view
    assert a_metric == golden["expected_metric_A"] == 20
    assert b_metric == golden["expected_metric_B"] == 15
    assert (
        execute(a, repaired["views"][0], metric)[0] != execute(b, repaired["views"][0], metric)[0]
    )
    return {
        "worlds": len(universe),
        "original_witness_pairs": len(positive_pairs),
        "repaired_witness_pairs": len(repaired_pairs),
        "golden_original_view_equal": a_view == b_view,
        "golden_metric_values": [a_metric, b_metric],
        "positive_example_pair_indices": list(positive_pairs[0]) if positive_pairs else None,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate_fixture(), indent=2, sort_keys=True))
