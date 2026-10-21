# Proof2Test Phase 5 export contract

Research question: Can a previously replayed Doppelgänger counterexample be turned into a portable, executable regression that rejects a declared defective SQL transformation and accepts a separately specified corrected transformation on the same synthetic input? The competing explanation is that a test may merely restate the witness, overfit one row, or mistake observed output for a business requirement. A passing generated test therefore establishes only the explicitly declared finite fixture behavior, not general correctness or a new theorem.

The initial contract is Doppelgänger witness schema version 1 plus a separate Proof2Test target contract schema version 1. Its required fields are `schema_version: 1`, `target_kind: single_table_sql`, a simple `model_name` distinct from the source table, `expected_rows` in source-column order, and a nonempty `expected_behavior` rationale. The target must return that expected output bag on this witness, with the source invariant SQL TRUE when evaluated on the output under the same table name in a separate connection. The rationale and expected rows are explicitly supplied by the user; DataProof does not infer them from the failing witness. The source invariant remains independently revalidated on the witness and must be SQL FALSE. For the example, the declared policy is to clamp negative `amount` to zero; an identity transform is defective on the witness and `GREATEST(amount, 0)` satisfies the declared example expectation. This does not establish that clamping is the right policy for any real pipeline.

The generated pytest test uses an isolated in-memory DuckDB connection, loads the exact synthetic witness rows, runs a supplied read-only single-table SQL transformation, compares its output as a bag to the declared expected rows, and evaluates the original invariant with SQL three-valued logic. The executable test requires `DATAPROOF_TARGET_SQL` to name the implementation SQL file and the installed DataProof package (including DuckDB and SQLGlot). The only admitted target projections are direct declared columns and `GREATEST(integer_column, 0)`, in original column order, with at most one existing guarded row filter. Joins, subqueries, UDFs, other expressions, DDL/DML and other dialects are rejected. The target is capped at 4096 bytes, executes over at most three source rows with a 128 MB DuckDB memory cap and a five-second interrupt timer. Absence, parse failure, unsupported constructs, SQL UNKNOWN, timeout, or backend errors cannot be a pass. The fixture records source-witness and target-contract byte hashes, schema versions, source assertion SQL, and explicit rows. Output paths and free-text rationales are omitted from the fixture to avoid copying private notes; hashes are provenance, not authenticity signatures. No production connection or LLM is used.

The conservative dbt adapter emits one dbt Core unit-test YAML with inline `given` input rows and `expect` output rows. It requires an additional `dbt_model_sql` target-contract field containing exactly one `{{ ref('source_table') }}` token; after substituting that token, its SQL must pass the same guarded target parser. It supports only nonempty, non-NULL INTEGER fixtures and one local SQL model with one `ref` parent. Copy `unit_tests.yml` into the target project's `models/` directory, ensure the named parent model exists in the local DuckDB warehouse, and run the named unit test. It does not modify the user's dbt project or claim support for arbitrary dbt models, sources, incremental materializations, macros, cloud warehouses, or other adapters. The YAML format was executed with dbt Core 1.10.23 and dbt-duckdb 1.10.0; other version combinations remain unverified. [dbt's unit-test documentation](https://docs.getdbt.com/docs/build/unit-tests) requires the YAML in `models/` and all `ref` parents in `given`.

## Executable example

```sh
dataproof-verifier proof2test export examples/doppelganger/evidence/witness.json \
  --target examples/proof2test/clamp_amount.contract.json \
  --format pytest --output artifacts/proof2test-demo
DATAPROOF_TARGET_SQL=examples/proof2test/defective.sql pytest -q artifacts/proof2test-demo
# Expected: 1 failed; actual bag ((-1,),) differs from expected ((0,),).
DATAPROOF_TARGET_SQL=examples/proof2test/corrected.sql pytest -q artifacts/proof2test-demo
# Expected: 1 passed.
```

The [versioned pytest output](../examples/proof2test/generated_pytest/fixture.json) and [dbt unit-test YAML](../examples/proof2test/generated_dbt/unit_tests.yml) are executable golden examples. `EXPORTED` is exit 0; `UNSUPPORTED` is exit 5; malformed input or output conflicts are `INVALID_INPUT` exit 6; unexpected backend errors are `INCONCLUSIVE` exit 8. On unsuccessful export no new test artifact is published. An existing output directory is reusable only when every generated file is byte-identical; any unrelated, changed, or symlinked file causes a conflict without overwrite. Do not export concurrently into one directory.

NoUndo is `UNSUPPORTED`: its pair-world non-determinacy witness is not a single input/output transformation oracle. Arbitrary SQL, joins, subqueries, UDFs, dialect translation, cloud adapters, and unverified dbt features remain outside this export contract. Published paper-readiness stays `NOT_READY`.

## Acceptance matrix written before implementation

| Case | Required result |
| --- | --- |
| Valid schema-1 Doppelgänger witness with replay SQL and evaluations | Independently revalidate constraints, original SQL and recorded outputs before export |
| Source invariant FALSE, declared target expected bag and original invariant TRUE on that bag | Emit deterministic executable fixture and provenance |
| Defective versus corrected SQL over the same fixture | Actually run one generated pytest test: defective FAIL for output/invariant mismatch, corrected PASS |
| Same inputs exported twice to one directory | Identical owned files; no unintended overwrite |
| Modified or unrelated output file, symlink or unsafe output directory | Conflict; preserve user files |
| Tampered rows, SQL, evaluations, replay SQL or unsupported witness version | Fail closed; no test artifact |
| Missing, malformed, incompatible or false-expected target contract | INVALID_INPUT or UNSUPPORTED; no artifact |
| Unsupported or mutating target SQL, missing target, backend exception | Generated test FAIL, never silently PASS |
| NULL, duplicate bags, empty input/output, PK, UNIQUE, NOT NULL | Exact fixture legality and bag/three-valued behavior |
| dbt Core unit-test adapter | Inline given/expect rows; real defective FAIL and corrected PASS where compatible local dbt is available |
| Existing NoUndo and Doppelgänger CLI/replay | Unchanged and covered by full regression suite |
