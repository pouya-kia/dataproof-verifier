"""Finite solver/reference/DuckDB agreement for one-world obligations."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from test_doppelganger import example_spec

from dataproof_verifier.doppel_model import parse_doppel_spec
from dataproof_verifier.doppel_reference import reference_search
from dataproof_verifier.doppel_replay import validate
from dataproof_verifier.doppel_solver import search


@settings(max_examples=20, deadline=None, derandomize=True)
@given(
    domain=st.lists(st.sampled_from([-1, 0, 1]), min_size=1, max_size=3, unique=True),
    max_rows=st.integers(min_value=0, max_value=2),
    threshold=st.integers(min_value=0, max_value=2),
)
def test_solver_agrees_with_exhaustive_duckdb_reference(
    domain: list[int], max_rows: int, threshold: int
) -> None:
    raw = example_spec()
    raw["table"]["columns"][0]["domain"] = domain  # type: ignore[index]
    raw["max_rows"] = max_rows
    raw["tests"] = [
        {
            "id": "row_floor",
            "sql": "SELECT COUNT(*) AS n FROM orders",
            "op": ">=",
            "value": threshold,
        }
    ]
    spec = parse_doppel_spec(raw)
    found = search(spec)
    reference = reference_search(spec)
    mapped = "BLIND_SPOT_FOUND" if found.status == "CANDIDATE" else found.status
    assert mapped == reference.status
    if found.rows is not None:
        assert reference.rows is not None
        assert len(found.rows) == len(reference.rows)
        assert validate(spec, found.rows).valid


def test_domain_permutation_preserves_outcome_and_minimum_size() -> None:
    sizes = []
    for domain in ([-1, 0, 1], [1, -1, 0], [0, 1, -1]):
        raw = example_spec()
        raw["table"]["columns"][0]["domain"] = domain  # type: ignore[index]
        spec = parse_doppel_spec(raw)
        result = search(spec)
        assert result.status == "CANDIDATE"
        assert result.rows is not None
        assert validate(spec, result.rows).valid
        sizes.append(len(result.rows))
    assert sizes == [1, 1, 1]
