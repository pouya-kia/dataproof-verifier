from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = json.loads((ROOT / "examples/no_undo/daily_distinct.json").read_text())
CASES = json.loads((ROOT / "tests/fixtures/core_cases.json").read_text())


@pytest.fixture
def base_spec() -> dict[str, Any]:
    return deepcopy(BASE)


def case_spec(case: dict[str, Any], output: Path) -> dict[str, Any]:
    raw = deepcopy(BASE)
    raw["output_dir"] = str(output)
    raw["table"]["unique"] = case.get("unique", [])
    raw["table"]["primary_key"] = case.get("primary_key", [])
    if "view" in case:
        raw["views"] = [case["view"]]
    if "metric" in case:
        raw["metric"] = case["metric"]
    if case.get("customer_nullable"):
        raw["table"]["columns"][1]["nullable"] = True
        raw["table"]["columns"][1]["domain"].append(None)
    if case.get("amount_nullable"):
        raw["table"]["columns"][2]["nullable"] = True
        raw["table"]["columns"][2]["domain"].append(None)
    return raw
