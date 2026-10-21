# Doppelgänger Phase 4 bounded contract

The obligation is to find one legal synthetic bag of rows `D` for which every separately declared existing test evaluates to SQL TRUE and a user-supplied business invariant evaluates to SQL FALSE. A different KPI value alone is not a defect. The user must supply a nonempty rationale for the invariant; DataProof checks the formal assertion, not the truth of that rationale.

The versioned JSON/YAML input has `schema_version: 1`, one `table`, `max_rows`, optional solver limits and output directory, `tests` (one to four named assertions), and a separate named `invariant`. Each assertion has `id`, `sql`, `op`, and integer `value`; the invariant also has `rationale`. An assertion computes one scalar aggregate query over the declared table and compares its result with the literal. Supported operators are `=`, `!=`, `<`, `<=`, `>`, `>=`. The SQL must be one guarded DuckDB `SELECT` of `COUNT(*)`, `COUNT(column)`, `COUNT(DISTINCT column)`, integer `SUM`, `MIN`, or `MAX`, with an explicit aggregate alias and at most one supported row filter. Arbitrary SQL, expressions, Python callbacks, joins, subqueries, and mutation are rejected. An empty test list is rejected rather than treated as vacuous coverage.

The table uses the existing finite `INTEGER`/`DATE` domains (one to four columns, up to three bag rows), nullability, primary-key and SQL UNIQUE semantics. Duplicate source rows are legal unless a key forbids them. `COUNT` returns zero on empty/all-NULL input; `SUM`/`MIN`/`MAX` return NULL. A comparison with NULL is UNKNOWN. A test passes only on TRUE; an invariant is violated only on FALSE. UNKNOWN in either position is not silently coerced.

Z3 encodes legal row slots and the admitted aggregates for one dataset, checks test satisfiability separately from the blind-spot obligation, and minimizes row count then finite-domain cell codes. `INCONSISTENT_TESTS` means no legal test-passing dataset in the finite bound. `BOUNDED_NO_BLIND_SPOT` means test-passing datasets exist but none has a confirmed invariant FALSE within the bound; neither status is an unrestricted proof. Timeout, memory and unexpected solver errors are `INCONCLUSIVE`. `UNSUPPORTED`, `INVALID_INPUT`, and `INVALID_CANDIDATE` fail closed. `BLIND_SPOT_FOUND` is emitted only after independent DuckDB evaluation and serialized replay.

DuckDB runs the original accepted SQL, not SQL reconstructed from Z3 terms. It independently checks declared row legality, every test result, the invariant result and the replay script. An isolated in-memory connection has external access disabled. A candidate mismatch or backend exception cannot publish a witness. Owned artifact files follow the existing hash-checked lifecycle; unrelated output files are never removed.

## Acceptance matrix written before implementation

| Case | Expected result |
| --- | --- |
| Explicit nonnegative-amount invariant missed by nonempty-row test | Legal, replayable blind-spot witness |
| Existing test prohibits the same forbidden amount | Bounded no blind spot |
| Contradictory tests or impossible row count | Inconsistent tests |
| Empty/all-NULL aggregate, SQL UNKNOWN, duplicate bag rows | Exact three-valued and bag behavior |
| Primary key, nullable UNIQUE and NOT NULL | Only legal synthetic worlds |
| Unsupported SQL, DDL, malformed spec, unsafe assertion | Fail closed without a witness |
| Timeout, UNKNOWN, solver/backend fault | Inconclusive without stale evidence |
| Deliberately corrupt candidate or serialized witness | Independent rejection |
| Reordered domain or rows; repeated runs | Stable scoped outcome and safe artifacts |
| Existing `dataproof-verifier check` and `replay` | Unchanged behavior and full regressions |

An independent tiny exhaustive enumerator and direct DuckDB evaluation will be compared with Z3 for generated legal cases. A found witness is evidence only for its declared finite input. The related-work comparison and publication readiness remain open; no performance or novelty claim follows from this slice.
