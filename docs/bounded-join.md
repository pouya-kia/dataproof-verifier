# Bounded two-table join check (unreleased development)

This is a separate NoUndo workflow for one narrow Data Engineering question:
can two legal tiny databases produce the **same retained grouped aggregate
bag** over an inner join but different values for a scalar downstream KPI? It is
motivated by repeated join-cardinality/fanout blockers in the
[DataProof-100 evaluation](evaluation/dataproof-100-evaluation.md). It does
**not** run the original multi-model dbt or BI tasks in that intake. The
published `v0.1.0a1` Wheel does **not** contain this command. Development
source is marked `0.1.0a2.dev0`, not a new release.

## Use from this development source

After an editable installation in a disposable environment:

```sh
dataproof-verifier join preflight examples/join/fanout.json
dataproof-verifier join check examples/join/fanout.json --output artifacts/my-new-join-run
dataproof-verifier join replay artifacts/my-new-join-run/witness.json
dataproof-verifier join explain artifacts/my-new-join-run/witness.json
```

`--output` **must name a new directory** for each run. The command refuses
an existing directory rather than deleting any existing file. The keyed
bounded-negative control is `examples/join/keyed_negative.json`; it exits 3
and creates only a result record, not a witness.

## Exact contract

- Exactly two distinct local source tables, in declared order. Each has 1–3
  lowercase simple-identifier columns of finite `INTEGER` or `DATE` type,
  at most three **effective** values per column including an admitted NULL,
  and 0–2 rows per world. Bags preserve duplicates. Optional per-table
  `PRIMARY KEY` and nullable `UNIQUE` constraints follow the existing schema
  validator. There are no foreign keys.
- Exactly one retained grouped query and one scalar metric query. Both are
  DuckDB `SELECT` statements reading the two declared tables with explicit,
  distinct aliases and **one explicit INNER JOIN** on equality of direct,
  alias-qualified columns of the same declared type. NULL join keys do not
  match. Neither query has a `WHERE`, CTE, additional join, derived source,
  or any other clause except the view's single direct `GROUP BY` column.
- The view projects that grouped column once and at least one named direct
  aggregate. The metric projects exactly one named scalar aggregate.
  Admitted aggregates are `COUNT(*)`, `COUNT(column)`,
  `COUNT(DISTINCT column)`, and integer-column `SUM`, `MIN`, `MAX`.
  SQL grouping treats NULL group keys as one group; empty grouped output is
  an empty bag. Scalar `COUNT` of empty join output is 0, while `SUM`/extrema
  are NULL. Output-column order matters; output-row order does not.
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

The example is authored synthetic evidence: one database has one distinct
order joined to two duplicate customer rows; another has two distinct orders
joined to one customer row. Both retain two joined rows, but the distinct
order KPI is 1 versus 2. Ordinary `COUNT(DISTINCT ...)` on available raw
sources can answer that KPI more simply; NoUndo becomes relevant only when
the declared retained summary is all that remains. This example does not
establish that raw data were deleted in any external workflow.

Unsupported forms fail closed: implicit/comma/cross/outer/semi/anti joins,
multiple joins or retained views, compound `ON`, string keys, expressions,
filters, multiple grouping columns, `HAVING`, windows, `ORDER BY`, subqueries,
CTEs, arbitrary SQL dialects, writes, UDFs, production database access and
dbt model graphs. The existing one-table NoUndo, Doppelgänger and Proof2Test
contracts remain unchanged. No public-origin task in the frozen 50-record
intake has been counted as solved by this new synthetic capability.
