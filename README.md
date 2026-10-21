# DataProof — experimental Alpha release candidate

DataProof is an offline, bounded SQL reasoning CLI. It works on small synthetic tables, not production databases. Its three workflows are distinct:

This local release candidate uses the approved release-preparation identifiers: distribution `dataproof-verifier`, import namespace `dataproof_verifier`, and command `dataproof-verifier`. It has not been registered or published on PyPI; install from this reviewed source or its locally built Wheel only. The unrelated PyPI `dataproof` project is not a dependency.

- **NoUndo:** find two legal source bags whose retained aggregate-view bags agree but whose downstream scalar KPIs differ.
- **Doppelgänger:** find one legal source bag on which declared existing SQL assertions are TRUE while a separately supplied invariant is FALSE.
- **Proof2Test:** turn a replay-validated Doppelgänger witness and a separately declared target-output contract into a restricted executable regression fixture.

`preflight` checks eligibility without searching. `replay` independently executes admitted SQL in DuckDB. `explain` presents an already validated positive witness as readable source and output bags. A found witness is concrete evidence only under the declared finite schema, domains, constraints, and SQL semantics. A bounded miss is **not** a universal proof. This Alpha is not evidence of production readiness, independent adoption, algorithmic novelty, or comparative speed.

## Install and try it

Python 3.11 or 3.12 is required for this Alpha. Installing dependencies may require a network; the installed core requires no account, API key, LLM, or cloud service. From this source directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/dataproof-verifier preflight no-undo examples/no_undo/daily_distinct.json
.venv/bin/dataproof-verifier check examples/no_undo/daily_distinct.json --output artifacts/no-undo
.venv/bin/dataproof-verifier replay artifacts/no-undo/witness.json
.venv/bin/dataproof-verifier explain artifacts/no-undo/witness.json
```

The NoUndo example has equal daily order-count, revenue, and distinct-customer summaries, but monthly distinct-customer KPIs of 1 and 2. The generated `replay.sql` ends with `REPLAY_OK` when run in DuckDB. Two bounded-negative controls are `examples/no_undo/constrained_customer.json` and `examples/no_undo/daily_sum.json`; each returns exit code 3, **not** a universal preservation proof.

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

## Exact finite scope

One source table, at most three rows per world, at most four columns and four declared domain values per column; finite `INTEGER` and `DATE` values with explicit NULL, primary-key and nullable-UNIQUE rules. NoUndo admits one retained grouped aggregate view and one scalar aggregate KPI. Supported aggregates are `COUNT(*)`, `COUNT(column)`, `COUNT(DISTINCT column)`, exact integer `SUM`, and direct integer `MIN`/`MAX`. A query may have one guarded row filter: integer-column equality to a signed integer literal, `IS NULL`, or `IS NOT NULL`. Doppelgänger admits one to four existing scalar assertions and one independent invariant. NULL, SQL UNKNOWN, duplicate bags, and empty inputs have explicit semantics. Unsupported joins, multiple retained views, compound predicates, HAVING, windows, arbitrary expressions, timestamps, floating-point arithmetic, and production data access fail closed. The full [semantics](docs/semantics.md), [limitations](docs/limitations.md), and [architecture](docs/architecture.md) are part of this candidate.

The CLI records assumptions, bounds, versions, hashes, witnesses, and replay artifacts. Reused output directories only clear unchanged DataProof-owned artifacts; unrelated files are preserved. Use separate directories for concurrent runs. See [artifact behavior](docs/limitations.md) and the demo. Scientific research scripts, raw runs, and manuscripts are not distributed in this production candidate.

## Contribute or report a problem

This candidate carries an [MIT license](LICENSE). Direct dependency pins and upstream license links are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Read [CONTRIBUTING.md](CONTRIBUTING.md), use the [reproducible issue template](ISSUE_TEMPLATE.md), or submit an original, possibly unsupported SQL task with [this intake template](ORIGINAL_SQL_PROBLEM_TEMPLATE.md). Read the [security reporting policy](SECURITY.md) before sharing a vulnerability. Do not submit confidential SQL, personal data, credentials, or proprietary schemas without permission. Unsupported and incomplete tasks are useful findings; do not simplify an original task solely to fit the current grammar.
