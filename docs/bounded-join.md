# Bounded two-table join check (unreleased development)

This is a separate NoUndo workflow for one narrow Data Engineering question:
can two legal tiny databases produce the **same retained grouped aggregate
bag** over a restricted equijoin but different values for a scalar downstream KPI? It is
motivated by repeated join-cardinality/fanout blockers in the
[DataProof-100 evaluation](evaluation/dataproof-100-evaluation.md). It does
**not** run the original multi-model dbt or BI tasks in that intake. The
published `v0.1.0a1` Wheel does **not** contain this command. The current
source is `0.1.0a3.dev0` development work, not a published release.

## Use from this development source

After an editable installation in a disposable environment:

```sh
dataproof-verifier join preflight examples/join/fanout.json
dataproof-verifier join check examples/join/fanout.json --output artifacts/my-new-join-run
dataproof-verifier join replay artifacts/my-new-join-run/witness.json
dataproof-verifier join explain artifacts/my-new-join-run/witness.json
dataproof-verifier join preflight examples/join/left_missing_match.json
dataproof-verifier join preflight examples/join/projection_cte.json
dataproof-verifier join preflight examples/join/monthly_timestamp_distinct.json
```

`--output` **must name a new directory** for each run. The command refuses
an existing directory rather than deleting any existing file. The keyed
bounded-negative control is `examples/join/keyed_negative.json`; it exits 3
and creates only a result record, not a witness.

## Exact contract

- Exactly two distinct local source tables, in declared order. Each has 1–3
  lowercase simple-identifier columns of finite `INTEGER`, `DATE`, restricted
  `STRING`, or restricted `TIMESTAMP` type,
  at most three **effective** values per column including an admitted NULL,
  and 0–2 rows per world. Bags preserve duplicates. Optional per-table
  `PRIMARY KEY` and nullable `UNIQUE` constraints follow the existing schema
  validator. There are no foreign keys.
- Exactly one retained grouped query and one scalar metric query. Both are
  DuckDB `SELECT` statements reading the two declared tables with explicit,
  distinct aliases and **one explicit INNER, LEFT, RIGHT, or FULL [OUTER] JOIN**
  on one or two distinct equalities of direct, alias-qualified columns of the
  same declared type, with one column from each source per equality. NULL
  join keys do not match. LEFT/RIGHT/FULL preserve unmatched bag-row instances
  with a NULL-generated tuple on the missing side. Duplicate source rows remain
  duplicate joined rows; genuine NULL and missing-match NULL may have the same
  projected value. The view and metric may choose join forms independently.
  A source may be a projection-only, row-preserving derived table or reference
  up to two nonrecursive CTE definitions with earlier-CTE dependencies. Each
  inner SELECT projects one to three direct source columns, optionally
  renaming them; it may not filter, aggregate, deduplicate, order, limit,
  compute expressions or read another table. Source aliases and projected
  column scope are checked; the finite evaluator resolves these renames to
  base columns, while DuckDB executes the unchanged original SQL. This is
  bag-preserving AST normalization, not general subquery evaluation. Neither
  query has an additional join or any other clause except an optional
  restricted `WHERE` and the view's
  one or two direct, distinct `GROUP BY` columns. Each query may use its own
  `WHERE`. Admitted predicates combine `AND`, `OR`, `NOT`, parentheses,
  direct-column `IS NULL`/`IS NOT NULL`, and direct comparisons
  `=`, `!=`, `<`, `<=`, `>`, `>=` between same-type INTEGER/DATE columns or an INTEGER
  column and signed 32-bit integer literal. STRING columns additionally admit
  `=` and `!=` against other STRING columns or a restricted STRING literal.
  SQL UNKNOWN filters out a row; Boolean
  operators follow SQL three-valued logic. DATE columns compare only with
  other DATE columns. STRING domains/literals are 1–32 printable ASCII characters;
  matching and grouping use DuckDB's default binary, case-sensitive semantics.
  `COLLATE`, locale comparisons, empty strings, non-ASCII text, string ordering,
  non-identity casts and general functions remain unsupported. STRING is admitted **only**
  in this separate finite join workflow, not the one-table Z3, Doppelgänger or
  Proof2Test contracts.
