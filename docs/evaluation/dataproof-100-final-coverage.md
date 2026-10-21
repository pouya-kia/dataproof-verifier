# DataProof-100: final bounded-SQL engineering coverage

This compares the published `v0.1.0a1` engineering baseline with the **unpublished** `0.1.0a2` source candidate. The original 100-case catalog, hypotheses, holdout and first-run evidence were not modified. This is not a scientific performance experiment or independent-user study. The two-table backend is separate from the one-table Z3 workflows.

## Baseline versus candidate

| Observation | Published baseline | Post-change candidate |
| --- | ---: | ---: |
| Public-origin records retained | 50 | 50 |
| Original tasks fully eligible unchanged | 0 | **0** |
| Independently verified original-task successes | 0 | **0** |
| Originals unsupported as stated | 29 | 29 |
| Originals missing a complete contract | 2 | 2 |
| Originals not applicable to a DataProof obligation | 19 | 19 |
| Originals partially covered as complete tasks | 0 | 0; isolated syntax analogues do not qualify |
| Researcher-authored controls retained | 50 | 50 |
| Authored controls exercised | 47 | 47 |
| Authored designs not admitted/executed | 3 | 3: A22, A27, A30 |
| Direct finite-oracle agreements / disagreements | 28 / 0 | 28 / 0 |
| Valid direct positive serialized replays | 20 | 20 |
| Additional source-witness replays for generated-test controls | 2 | 2 |
| Direct bounded-negative results | 7 | 7: five NoUndo, two Doppelgänger |
| Direct inconsistent-existing-test result | 1 | 1 |
| Recorded direct timeouts / incomplete searches | 0 / 0 | 0 / 0 |

The 50 public records comprise 17 historical problem references and 33 linked issue/commit records, not 50 independent customer incidents. Complete original SQL, schema, constraints and an independently justified KPI/invariant are often absent. No original public task was run as a complete DataProof obligation. The `0/50` result measures this intake, not prevalence across all data engineering. Original A17's expected-negative label was contradicted by complete finite enumeration and a valid witness; it was retained, not changed to make the tool pass. The original holdout was not retuned.

The private 100-identity post-change derivative records original eligibility, new syntax and semantic applicability separately, historical/observed status, method, search completeness, oracle availability/agreement, replay validity, runtime, blocker, and whether the original decision was addressed. It is not redistributed pending source-rights and path review. Public [wave 1](sql-coverage-wave-1.md) and [wave 2](sql-coverage-wave-2.md) summaries describe their checks. The final derivative SHA-256 is `d201cb2e1c46d5cf9565606ae35579bda7c458f07cc5311d9756ecd7d1386eb4`; that is **not** the immutable baseline stream's hash.

## SQL capability matrix

“Checked” means finite Python evaluation against admitted original SQL executed by DuckDB on tiny legal worlds, plus positive replay where relevant. It is not a general SQL proof. A single admitted form does not make a whole family or original task supported.

| SQL family | `v0.1.0a1` baseline | `0.1.0a2` candidate | Semantic verification | Remaining restrictions |
| --- | --- | --- | --- | --- |
| Compound WHERE / comparisons | One guarded predicate per one-table query | **Restricted support** in separate two-table queries: AND/OR/NOT, IS [NOT] NULL, direct typed comparisons and signed 32-bit INTEGER literals | Every legal world of several small NULL/DATE/bag cases compared with DuckDB; SQL UNKNOWN filters rows | One-table Z3 unchanged; no functions, IN or arbitrary expressions |
| STRING columns/predicates | Unsupported | Unsupported | None | Collation, type and domain policy not established |
| Multi-column GROUP BY | One direct column | **Restricted support** for one/two distinct direct qualified columns in joined backend | Small-world NULL grouping/projection-order differential checks | One-table path still one key; no expression keys or grouping sets |
| Arithmetic, casts, derived scalar expressions | Unsupported | Unsupported | None | Overflow, cast and NULL semantics need an independent evaluator |
| CASE / conditional aggregation | Unsupported | Unsupported | None | Branch truth and aggregate-input semantics not established |
| Multiple-table INNER JOIN | Unsupported | **Restricted support:** exactly two tables, one explicit same-type direct equijoin | Complete finite bag search, DuckDB original-SQL reference, positive replay | ≤2 rows/table, ≤3 columns/effective values per column, ≤500 analytical combined worlds |
| LEFT and other OUTER JOIN | Unsupported | **Restricted LEFT [OUTER] support** only | Tiny-world NULL extension, duplicate and aggregate differential checks; replayed positive and negative controls | RIGHT/FULL, compound ON, lateral/semi/anti unsupported; WHERE is post-join |
| CTEs | Unsupported | Unsupported | None | Scope/materialization/bag-preserving rewrite not established |
| Subqueries / derived tables | Unsupported | Unsupported | None | Correlation, alias scope, multiplicity and typing unmodeled |
| TIMESTAMP / timezone / date bucketing | DATE domains only | DATE domains only | Existing DATE and joined DATE comparison tests | No timestamp, timezone or bucket-boundary contract |
| Reporting-period aggregation | Direct finite grouped aggregates | Same, plus two joined grouping keys | Finite aggregate/grouping tests | No date truncation, nested period pipeline or period reaggregation |
| Rolling / cross-period COUNT DISTINCT | Only direct finite COUNT DISTINCT | Same | Direct COUNT DISTINCT reference checks | No window/rolling semantics; the old daily/monthly witness is not a reporting pipeline |
| Window functions / ordering | Unsupported | Unsupported | None | Ties, frames, partition/order and determinism unresolved; ORDER BY rejected in admitted target SQL |
| SQL dialect variants | Guarded DuckDB SQL | Guarded DuckDB SQL | DuckDB replay only | No PostgreSQL, BigQuery or other dialect fidelity claim |
| dbt models/tests | Restricted Proof2Test YAML export | Same | Export/structure checks only | A44 was **not** executed under dbt Core; model graphs/macros unsupported |
| Mutable / incremental state | Not in production CLI | Not added | None in candidate | Requires update/retry/watermark semantics; private TimeProof work was not imported |

