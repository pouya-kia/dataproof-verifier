# First run: a finite, offline SQL counterexample

Install the v0.1.0a4 source with Python 3.11 or 3.12:

```sh
git clone https://github.com/pouya-kia/dataproof-verifier.git
cd dataproof-verifier
python3.11 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/dataproof-verifier demo
```

This is a single command **after installation**, not a promise that installation
finishes in five minutes. The demo also works from an installed Wheel without a
source checkout or network access: run that environment's `dataproof-verifier demo`.
Use `demo --output-dir NEW_DIRECTORY` to preserve the generated evidence. The
directory must not already exist; the demo will not overwrite user files.

The researcher-authored synthetic example retains a per-day `COUNT(*)` and
`SUM` of *rolling-24-hour reported-volume snapshots*. It asks whether the
largest individual reported snapshot can still be reconstructed. Two legal
worlds can retain `(2026-10-01, 2, 30)` but have peaks 20 and 15 (illustrative
integer thousands of USDT). The solver may find a different legal pair. Its
positive result is replayed from serialized evidence, and the generated SQL is
executed again in a separate DuckDB connection. A second check adds `MAX` to
the retained view and returns `BOUNDED_NO_COUNTEREXAMPLE` with exit code 3.
An independent DuckDB/itertools check enumerates all 16 legal worlds, finding
two original loss pairs and no repaired pairs.

`COUNTEREXAMPLE_FOUND` is one legal finite witness, not proof of a real data
loss incident. `BOUNDED_NO_COUNTEREXAMPLE` means no pair exists in the declared
finite world/domain bounds, not a universal SQL theorem. `INCONCLUSIVE` means
the check did not establish either result, for example after a timeout. The
summary is **not actual daily traded volume**: summing overlapping rolling
reports would be a different metric. No production exchange data are used.

For your own task, begin with `dataproof-verifier preflight no-undo SPEC.json`
or `preflight doppelganger SPEC.json` to screen the original SQL. NoUndo asks
whether one retained grouped view determines a declared KPI. Doppelgänger
asks whether declared existing assertions can pass while a separate business
invariant is false. Proof2Test additionally needs an independently specified
expected target output; it does not infer a correct implementation. See the
[workflow demo](demo.md), [witness explanation](explain.md), [exact SQL
fragment](relational-sql-contract.md), and [limitations](limitations.md).

Unsupported joins/CTEs in the one-table workflows, rolling windows,
timezones, arbitrary dbt graphs and production data access are not converted
into supported cases. Report your unchanged original task via the
[public issue form](https://github.com/pouya-kia/dataproof-verifier/issues/new?template=original_sql_problem.yml),
including unknown details and unsupported SQL. Do not post confidential SQL,
personal data, credentials or proprietary schemas without permission. A
conventional SQL/dbt test is simpler when the desired input and output are
already known.