- The view projects every grouped column once and at least one named direct
  aggregate. The metric projects exactly one named scalar aggregate.
  Admitted aggregates are `COUNT(*)`, `COUNT(column)`,
  `COUNT(DISTINCT expression)`, and integer-valued `SUM`, `MIN`, `MAX`.
  Aggregate arguments may be direct columns, admitted finite literals, a
  searched or simple `CASE` (one to three arms, same-type INTEGER or STRING
  branches, optional implicit NULL default), identity `CAST(... AS INTEGER)`,
  and INTEGER addition/subtraction. Arithmetic is
  rejected if the declared finite input-domain interval could overflow signed
  32-bit INTEGER at any subexpression. Division, multiplication, mixed-type
  coercion, `TRY_CAST`, STRING casts and non-identity casts remain unsupported.
  `COUNT(expression)` and
  `COUNT(DISTINCT expression)` admit STRING-valued expressions and ignore NULL;
  they also admit direct TIMESTAMP columns. `DATE_TRUNC('day'|'month',
  alias.timestamp_column)` may be projected and grouped; it returns a
  TIMESTAMP at midnight on the corresponding UTC-naive calendar boundary.
  A TIMESTAMP domain must use exact `YYYY-MM-DDTHH:MM:SS` strings without
  an offset, fractional second or leap-second value. Values are interpreted
  as UTC-naive timestamps, not converted from a local timezone. Comparisons
  between TIMESTAMP columns of the same type are supported in `WHERE`;
  TIMESTAMP literals and implicit DATE/TIMESTAMP conversions are not.
  This can represent finite day/month reporting periods with `COUNT DISTINCT`,
  but not rolling windows or timezone-aware reporting.
  `SUM`/extrema require INTEGER-valued expressions.
  SQL grouping treats each NULL group-key component as one group; empty grouped output is
  an empty bag. Scalar `COUNT` of empty join output is 0, while `SUM`/extrema
  are NULL. With LEFT JOIN, `COUNT(*)` includes unmatched left rows whereas
  `COUNT(right_column)` does not. RIGHT/FULL follow the symmetric unmatched-row
  rules. A `WHERE` condition is applied **after** null-extension; `ON` accepts
  only the one or two direct equalities, not arbitrary predicates or a rewritten
  `WHERE`. Output-column order matters; output-row order does not.
- The analytical upper bound on **combined** two-table legal worlds must be
  at most 500, computed before key filtering. This conservative cap may
  reject a constrained schema with fewer actual worlds. Two databases are
  drawn from that identical finite legal-world set. The Python evaluator
  searches its complete bag enumeration; independently, DuckDB executes the
  original admitted SQL across the same worlds. The shared parser, schema
  and world enumerator are correlated-error risks.
- `timeout_ms` is 1–30,000 and applies to the full search plus reference
  comparison through cooperative deadline checks. A single in-flight
  DuckDB call is not preempted, and there is **no OS-enforced process-memory
  limit**. The 500-world cap bounds planned enumeration; engine failures,
  timeout, reference disagreement and incomplete checks fail closed as
  `INCONCLUSIVE`. No Z3 claim or optimization claim is made for this backend.

A positive result needs equal **unordered view bags**, different nullable-
aware metric values, a fresh DuckDB check of the candidate, and a validated
serialized `witness.json` plus executable `replay.sql`. The sidecars carry
canonical spec/world hashes and an input-file digest. `join replay` rechecks
the original SQL in DuckDB; `join explain` reports labeled source bags and
KPI values only after this check. The witness is deterministic for the
declared enumeration order but is **not claimed minimal**. A
`BOUNDED_NO_COUNTEREXAMPLE` is emitted only after *both* Python and DuckDB
complete the declared finite enumeration; it is not universal SQL
determinacy. The status, backend, analytical bound and work counts are in
`result.json` and `--json` output. `UNSUPPORTED` and `INVALID_INPUT` are
rejected before any output directory is created.

These hashes and the local ownership record check internal consistency, not
external authenticity. Once the original input file is unavailable, a
self-consistently rewritten bundle cannot be tied to that file without an
independently trusted digest.

The fanout example is authored synthetic evidence: one database has one distinct
order joined to two duplicate customer rows; another has two distinct orders
joined to one customer row. Both retain two joined rows, but the distinct
order KPI is 1 versus 2. Ordinary `COUNT(DISTINCT ...)` on available raw
sources can answer that KPI more simply; NoUndo becomes relevant only when
the declared retained summary is all that remains. The new synthetic
`left_missing_match.json` shows that unmatched and matched orders can retain
the same grouped `COUNT(*)` while `COUNT(c.cid)` differs. Neither example
establishes that raw data were deleted in any external workflow.

Unsupported forms fail closed: implicit/comma/cross/semi/anti joins,
multiple joins or retained views, non-equality `ON`, more than two join keys,
unsupported string expressions, timezone conversions and DATE/TIMESTAMP casts,
more than two grouping columns, `HAVING`, windows (including `ROW_NUMBER`,
`RANK`, `DENSE_RANK` and windowed aggregates), `ORDER BY`, scalar or
correlated subqueries, filtering/aggregate CTEs, recursive CTEs,
multi-stage aggregation, arbitrary SQL dialects, writes, UDFs, production database access and
dbt model graphs. The existing one-table NoUndo, Doppelgänger and Proof2Test
contracts remain unchanged. No public-origin task in the frozen 50-record
intake has been counted as solved by this new synthetic capability.
