"""Read-only eligibility checks using the production input validators."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dataproof_verifier.doppel_model import load_doppel_spec
from dataproof_verifier.models import SpecError, UnsupportedError, load_spec
from dataproof_verifier.parser import parse_query
from dataproof_verifier.status import EXIT_CODES

_COMMON_LIMITS: dict[str, Any] = {
    "tables": 1,
    "min_rows_per_world": 0,
    "max_rows_per_world": 3,
    "columns": "1..4",
    "declared_domain_values_per_column": "1..4",
    "column_types": ["INTEGER", "DATE"],
    "aggregates": [
        "COUNT(*)",
        "COUNT(column)",
        "COUNT(DISTINCT column)",
        "SUM(integer)",
        "MIN(integer)",
        "MAX(integer)",
    ],
    "row_filter": "at most one INTEGER equality or IS NULL/IS NOT NULL predicate per query",
    "sql_dialect": "DuckDB",
    "timeout_ms": "1..30000",
    "max_memory_mb": "32..1024",
    "seed": "0..2147483647",
}


def _limits(workflow: str) -> dict[str, Any]:
    result = dict(_COMMON_LIMITS)
    if workflow == "no-undo":
        result.update({"retained_views": 1, "group_columns": 1, "scalar_kpis": 1})
    else:
        result.update({"existing_assertions": "1..4", "business_invariants": 1})
    return result


def _emit(result: dict[str, Any], machine: bool) -> None:
    if machine:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(result["status"])
        if result.get("reason"):
            print(result["reason"])
        print(result["note"])


def check(workflow: str, path: Path, machine: bool) -> int:
    """Mirror production validation, without search, SQL execution or artifact writes."""
    if workflow not in {"no-undo", "doppelganger"}:
        raise ValueError("unknown preflight workflow")
    result: dict[str, Any] = {
        "schema_version": 1,
        "workflow": workflow,
        "limits": _limits(workflow),
        "note": (
            "Static eligibility only: no solver or DuckDB execution was performed. "
            "Eligibility does not guarantee a witness, solver completion, or universal correctness."
        ),
    }
    try:
        if workflow == "no-undo":
            spec = load_spec(path)
            parse_query(spec.views[0], spec, metric=False)
            parse_query(spec.metric, spec, metric=True)
        else:
            load_doppel_spec(path)
    except UnsupportedError as exc:
        result.update(status="UNSUPPORTED", reason=str(exc))
        code = EXIT_CODES["UNSUPPORTED"]
    except (SpecError, OSError, UnicodeError, ValueError) as exc:
        result.update(status="INVALID_INPUT", reason=str(exc))
        code = EXIT_CODES["INVALID_INPUT"]
    except Exception as exc:
        result.update(
            status="INCONCLUSIVE",
            reason=f"unexpected validation error: {type(exc).__name__}",
            reason_code="VALIDATION_ERROR",
        )
        code = EXIT_CODES["INCONCLUSIVE_UNKNOWN"]
    else:
        result.update(status="ELIGIBLE", reason=None)
        code = 0
    _emit(result, machine)
    return code
