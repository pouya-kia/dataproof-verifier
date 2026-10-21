# Offline DataProof demo cue sheet

This is a screen-recording cue sheet, not a claim that setup or installation takes a measured amount of time. Install once as shown in the README, then record the following actual local terminal commands without editing their output:

```sh
.venv/bin/dataproof-verifier check examples/no_undo/daily_distinct.json --output artifacts/demo
.venv/bin/dataproof-verifier replay artifacts/demo/witness.json
.venv/bin/dataproof-verifier explain artifacts/demo/witness.json
.venv/bin/python -c 'import duckdb; con=duckdb.connect(":memory:", config={"enable_external_access":"false"}); print(con.execute(open("artifacts/demo/replay.sql").read()).fetchall())'
```

Show the two monthly values and equal retained daily rows in `artifacts/demo/witness.json`, then show the final `REPLAY_OK` assertion in `artifacts/demo/replay.sql` using a local DuckDB execution. The CLI's replay command already executes the serialized SQL independently. State the precise interpretation: the retained daily view fails to determine monthly distinct customers under this finite schema; no backup deletion or universal determinacy result is implied. Do not present a recording until the commands and unaltered logs have been rerun on the recording machine.

For the distinct Doppelgänger obligation, use a different output directory:

```sh
.venv/bin/dataproof-verifier doppelganger check examples/doppelganger/nonnegative_amount.json --output artifacts/doppel-demo
.venv/bin/dataproof-verifier doppelganger replay artifacts/doppel-demo/witness.json
.venv/bin/dataproof-verifier explain artifacts/doppel-demo/witness.json
```

Show the one synthetic `amount = -1` row, the declared nonempty test evaluating TRUE, and the separately declared no-negative-amount invariant evaluating FALSE. The invariant's rationale is user supplied; DataProof does not establish that any real organization's business rule is true. The result is finite-bound evidence of a test blind spot, not a universal adequacy verdict.

For the scoped Proof2Test follow-up, first install the documented development test dependency, then export from the versioned witness and run the **same generated test** against two supplied transformations:

```sh
.venv/bin/python -m pip install pytest
.venv/bin/dataproof-verifier proof2test export examples/doppelganger/evidence/witness.json --target examples/proof2test/clamp_amount.contract.json --format pytest --output artifacts/proof2test-demo
DATAPROOF_TARGET_SQL=examples/proof2test/defective.sql .venv/bin/pytest -q artifacts/proof2test-demo
DATAPROOF_TARGET_SQL=examples/proof2test/corrected.sql .venv/bin/pytest -q artifacts/proof2test-demo
```

The first pytest invocation should exit 1 because the target emits `-1` while the separately declared expectation is `0`; the second should exit 0. Do not cut the failed-test output from a recording. The example policy is synthetic and declared in the target contract, not inferred from the witness. The [export contract](proof2test.md) documents the narrow SQL and dbt Core boundaries.
