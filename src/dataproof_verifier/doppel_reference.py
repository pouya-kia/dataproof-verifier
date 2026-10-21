"""Tiny exhaustive reference using direct DuckDB SQL, without Z3 evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from dataproof_verifier.doppel_model import DoppelSpec
from dataproof_verifier.doppel_replay import validate
from dataproof_verifier.models import Row
from dataproof_verifier.reference_enumerator import all_worlds


@dataclass(frozen=True)
class DoppelReferenceResult:
    status: str
    worlds_checked: int
    test_passing_worlds: int
    rows: tuple[Row, ...] | None


def reference_search(spec: DoppelSpec) -> DoppelReferenceResult:
    worlds = all_worlds(spec.table)
    passing = 0
    witness: tuple[Row, ...] | None = None
    for rows in worlds:
        checked = validate(spec, rows)
        if all(test.truth is True for test in checked.tests):
            passing += 1
            if checked.valid and witness is None:
                witness = rows
    status = (
        "BLIND_SPOT_FOUND"
        if witness is not None
        else "BOUNDED_NO_BLIND_SPOT"
        if passing
        else "INCONSISTENT_TESTS"
    )
    return DoppelReferenceResult(status, len(worlds), passing, witness)
