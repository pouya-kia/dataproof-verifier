# Full-Contract SQL Tasks v1 — authored engineering controls

This [versioned manifest](../../examples/full_contract/tasks.json) is separate
from the frozen DataProof-100 intake. All 12 inputs are **researcher-authored
NoUndo controls** (nine reuse previously executed public synthetic examples;
three are exact SQL variants). Their outcomes were not selected blind, and
they are not authentic developer incidents, a preregistered experiment,
independent adoption or scientific performance evidence. The manifest pins
each exact source JSON by SHA-256 and, for variants, supplies the exact SQL
override. Source specs declare finite schema/domain/keys, retained view,
scalar KPI and timeout. The `decision` and `simpler` fields disclose the
intended engineering question and when ordinary SQL would be simpler.

| ID | Family / full finite question | Legal worlds | Independently executed DuckDB status |
| --- | --- | ---: | --- |
| FC01 | INNER join fanout versus distinct orders | 18 | Counterexample |
| FC02 | Filtered fanout versus distinct KPI | 18 | Counterexample |
| FC03 | Declared-key fanout control | 8 | Complete bounded negative |
| FC04 | LEFT unmatched rows versus right availability | 18 | Counterexample |
| FC05 | RIGHT unmatched rows versus left availability | 6 | Counterexample |
| FC06 | Binary STRING distinctness under a join | 20 | Counterexample |
| FC07 | Projection-only CTE scope/renaming | 6 | Counterexample |
| FC08 | UTC-naive monthly TIMESTAMP grouping | 56 | Counterexample |
| FC09 | Nested aggregate CTE, retained total versus peak fanout | 18 | Counterexample |
| FC10 | Nested aggregate CTE, retained total versus total KPI | 18 | Complete bounded negative |
| FC11 | Grouped joined counts versus scalar total | 18 | Complete bounded negative |
| FC12 | Aggregate derived source spelling of FC09 | 18 | Counterexample |

The 12 case sets contain **222 legal worlds in total** (some identical base
world sets recur). `test_full_contract_sql_suite.py` compares the version-1
plan's view bag and scalar KPI against DuckDB executing each **original
admitted SQL** on every legal world; it then performs a separate complete
DuckDB NoUndo reference search, runs CLI preflight/check, checks finite
negative exhaustion, and replays every positive serialized witness. The
focused suite reported 13 passing tests: 12 task checks plus manifest
integrity. Nine positives replayed, three negatives exhausted; no source
task or hypothesis was relabeled after a result. The DuckDB execution is
independent of the plan evaluator but shares case schema, world enumeration,
SQL dialect and some admission assumptions. The positive paths may stop
early; only the negative paths attest complete search. None proves behavior
outside the declared finite bound.

This suite exercises several feature families but **does not** supply a new
Doppelgänger invariant or Proof2Test expected-output contract. Those
workflows keep their existing separate tests and capability limits. The
suite also does not itself address the unchanged original 50 public-origin
tasks. Their restored private ledger received a [separate per-ID
reassessment](dataproof-100-architecture-postchange.md); no original task
became a demonstrated unchanged full-contract success.
