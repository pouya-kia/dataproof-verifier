# DataProof 0.1.0a3 source candidate: bounded SQL and DataProof-100 accounting

This is an engineering coverage report, not an independent-user evaluation,
scientific performance result or published release. The original DataProof-100
ledger, holdout first runs and negative Paper 1–3 practical decisions were not
altered. Each newly admitted form is confined to the separate two-table
NoUndo finite backend unless stated otherwise. The existing one-table Z3,
Doppelgänger and Proof2Test contracts remain unchanged.

| Capability | Published `v0.1.0a1` | Unpublished `0.1.0a2` candidate | `0.1.0a3` source candidate |
| --- | --- | --- | --- |
| One-table NoUndo, Doppelgänger, Proof2Test | Bounded, shipped | Same | Same |
| Joined NoUndo | None | Two-table INNER/LEFT finite path | INNER/LEFT/RIGHT/FULL; one or two typed equality keys |
| Joined predicates/grouping | None | Restricted three-valued WHERE; up to two direct grouping columns | Same, plus restricted TIMESTAMP period grouping |
| STRING and expressions in joined path | None | None | Finite printable ASCII/binary STRING equality and grouping; guarded CASE and signed 32-bit addition/subtraction or identity INTEGER CAST in aggregate arguments |
| Nested source organization | None | None | One or two nonrecursive, projection-only CTEs and row-preserving derived tables |
| Time | DATE domains only | DATE domains only | Exact UTC-naive TIMESTAMP seconds; DAY/MONTH DATE_TRUNC grouping and period COUNT DISTINCT |
| Semantic verification | Z3 plus independent DuckDB replay | Complete Python finite search plus DuckDB original-SQL reference for joins | Same, with exhaustive tiny-world differential tests for new forms |

The joined contract remains **two tables**, at most two rows and three
columns/effective values per table, at most 500 analytical combined legal
worlds and a cooperative deadline. It does not use Z3 for joins, has no hard
process memory limit, and does not prove unbounded determinacy. Original SQL
is executed in in-memory DuckDB with external access disabled; this is not a
general hostile-SQL sandbox. The Python evaluator and DuckDB execution share
schema admission/world generation, so correlated errors remain possible.
See the exact [admitted grammar and replay contract](../bounded-join.md).

## All 100 original IDs retained

The final private, post-change 100-ID derivative is
`postchange-waved-a3-complete-100.jsonl`, SHA-256
`be7e28b7167ad60b2abc7f73d5f5151e8c3086a0ed0dae204d1d1d4a6fae6a78`.
It is a derivative of the unchanged original intake, not a new blind study.

| Cohort/outcome | Original intake | After Wave A | After Wave B | After Wave C | After Wave D |
| --- | ---: | ---: | ---: | ---: | ---: |
| Public-origin records retained | 50 | 50 | 50 | 50 | 50 |
| Original tasks fully eligible / independently solved | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Original unsupported / insufficient / not applicable | 29 / 2 / 19 | 29 / 2 / 19 | 29 / 2 / 19 | 29 / 2 / 19 | 29 / 2 / 19 |
| Authored controls retained / exercised | 50 / historical first run | 50 / 47 | 50 / 47 | 50 / 47 | 50 / 47 |
| Direct authored finite-reference agreements | historical | 28 / 28 | 28 / 28 | 28 / 28 | 28 / 28 |
| Direct authored positive serialized replays | historical | 20 | 20 | 20 | 20 |
| Changed authored outcome statuses / reference disagreements | not applicable | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

The 34 direct authored reruns plus 13 further authored controls were
post-change regression checks. Three authored cases (A22, A27, A30) remain
inadmissible, not passes. The published original evaluation describes the
original 50 source records and their denominator. The private per-ID blocker
roadmap separates missing SQL syntax from absent schema, KPI/invariant,
retention premise or other original-task contract; this summary does not
publish missing original SQL or invent those requirements. New syntax-only
compatibility and synthetic analogues do **not** count as an unchanged
original-task success.

## Concrete remaining feature boundaries

| Family | Original records with a relevant blocker in the retained intake | Why still unsupported / further prerequisite |
| --- | --- | --- |
| Three-table joins and general model graphs | L08–L10, G02, G12, G13, G29, G32, G33 | World, alias, outer-join tree, serializer and replay are exactly two-sided; independent complete three-table checking and original model contracts are missing. |
| Aggregate/filter CTEs, scalar/correlated subqueries | G01, G02, G09, G12–G14 | Row-preserving normalization no longer applies. A materialized bag IR must model NULL, empty results, scope, scalar cardinality errors and complete finite worlds. |
| Timezone-aware reporting and rolling distinct | L01, L02, L14, G03, G07, G15, G16 | Naive fixed periods are not timezone conversions or dynamic rolling frames; many original KPIs and retention premises are absent. |
| Window ranking/ordered frames | L01, G16, G21, G30 | The current retained view is an unordered grouped bag; tie, NULL ordering and frame semantics need an explicit ordered relational stage and independent oracle. |
| Mutable/incremental/engine-specific behavior | L04, L11, L12, L15, G18, G22–G33 | Requires a stateful or engine-specific obligation, not another parser admission rule. |

These sets overlap and are *relevant blockers*, not mutually exclusive source
counts or claims that one feature would make an original case eligible. The
complete 50-record denominator remains 0/50. Do not simplify a source task
to turn it into a supported synthetic example.
