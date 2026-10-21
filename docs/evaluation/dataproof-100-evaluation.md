# DataProof-100: bounded Alpha engineering evaluation

This is a coverage and regression audit of the **published** DataProof Alpha
`v0.1.0a1`, not a scientific performance study or an independent-user pilot.
The tested distribution was the [GitHub release Wheel](https://github.com/pouya-kia/dataproof-verifier/releases/tag/v0.1.0a1), SHA-256
`32b3575bdb3acda97ccc5ad9a3ac7ee0adbf02b40f2ce698e518903b782c6b77`.
Its source tag resolves to `ee038a23d5c061e66cf58f41e2cf1f9a2fa4e087`;
the public `main` observed during evaluation was
`11aed873fa92f2f94cba3f21baf0dbcf745cc84c`. The latter contains
documentation and contributor-infrastructure changes after the release;
it was **not** the installed evaluation target.

## Executive result

| Cohort or check | Denominator | Baseline observation |
| --- | ---: | --- |
| Public-origin records | 50 | 0 executable unchanged |
| Unsupported originals | 29 | SQL/workflow outside the Alpha contract |
| Insufficient originals | 2 | No complete original obligation |
| Not-applicable public records | 19 | No complete DataProof question to run |
| Researcher-authored synthetic controls | 50 | 47 exercised; 3 designs not admitted |
| Complete finite DuckDB oracles | 30 | 28 direct obligations plus 2 later source-witness obligations |
| Initial solver/oracle comparisons | 28 | 28 agreements in declared tiny domains |
| Initial positive witnesses | 20 | 20 serialized and separate DuckDB replays valid |
| Additional Proof2Test source witnesses | 2 | Both replayed |

These are **different denominators**, not interchangeable pass rates. In
particular, `28/28` is not a success rate on original developer problems:
all 28 were authored controls. No original public task was solved unchanged,
and no original engineering decision was shown to improve.

## Question, selection, and provenance

The audit asked two separate questions: (1) which original, public-origin
SQL or data-engineering problems fit the shipped contract **without rewriting
their requirement**, and (2) whether the installed package agrees with
complete tiny-world references on deliberately constructed controls.

The 100-ID catalog contains 17 historical public-post references, 33 linked
GitHub issue/commit records, and 50 researcher-authored synthetic controls.
All IDs, including ineligible and negative ones, remained in the denominator.
The historical links were recovered from a pre-existing local inventory and
their URLs/titles resolved; full original post bodies and executable
requirements were **not** reconstructed. The 33 GitHub records were 15
commit patches and 18 issue bodies with associated comments, not 33
independent defects. Several are feature requests, engine bugs, or related
edits. This provenance cannot substitute for a developer-approved KPI,
business invariant, retained-data contract, or expected output. For example,
[a join-count question](https://stackoverflow.com/questions/8860919/group-by-in-sql-server-giving-wrong-count)
motivates a join-cardinality capability but does not by itself specify a
NoUndo view/KPI pair; a [dbt model edit](https://github.com/dbt-labs/jaffle-shop/commit/2447e1b505a7401cbe3a3c6a818d7073ed2e61d8)
contains additional model-graph semantics that the Alpha does not execute.
Links are citations to public origins, **not** claims of participation or
permission to republish their full text.

Eligibility required an original schema/domain and admitted SQL, plus a
complete NoUndo retained-view/KPI pair or Doppelgänger existing-tests and
separately justified invariant. An independently checked output also had to
bear on the original engineering decision. A translated dialect, simplified
toy model, or newly invented rule was **not** counted as unchanged support.
The ledger classified 29 originals as unsupported as stated, two as
insufficiently specified, and 19 as not a complete applicable obligation.
Thus the observed unchanged eligibility is **0/50**. This is a finding about
this mixed intake, not an estimate of prevalence in all data-engineering work.

## Evaluation procedure and exact scope

The published Wheel was installed into a fresh local CPython 3.11.16
environment on macOS arm64. Runtime pins were DuckDB 1.5.6, SQLGlot 29.0.1,
Z3 Solver 5.3.1.0, and PyYAML 6.0.3. The input-planning manifest used system
Python 3.9.6 **before** this environment existed; it was not the interpreter
used to run the tool. The 50 authored controls included positive,
bounded-negative, unsupported, invalid, and injected fail-closed cases.
Ten IDs were held out from the same authored catalog before first execution;
this was not an external or untouched population sample.

For tractable authored obligations, an exhaustive reference enumerated legal
finite bag worlds within the declared column domains and row bounds, using
DuckDB for admitted SQL. It refused analytical world counts over 10,000 and
had a 45-second per-case wall budget. The 30 complete references consist of
28 initial solver obligations and two additional source-witness obligations
for generated-test controls. The 28 initial solver outcomes agreed with the
reference. Twenty initial positive NoUndo/Doppelgänger witnesses passed the
installed serialized validator and a separate fresh DuckDB output-bag or
assertion check; two further source witnesses did too. This is execution
independence from Z3 formulas, **not** full semantic independence: the schema,
admission policy, SQL dialect assumptions, and DuckDB semantics are shared.
The finite reference is not a proof for larger or arbitrary databases.

The harness imposed a 15-second child wall cap; specs retained their own
5-second Z3 timeout and 256-MB Z3 memory setting. **No hard process-memory
ceiling** was enforced by the local harness. On this Mac, `pip check` reported
`z3-solver 5.3.1.0 is not supported on this platform`; imports, solver calls,
and CLI runs nevertheless worked. That metadata discrepancy is unresolved
installation evidence, not a reason to hide the failed check.

## Results and failures retained

The direct controls produced 14 NoUndo counterexamples, six Doppelgänger
blind spots, five NoUndo bounded negatives, two Doppelgänger bounded
negatives, and one inconsistent-existing-tests result. Other authored
controls exercised unsupported/invalid inputs, Proof2Test exports, artifact
ownership, and injected inconclusive paths. The three proposed assertion
designs A22, A27, and A30 compared one aggregate to another, outside the
shipped assertion grammar, and were **not** rewritten to make them pass.
Observed finite negatives mean no witness in those exact declared worlds,
not universal determinacy or test adequacy.

The catalog predicted a bounded-negative outcome for **A17**. Complete
finite enumeration and the installed package instead both found a valid
counterexample for the displayed obligation. The original prediction was
wrong; the input and first-run result were retained. This does not, by
itself, demonstrate a DataProof solver defect. A synthetic Proof2Test
defective-versus-corrected target produced FAIL/PASS, and wrong expected-bag,
duplicate-multiplicity, and row-order controls exercised their intended
engineering paths. The **A43** first-run generated test exited nonzero on a
JOIN target, but retained output was truncated: its exact pytest exception
class is unverified and the holdout was not rerun. **A44** emitted parsable
dbt YAML, but dbt Core did not execute it. The A47 Z3 timeout/memory/unknown
paths were **mocked failure injections**, not physical resource-exhaustion
tests. No positive replay disagreement or supported-input crash was observed
in the recorded controls; neither absence establishes unrestricted safety.

## Coverage blockers and engineering implications

Common blockers in the original cohort were multi-table joins and dbt model
graphs; timestamps, rolling windows, and incremental state; strings and
collations; conditional expressions; multi-key grouping; and engine-specific
execution bugs. SQL syntax is not the only barrier: many sources lack a
retained-view/KPI pair, an independent business invariant, domains or
constraints, or evidence that source data were actually unavailable. A
normal SQL query, dbt test, or engine regression can be simpler and more
appropriate than DataProof for several originals. The Alpha's one-table,
three-row, INTEGER/DATE finite fragment is intentionally narrow. A later
synthetic extension cannot be counted as solving an original task unless
the full original contract is faithfully supported and checked.

The next engineering question is whether one bounded, independently
reference-checked SQL capability can add useful *synthetic* verification
without weakening fail-closed behavior. Join fanout is a reasonable
candidate because it recurs in public-origin records; implementing a
restricted equijoin would **not** make their full dbt/BI tasks eligible by
itself. The outcome of any subsequent extension must be reported separately
from this immutable `v0.1.0a1` baseline.

## Reproduction and limitations

The public release Wheel and its SHA-256 identify the executable. The
[supported SQL semantics](../semantics.md), [demo](../demo.md), and public
synthetic examples provide independently runnable *product* smoke tests:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install dataproof_verifier-0.1.0a1-py3-none-any.whl
.venv/bin/dataproof-verifier preflight no-undo examples/no_undo/daily_distinct.json
.venv/bin/dataproof-verifier check examples/no_undo/daily_distinct.json --output artifacts/no-undo
.venv/bin/dataproof-verifier replay artifacts/no-undo/witness.json
```

Download the Wheel from the linked release before running these commands,
and verify its hash above. The full 100-ID audit is **not publicly
reproducible from this report alone**: raw source caches, authored fixture
suite, first-run records, and local scripts remain private pending privacy,
redistribution-rights, and methodology review. A hash of a private file is
not a substitute for public availability. The aggregate counts here were
recomputed from the local 100-ID ledger and its 186-entry SHA-256 inventory,
not reconstructed from the public examples. No raw third-party issue bodies,
private notes, machine paths, or unpublished research runs are included.

The strongest result is a **coverage limitation**: none of 50 mixed
public-origin records was executable unchanged. The synthetic agreements
support narrow engineering regression confidence, not broad SQL
correctness, independent adoption, practical superiority, or production
readiness. Prior preregistered Paper 1, Paper 2, and TimeProof Phase 6C
primary practical gates all failed; this audit does not reverse any of them.
