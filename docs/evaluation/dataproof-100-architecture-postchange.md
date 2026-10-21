# DataProof-100 after the relational-core and aggregate-CTE changes

Status: **aggregate-only continuity report; per-ID reassessment not completed**.
The immutable private 100-ID ledger and source snapshots cited by the earlier
[evaluation](dataproof-100-evaluation.md) and [a3 report](sql-coverage-a3-candidate.md)
were not available at their recorded local paths for this development run.
This page does not reconstruct missing original SQL, task requirements, first
runs or private observations. The new production code and synthetic example
cannot themselves establish a revised original-task count.

| Cohort / fact | Preserved historical baseline | New assessment |
| --- | ---: | --- |
| Public-origin identities | 50 | 50 IDs retained in prior reports; no per-ID source re-execution |
| Historical unchanged original tasks fully eligible / solved | 0 / 0 | **NOT REASSESSED**, not promoted |
| Historical unsupported / insufficient / not applicable | 29 / 2 / 19 | Historical classes retained; individual changes unverified |
| Researcher-authored controls | 50, 47 exercised historically | Original controls not rerun as a 100-ID study |
| Historical authored oracle agreements / positive replays | 28/28 / 20 | Not substituted with new regression counts |

The new `0.1.0a4.dev0` source admits **one guarded grouped aggregate CTE or
derived stage** in the finite two-table NoUndo workflow. The synthetic
`aggregate_cte_fanout.json` pair is independently checked against original
DuckDB SQL over all 18 legal worlds; the positive witness replays and a paired
SUM metric is complete bounded-negative. This is **syntax/semantic coverage**,
not an unchanged original developer-task success. The source cases previously
listed as related to aggregate/filter CTEs or subqueries may additionally need
different SQL dialects, multiple models, constraints, retention premise and
an independently declared KPI. No such contract can be invented from a link.

To complete a defensible 100-ID reassessment, recover and verify the original
private ledger hash and source inventory, retain exactly its 50/50 cohorts and
first-run outcomes, evaluate each original *unchanged* against the new exact
grammar and obligations, and publish only a privacy/right-cleared aggregate.
Keep A17's incorrect historical expected-negative label, A43's unverified
original exception class and A44's unexecuted dbt Core result visible. Until
then, the original-task outcome is **unverified after this change**, not 1/50
or 50/50. Paper 1, Paper 2 and Phase 6C primary practical gates remain failed.
