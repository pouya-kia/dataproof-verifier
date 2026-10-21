# DataProof — experimental Alpha (`0.1.0a4.dev0` development source)

DataProof is an offline, bounded SQL reasoning CLI. It works on small synthetic tables, not production databases. Its three workflows are distinct:

Alpha v0.1.0a1 is publicly available from the [GitHub prerelease](https://github.com/pouya-kia/dataproof-verifier/releases/tag/v0.1.0a1). Distribution: `dataproof-verifier`; import: `dataproof_verifier`; CLI: `dataproof-verifier`. It is **not published on PyPI**; install from this repository or the release Wheel. The unrelated PyPI `dataproof` project is not a dependency.

Current source is an untagged `0.1.0a4.dev0` **development candidate**, not
a tagged GitHub release or PyPI publication. The published `v0.1.0a1`
Wheel and its frozen evaluation are unchanged.

- **NoUndo:** find two legal source bags whose retained aggregate-view bags agree but whose downstream scalar KPIs differ.
- **Doppelgänger:** find one legal source bag on which declared existing SQL assertions are TRUE while a separately supplied invariant is FALSE.
- **Proof2Test:** turn a replay-validated Doppelgänger witness and a separately declared target-output contract into a restricted executable regression fixture.

`preflight` checks eligibility without searching. `replay` independently executes admitted SQL in DuckDB. `explain` presents an already validated positive witness as readable source and output bags. A found witness is concrete evidence only under the declared finite schema, domains, constraints, and SQL semantics. A bounded miss is **not** a universal proof. This Alpha is not evidence of production readiness, independent adoption, algorithmic novelty, or comparative speed.

## Install and try it

Python 3.11 or 3.12 is required. Do not use a system `python3` that resolves
to an older interpreter. Installing dependencies may require a network; the
installed core requires no account, API key, LLM, or cloud service. To install
from this public source candidate:

```sh
git clone https://github.com/pouya-kia/dataproof-verifier.git
cd dataproof-verifier
python3.11 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/dataproof-verifier preflight no-undo examples/no_undo/daily_distinct.json
.venv/bin/dataproof-verifier check examples/no_undo/daily_distinct.json --output artifacts/no-undo
.venv/bin/dataproof-verifier replay artifacts/no-undo/witness.json
.venv/bin/dataproof-verifier explain artifacts/no-undo/witness.json
```

The NoUndo example has equal daily order-count, revenue, and distinct-customer summaries, but monthly distinct-customer KPIs of 1 and 2. The generated `replay.sql` ends with `REPLAY_OK` when run in DuckDB. Two bounded-negative controls are `examples/no_undo/constrained_customer.json` and `examples/no_undo/daily_sum.json`; each returns exit code 3, **not** a universal preservation proof.

The [synthetic exchange-volume retention use case](examples/use_cases/exchange_volume_retention/README.md) gives a practitioner-inspired, fully runnable information-loss and bounded-repair walkthrough. Its separately coded DuckDB oracle enumerates all 16 declared legal worlds; this is engineering evidence, **not** a real exchange incident or independently sourced user-task success.

```sh
.venv/bin/dataproof-verifier preflight doppelganger examples/doppelganger/nonnegative_amount.json
.venv/bin/dataproof-verifier doppelganger check examples/doppelganger/nonnegative_amount.json --output artifacts/doppel
.venv/bin/dataproof-verifier doppelganger replay artifacts/doppel/witness.json
.venv/bin/dataproof-verifier explain artifacts/doppel/witness.json
```

The Doppelgänger example declares a nonnegative-amount invariant and an existing test that only requires at least one order. Its synthetic witness passes that test but violates the invariant. DataProof does not infer the business invariant.

Proof2Test additionally needs a target-output contract supplied independently of the witness. The included synthetic clamp example is an engineering smoke test, not external evidence:

```sh
.venv/bin/python -m pip install pytest
.venv/bin/dataproof-verifier proof2test export examples/doppelganger/evidence/witness.json --target examples/proof2test/clamp_amount.contract.json --format pytest --output artifacts/proof2test
DATAPROOF_TARGET_SQL=examples/proof2test/defective.sql .venv/bin/pytest -q artifacts/proof2test
DATAPROOF_TARGET_SQL=examples/proof2test/corrected.sql .venv/bin/pytest -q artifacts/proof2test
```

The defective model must fail the generated assertion; the corrected one must pass. A narrowly scoped dbt Core unit-test YAML adapter also exists; arbitrary dbt projects are unsupported. See the complete [offline demo](docs/demo.md), [preflight](docs/preflight.md), [explanation](docs/explain.md), [Doppelgänger](docs/doppelganger.md), and [Proof2Test](docs/proof2test.md) contracts.

## Published v0.1.0a1 one-table finite scope

One source table, at most three rows per world, at most four columns and four declared domain values per column; finite `INTEGER` and `DATE` values with explicit NULL, primary-key and nullable-UNIQUE rules. NoUndo admits one retained grouped aggregate view and one scalar aggregate KPI. Supported aggregates are `COUNT(*)`, `COUNT(column)`, `COUNT(DISTINCT column)`, exact integer `SUM`, and direct integer `MIN`/`MAX`. A query may have one guarded row filter: integer-column equality to a signed integer literal, `IS NULL`, or `IS NOT NULL`. Doppelgänger admits one to four existing scalar assertions and one independent invariant. NULL, SQL UNKNOWN, duplicate bags, and empty inputs have explicit semantics. Unsupported joins, multiple retained views, compound predicates, HAVING, windows, arbitrary expressions, timestamps, floating-point arithmetic, and production data access fail closed. The full [semantics](docs/semantics.md), [limitations](docs/limitations.md), and [architecture](docs/architecture.md) are part of this Alpha release.

The CLI records assumptions, bounds, versions, hashes, witnesses, and replay artifacts. Reused output directories only clear unchanged DataProof-owned artifacts; unrelated files are preserved. Use separate directories for concurrent runs. See [artifact behavior](docs/limitations.md) and the demo. Scientific research scripts, raw runs, and manuscripts are not distributed in this source candidate.

This candidate source additionally has a **separate** [bounded
two-table equijoin workflow](docs/bounded-join.md): at most two rows per
source, three columns and three effective domain values per column, and 500
analytical combined worlds. It supports guarded three-valued WHERE predicates
and at most two grouping expressions. It uses complete finite Python search
plus an independent DuckDB SQL reference, **not** the one-table Z3 encoding.
It now admits restricted finite ASCII STRING equality/grouping and guarded
CASE/integer expressions in that separate join workflow only. It does not imply
general dbt, arbitrary CTE, unrestricted string, window, or incremental support.
The finite join path also admits one or two direct equality keys and
INNER/LEFT/RIGHT/FULL null-extension semantics; three-table joins remain unsupported.
The [Wave A engineering record](docs/evaluation/sql-coverage-wave-a.md) keeps
the original-task result at 0/50 and distinguishes these finite synthetic checks.
The [Wave B engineering record](docs/evaluation/sql-coverage-wave-b.md) covers
composite keys and outer-join null extension without a three-table claim.
Projection-only, row-preserving CTE chains and derived sources are admitted.
The `0.1.0a4.dev0` joined path also admits one guarded grouped aggregate CTE
or derived source followed by one aggregate stage; general CTE graphs and
scalar subqueries remain unsupported. Restricted UTC-naive
second-precision TIMESTAMP values and `DATE_TRUNC` day/month grouping allow
tiny period-count and COUNT DISTINCT examples. Timezone conversions, rolling
frames and all `OVER` windows remain unsupported. See [Wave C](docs/evaluation/sql-coverage-wave-c.md),
[Wave D](docs/evaluation/sql-coverage-wave-d.md), the [final capability and
coverage matrix](docs/evaluation/sql-coverage-a3-candidate.md), and the
[candidate release notes](docs/release-notes-0.1.0a3.md).
The separate [untagged `0.1.0a4.dev0` development notes](docs/release-notes-0.1.0a4-dev.md)
describe the new bounded aggregate pipeline and its remaining gates.
This development source routes the bounded joined-query Python search through
the [versioned relational plan](docs/architecture/relational-core.md); the
classic one-table Z3, Doppelgänger, and Proof2Test contracts are unchanged.
For example, after installation:

```sh
.venv/bin/dataproof-verifier join preflight examples/join/left_missing_match.json
.venv/bin/dataproof-verifier join check examples/join/left_missing_match.json --output artifacts/left-join
.venv/bin/dataproof-verifier join replay artifacts/left-join/witness.json
.venv/bin/dataproof-verifier join preflight examples/join/right_missing_match.json
.venv/bin/dataproof-verifier join preflight examples/join/projection_cte.json
.venv/bin/dataproof-verifier join preflight examples/join/monthly_timestamp_distinct.json
.venv/bin/dataproof-verifier join preflight examples/join/aggregate_cte_fanout.json
.venv/bin/dataproof-verifier join check examples/join/aggregate_cte_fanout.json --output artifacts/aggregate-cte
.venv/bin/dataproof-verifier join replay artifacts/aggregate-cte/witness.json
.venv/bin/dataproof-verifier join explain artifacts/aggregate-cte/witness.json
```

## Contribute or report a problem

This Alpha release carries an [MIT license](LICENSE). Direct dependency pins and upstream license links are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Read [CONTRIBUTING.md](CONTRIBUTING.md), use the [reproducible issue template](ISSUE_TEMPLATE.md), or submit an original, possibly unsupported SQL task with [this intake template](ORIGINAL_SQL_PROBLEM_TEMPLATE.md). Read the [security reporting policy](SECURITY.md) before sharing a vulnerability. Do not submit confidential SQL, personal data, credentials, or proprietary schemas without permission. Unsupported and incomplete tasks are useful findings; do not simplify an original task solely to fit the current grammar.

Open a [bug report](https://github.com/pouya-kia/dataproof-verifier/issues/new?template=bug_report.yml), share an [original SQL problem or unsupported query](https://github.com/pouya-kia/dataproof-verifier/issues/new?template=original_sql_problem.yml), or make a [feature request](https://github.com/pouya-kia/dataproof-verifier/issues/new?template=feature_request.yml). Suspected vulnerabilities belong in GitHub's [private reporting flow](https://github.com/pouya-kia/dataproof-verifier/security), not public Issues. To validate a contribution locally after `.venv/bin/python -m pip install -e ".[dev]"`, run `.venv/bin/python -m ruff check .`, `.venv/bin/python -m ruff format --check .`, `.venv/bin/python -m mypy src`, `.venv/bin/python -m pytest -q`, and `git diff --check`; the [contributor guide](CONTRIBUTING.md) gives copy/paste setup and PR steps.

The [DataProof-100 engineering evaluation](docs/evaluation/dataproof-100-evaluation.md)
reports the Alpha's finite synthetic checks and the unchanged eligibility of
50 public-origin records, including the negative coverage result.

The [final post-change DataProof-100 comparison](docs/evaluation/dataproof-100-final-coverage.md)
retains all 50 original public-origin problems and 50 synthetic controls. It
does not claim that any original public-origin task was fully solved by the
earlier `0.1.0a2` candidate syntax. The `v0.1.0a1` release remains available separately.

For the current development source, read the [exact relational SQL and
workflow matrix](docs/relational-sql-contract.md), the [12 authored
full-contract controls](docs/evaluation/full-contract-sql-suite.md), and the
[architecture-era original-task accounting](docs/evaluation/dataproof-100-architecture-postchange.md).
The authored controls are not independent-user outcomes. The restored
private 100-ID ledger was reassessed on the exact current Wheel: 34 direct
authored fixtures retained their outcomes, while no public-origin task had
an unchanged executable full contract. Original-task success remains 0/50;
new syntax is not a substitute for missing developer requirements.
