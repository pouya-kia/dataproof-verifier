# DataProof-100: post-change engineering decision

This is the final accounting for the **unpublished `0.1.0a2` source candidate**, not a replacement for the immutable [published `v0.1.0a1` evaluation](dataproof-100-evaluation.md). The candidate incorporates the independently reviewed [wave 1](sql-coverage-wave-1.md) and [wave 2](sql-coverage-wave-2.md) changes. The private 100-row final derivative is the wave-2 record, SHA-256 `d201cb2e1c46d5cf9565606ae35579bda7c458f07cc5311d9756ecd7d1386eb4`. It preserves the original IDs and historical expectations; unpublished source text, local paths and raw machine logs are not redistributed here.

| Cohort | Count | Final interpretation |
| --- | ---: | --- |
| Public-origin records | 50 | **0 fully solved unchanged**, 0 complete original obligations executed |
| Unsupported original SQL/workflow | 29 | Still requires other SQL, dbt, temporal, engine or business semantics |
| Missing original contract | 2 | No established complete KPI/invariant or constraints |
| Not applicable to a DataProof obligation | 19 | Retained, not dropped from denominator |
| Researcher-authored controls | 50 | 47 exercised, 3 original designs not admitted |
| Direct authored fixtures | 34 | 28 applicable finite-oracle agreements, zero disagreements; 20 independently replayed positive witnesses |
| Other authored controls | 13 | Proof2Test/export/error/ownership paths; some are mocks or non-executed dbt YAML |

The candidate adds guarded three-valued `WHERE`, up to two direct GROUP BY columns, and explicit restricted LEFT joins to the **separate** two-table complete finite backend. Its analytical cap is 500 combined legal worlds, with at most two rows per table. Both the Python search evaluator and DuckDB original-SQL reference must complete before a bounded-negative conclusion; positive witnesses require serialized DuckDB replay. The production one-table Z3 path retains its existing ≤3-row, INTEGER/DATE fragment. No broad SQL or arbitrary dbt support follows from these changes.

The original public records cannot be promoted to successes by attaching researcher-authored finite SQL analogues. The retained source inventory lacks complete original SQL/schema/domain/KPI evidence for many entries, and a syntax feature does not establish applicability to the original developer decision. The A17 historical expected-negative error remains recorded in the baseline; no target or expected output was rewritten to hide it. A22/A27/A30 remain inadmissible assertion designs. A44 is a dbt YAML export, not an executed dbt test. A47's timeout/memory/unknown categories are controlled mocks. The first post-change A40 follow-up accidentally used an unsupported `ORDER BY` target; that run is preserved as a harness-selection error, and the original corrected-target control passed in the corrected record. These details prohibit a synthetic "100/100 passed" claim.

The feature-dependency assessment found that remaining strings/collations, casts/arithmetic/CASE, CTEs, period DISTINCT, timestamps/windows, arbitrary model graphs and mutable/incremental pipelines either require a new semantic model, independent oracle and security design, or missing original business contracts. The small safe slices above were completed; broader support is deferred rather than accepted under unverifiable assumptions. A new feature should be justified by a complete, independently motivated task and cross-validated semantics, not by an apparent increase in parsed case count. Ordinary SQL or dbt assertions remain simpler for tasks with available raw data and a known expected answer.

This engineering evaluation is not a Paper 1, Paper 2 or Paper 3 rerun. Their frozen negative primary practical decisions remain unchanged. The evidence supports a bounded, replayable tool candidate and no claim of production readiness, original-task adoption, algorithmic novelty, comparative superiority, or general SQL correctness.