The original blockers overlap. A join-count problem may still require model lineage and an independent KPI; rolling distinct needs temporal and retention semantics; an engine bug may not be a determinacy or test-blind-spot question at all. A normal SQL query, dbt assertion or engine regression can be simpler when source data and expected answers remain available. Expanding a syntax family solely to make a toy analogue parse does not address missing original decisions.

## Engineering verification and failures retained

The implemented-code freeze is public merge `22d98b2c77eae217503ac61eb20101b2ef9da7db` after [PR #4](https://github.com/pouya-kia/dataproof-verifier/pull/4) (predicates/grouping), [PR #5](https://github.com/pouya-kia/dataproof-verifier/pull/5) (LEFT JOIN), and [PR #6](https://github.com/pouya-kia/dataproof-verifier/pull/6) (candidate version/docs). This report is documentation-only relative to that freeze. Runtime changes are in the joined-query parser/model, Python finite reference and joined replay/explanation labels; one-table Z3, Doppelgänger and Proof2Test algorithms were not modified. Local full suite: **241 passed, one skipped**; joined-query focused suite: **45 passed**. Ruff lint/format, strict mypy, Wheel/sdist builds, fresh Python 3.11 installs and a 19-outcome installed-Wheel synthetic demo passed. Each PR and post-merge run passed Ubuntu Python 3.11/3.12 CI, including installed-Wheel joined replay and dependency consistency.

No direct-case status changed post-change. Twenty direct positive witnesses passed serialized DuckDB replay; two more Proof2Test source witnesses replayed. A48 intentionally tampers with a witness and correctly fails validation; it is not an invalid generated positive. A22/A27/A30 were not rewritten. A43's **original** holdout only retained a nonzero generated-pytest exit with truncated output; its later post-change run is a regression, not a restored blind observation. A44 exported dbt YAML but never ran dbt Core. A47's timeout/memory/unknown classifications are injected mocks, not physical resource events. An initial post-change accounting pass misclassified six Doppelgänger oracle positives; a separate first follow-up fed A40 an unsupported ORDER BY target. Both private records were retained; corrected accounting and the original-target A40 run passed. Neither mistake changed the frozen baseline.

The 500-world analytical cap is checked before enumeration. `BOUNDED_NO_COUNTEREXAMPLE` requires **complete** legal-world search by both finite evaluators; timeout, error or disagreement is inconclusive. The deadline is cooperative and no OS hard process-memory ceiling is claimed. Both evaluators share schema admission/world enumeration, so DuckDB execution independence does not remove all correlated-error risk. macOS `pip check` still reports an upstream Z3 wheel-platform metadata mismatch, although solver tests and CLI work; Ubuntu CI dependency checks pass.

## Research integrity and developer impact

The existing negative Paper 1, Paper 2 and Phase 6C primary practical decisions remain unchanged. This candidate did not rerun them, alter frozen cases or import private TimeProof code. It establishes no algorithmic novelty, general performance superiority, production readiness or independent adoption. It **does** permit tiny replayable counterexamples for joined-data information loss—including filtered fanout and missing LEFT-join matches—that `v0.1.0a1` could not represent. This is an engineering capability under explicit assumptions, not successful analysis of an original public task in this catalog.

The history-free `0.1.0a2` source candidate and separate Wheel/sdist artifacts await explicit owner approval for any tag or GitHub Release. The published `v0.1.0a1` release is unchanged, and no PyPI publication is claimed. A credible next utility evaluation needs a permissioned complete original developer task with schema, constraints and an independently justified KPI/invariant; unsupported outcomes stay in its denominator. Broader SQL should wait for such a task and an independently checkable semantic contract.
