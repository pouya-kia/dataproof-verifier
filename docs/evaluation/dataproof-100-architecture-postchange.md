# DataProof-100 after the relational-core and aggregate-CTE changes

Status: **all 100 historical IDs accounted for; 34 unchanged direct authored
fixtures rechecked, other control types retained but not rerun**. The private
original catalog and `evaluated-cases.jsonl` were restored after an initial
aggregate-only draft. Their recorded SHA-256 values match
`5baf8d3058a367fb85786c9c147cce51e588efd33dba4033e181bb615bf788e9`
and `8bd247601030975038b76bf2c149495a602bb871ccffa8555bb790647ee42474`;
all 186 original inventory entries passed byte-hash verification. The source
snapshot is the untagged `0.1.0a4.dev0` Wheel built from commit
`b2e1b66d1c2b863940e0f4edccb742e5d345054d`, SHA-256
`1cfac6725bc91d796bdbb6a7eb9749567a4522c0de4fbaacc091ec9d87bbcf7c`.
No original description, fixture, first-run result or frozen study was edited.

| Cohort / fact | Preserved historical baseline | New assessment |
| --- | ---: | --- |
| Public-origin identities | 50 | 50/50 inspected in the restored ledger; every original still lacks an unchanged, executable full-contract fixture |
| Original tasks fully eligible / independently solved | 0 / 0 | **0 / 0** for this intake; no syntax-only analogue promoted |
| Original unsupported / insufficient / not applicable | 29 / 2 / 19 | 29 / 2 / 19 as-stated classifications retained |
| Researcher-authored controls | 50, 47 exercised historically | 50/50 accounted for; 34 direct fixtures rerun unchanged, remaining types not rerun in this pass |
| Direct authored status changes | not applicable | 0/34 |
| Direct complete finite-oracle agreements / disagreements | 28/28 / 0 | 28/28 / 0 against preserved independent DuckDB oracle records |
| Direct positive serialized / separate DuckDB replays | 20 / 20 | 20 / 20 valid |

The new `0.1.0a4.dev0` source admits **one guarded grouped aggregate CTE or
derived stage** in the finite two-table NoUndo workflow. The synthetic
`aggregate_cte_fanout.json` pair is independently checked against original
DuckDB SQL over all 18 legal worlds; the positive witness replays and a paired
SUM metric is complete bounded-negative. This is **syntax/semantic coverage**,
not an unchanged original developer-task success. The 50 original rows had no
as-stated fixture in the verified ledger. Some source links contain SQL
features now partly admitted, but their original model graphs, schema,
constraints, retention premise, expected output or independently declared
KPI/invariant remain absent or outside the precise fragment. A syntax match
is not an executable obligation. The 19 not-applicable records are not
silently relabeled as unsupported; the two insufficient records remain so.

The new private machine-readable 100-ID derivative has SHA-256
`75da7ae7d79196781ce50794e578b757c04b8b7dbfa03c88a90c180aa9e32b22`.
It retains all original IDs and status labels, records the direct rerun and
replay classifications, and does not redistribute third-party text, machine
paths or raw logs. Of the 34 direct controls, 32 ran in the first current-Wheel
pass; two reliability-format controls (A46/A50) were checked in a separately
recorded follow-up and agreed with their old unsupported/invalid outcomes.
Other Proof2Test and injected reliability controls were *not* newly rerun;
their historical statuses are retained, not counted as fresh passes. A17's
incorrect historical expected-negative hypothesis remains visible, A43's
first-run exception class is still unverified, and A44 still lacks dbt Core
execution. The restored intake is still not an independent-user sample or a
fully public reproducibility package. Paper 1, Paper 2 and Phase 6C primary
practical gates remain failed.
