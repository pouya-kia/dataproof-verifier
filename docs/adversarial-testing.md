# Finite SQL adversarial testing

The short CI suite contains seed-stable Hypothesis properties in
`tests/test_adversarial_one_table.py` and `tests/test_adversarial_join.py`.
They generate legal finite source bags and compare DataProof's admitted SQL
evaluation with unchanged SQL executed in fresh, in-memory DuckDB connections.
Results are compared as full bags, including row multiplicity and SQL NULLs.
Row-order permutation and alias-renaming checks exercise invariances that
should hold for the admitted unordered queries.

Run the standard checks with `pytest -q tests/test_adversarial_one_table.py
tests/test_adversarial_join.py`. To increase the generated-example budgets, use
`DATAPROOF_STRESS=1 pytest -q tests/test_adversarial_one_table.py
tests/test_adversarial_join.py`; this longer mode is not the default CI gate.
Hypothesis shrinks a failure to a small source world. If a failure is found,
preserve its minimized world and original SQL as a deterministic regression.

The generated one-table properties exercise nullable grouping, COUNT variants,
SUM, MIN/MAX, guarded filters, duplicate rows, and PK/nullable-UNIQUE rules.
Tiny independent `itertools`/DuckDB world enumeration checks four solver
verdicts. The joined properties cover INNER, LEFT, RIGHT, FULL, composite keys,
outer unmatched rows, STRING, CASE/arithmetic, projection/aggregate CTEs, and
DATE/TIMESTAMP grouping from admitted examples. Local mutations deliberately
break nullable COUNT, COUNT DISTINCT, empty SUM, bag multiplicity, or NULL join
equality; the checks must reject these mutations. They do not claim to cover
all possible faults or SQL syntax.

Existing regression suites separately exercise Z3 UNKNOWN, timeouts, backend
errors, solver/DuckDB disagreement, serialized-evidence tampering, schema and
SQL rejection, symlink/ownership conflicts, and replay versioning. In
particular, see `test_fail_closed.py`, `test_artifact_lifecycle.py`,
`test_bounded_join.py`, `test_explain.py`, and `test_proof2test.py`. A rejected
query or inconclusive search is not counted as successful reasoning.

DuckDB execution is independent of the Python evaluator and Z3 formulas, but
these tests share DataProof's schema admission and finite-domain assumptions.
Finite exhaustive agreement establishes only the declared small bounds. The
synthetic [exchange-volume retention example](../examples/use_cases/exchange_volume_retention/README.md)
has a separate 16-world `itertools`/DuckDB reference oracle; it is not an
independently observed production defect or an original DataProof-100 success.
