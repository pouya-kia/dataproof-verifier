# Post-baseline SQL coverage accounting: bounded INNER JOIN development slice

This document is a **separate development evaluation**. It does not amend
the [published-Wheel DataProof-100 baseline](dataproof-100-evaluation.md),
the ten-ID authored holdout, or any preregistered Paper 1–3 result. The
baseline target was `v0.1.0a1`; the changed source is explicitly versioned
`0.1.0a2.dev0` and is **unreleased**. Its precise command and finite limits
are in the [join contract](../bounded-join.md).

## Why this slice

The frozen intake contains repeated join-cardinality/fanout blockers,
including L08/L09/L10/L13 and G02/G09/G12/G13. Several of these need
outer joins, more than two models, strings, or a missing independent KPI;
they are **not** eight complete executable requirements. The selected
engineering capability is a small, explicit two-table inner equijoin
NoUndo obligation. Reporting-period distinct work was not selected:
the authored daily-versus-global distinct overlap control is already
supported, while the original time-windowed BI tasks also lack required
semantics and/or retention contracts. CASE, strings, multi-key grouping,
and mutable/incremental state likewise do not alone complete an original
obligation. The private per-ID blocker matrix preserves all 50 decisions;
no public third-party issue bodies or local-machine paths are copied here.

## Unchanged-original coverage

| Classification | Published Alpha baseline | This development slice |
| --- | ---: | ---: |
| Public-origin records in intake | 50 | 50 unchanged records reviewed |
| Eligible original obligations without rewriting | 0 | **0** |
| Original tasks fully solved and independently checked | 0 | **0** |
| Unsupported as stated | 29 | 29 |
| Insufficient specification | 2 | 2 |
| Not a complete applicable DataProof obligation | 19 | 19 |

The added command cannot accept a public record simply because it mentions
a join. An original task would also need the actual two-table inner-join SQL,
complete legal domains/constraints, one retained grouped view and scalar KPI,
and evidence that the result addresses the original decision. None of the
50 records provided that full unchanged obligation in this audit. No
researcher-authored translation or new KPI has been scored as original-task
success. The 50-record set is mixed and convenience-selected; it does not
estimate acceptance in a wider population.

## What was added and checked

The new `join` subcommands validate a restricted two-table schema and two
SELECTs, perform complete finite Python bag-world search, cross-check the
classification with original-SQL DuckDB execution over the same worlds,
and serialize/replay a positive witness. A conservative 500 analytical
combined-world cap, two rows per table, and explicit timeout status prevent
truncated search being mislabeled as a finite negative. Original one-table
Z3, Doppelgänger and Proof2Test commands are unchanged; the development
package version prevents confusion with the frozen Alpha Wheel.

Two **newly authored synthetic** examples are included. `fanout.json`
confirms a positive: both worlds retain grouped joined-row count 2, while
`COUNT(DISTINCT order.id)` is 1 versus 2. Independent DuckDB replay returns
`REPLAY_OK`. `keyed_negative.json` adds primary keys and the Python and
DuckDB finite references both exhaust eight legal combined worlds with no
counterexample; this is not a universal theorem. These examples are not
adaptations of original external SQL. They also illustrate a simpler
alternative: if raw inputs remain, a direct SQL `COUNT(DISTINCT ...)` may
answer the KPI without DataProof.

Adversarial engineering tests cover NULL join-key nonmatching, nullable
grouping, bag duplicates, COUNT DISTINCT, SUM/MIN/MAX, DATE keys,
nullable-UNIQUE and primary-key behavior, empty worlds, rejected joins and
clauses, result/replay tampering, identifier and output-path safety,
timeouts/backend errors, reference disagreement, deterministic witnesses,
and Python/DuckDB differential properties. Those tests are synthetic
correctness controls, not external utility evidence. A separately installed
development Wheel was checked with the positive join path and the old
NoUndo/Doppelgänger positive/replay paths. Five unchanged authored
DataProof-100 controls (A01, A17, A21, A28, A31) retained their baseline
positive statuses and independently replayed under the development Wheel;
this is a **post-change engineering recheck**, not a rerun of the frozen
ten-ID holdout as a new blind trial. A17 remains positive: its original
bounded-negative catalog prediction was wrong.

## Limits and interpretation

The Python and DuckDB evaluators are separately implemented for SQL output
semantics, but they share the admission parser, schema constraints and world
enumeration. Agreement is not a mathematical proof of those shared layers.
The join command has no Z3 encoding, no witness-minimality or performance
claim, no OS-enforced memory ceiling, and no hard interruption of a single
in-flight DuckDB call. It deliberately rejects outer/implicit/multiple
joins, filters, CTEs, string columns, dbt graphs and production access.
An unsupported or malformed original remains in the denominator; no
partial synthetic success rescues it. The historical P1/P2/Phase 6C
primary practical gates remain failed.

The public examples and new tests can reproduce the **new feature checks**
from this development source. The complete original 100-case first-run
audit is still not publicly reproducible: its local case ledger, raw
records, source cache and full authored fixtures remain private pending
privacy, redistribution-rights and methodological review. No private
artifact hash is represented as a publicly available dataset.
The [machine-readable post-change summary](bounded-join-summary.json)
records the two new example hashes, finite work counts, and five selected
unchanged authored-control rechecks without copying private raw output.
