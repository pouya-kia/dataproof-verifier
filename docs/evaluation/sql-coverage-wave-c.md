# Advanced SQL Wave C — row-preserving nested sources

The separate finite two-table NoUndo backend now admits projection-only
derived sources and up to two nonrecursive, dependency-ordered CTEs. An inner
source may only select one to three direct source columns with optional
aliases. A CTE can project from a declared table or a prior CTE. No inner
filter, aggregate, DISTINCT, computed projection, ordering or limit is
admitted. Each admitted inner SELECT preserves source bag rows exactly;
typed outer references resolve through the projection map to base columns.
DuckDB executes the original SQL, not the normalized tree.

This is a useful source-organization feature, **not** support for arbitrary
subqueries or multi-stage aggregation. Scalar and uncorrelated subqueries,
correlation, filtered/aggregating CTEs and recursion remain rejected. They
would require materialized intermediate bags with independently checked
NULL, empty-input, scope and cardinality semantics, plus revised search and
replay contracts. In particular, a scalar subquery returning more than one
row must not be approximated as an arbitrary first row.

The unchanged DataProof-100 ledger was reassessed into the private post-change
derivative `postchange-wavec-a3-complete-100.jsonl` (SHA-256
`551bbcf28216d0e220d6c163300948828f05f457835a666e6f9f5c112c47e927`).
All 100 IDs are retained. Thirty-four direct authored obligations were run:
28/28 cases with a complete finite reference agreed, 20 positive serializations
replayed, and no status changed. Thirteen other authored controls were run,
for 47/50 authored cases exercised. The same three inadmissible authored cases
remain unrun. No original public-origin SQL task became fully eligible or
solved: **0/50**. These repeats are post-change engineering checks, not new
blind evidence. Existing Paper 1–3 negative primary results remain unchanged.
This development source is not the published `v0.1.0a1` release.
