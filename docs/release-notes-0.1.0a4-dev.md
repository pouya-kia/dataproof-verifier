# DataProof `0.1.0a4.dev0` — untagged development candidate

This document describes source that can be built for private review. It is
**not** a GitHub Release, Git tag or PyPI distribution. The released
`v0.1.0a1`, the untagged `0.1.0a3` candidate and their prior evidence remain
unchanged. The runtime distribution is `dataproof-verifier`, import namespace
`dataproof_verifier`, and CLI `dataproof-verifier`.

The bounded two-table NoUndo finite backend now uses a version-1 relational
plan for its active Python bag evaluation. One **nonrecursive, once-referenced
aggregate CTE or derived SELECT** may group admitted joined rows and feed one
second aggregate stage. The example below uses a retained grouped total that
cannot determine the peak per-order join fanout in its declared 18-world
finite model. DuckDB separately executes the admitted original SQL; the
positive witness is serialized, replayed and explained. A companion scalar
total KPI is complete bounded-negative over the same 18 worlds. Classic
one-table Z3 NoUndo, Doppelgänger and Proof2Test obligations and artifact
formats are unchanged. Historical versionless joined witnesses remain
readable; unknown plan versions fail closed.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/dataproof-verifier join preflight examples/join/aggregate_cte_fanout.json
.venv/bin/dataproof-verifier join check examples/join/aggregate_cte_fanout.json --output artifacts/aggregate-cte
.venv/bin/dataproof-verifier join replay artifacts/aggregate-cte/witness.json
.venv/bin/dataproof-verifier join explain artifacts/aggregate-cte/witness.json
```

The [exact SQL/workflow matrix](relational-sql-contract.md) and
[joined limits](bounded-join.md) are required reading. This does **not** add
arbitrary CTE graphs, three-table joins, scalar/correlated subqueries,
windows, timezone conversion, general dbt models or a shared solver across
the three different obligations. The two-table world representation,
original-SQL replay, and source resolver are still exactly two-sided; a
three-table feature cannot safely be inferred from the new plan node. The
finite search uses a cooperative deadline, not an OS-hard process/memory cap.
The SQLGlot admission, schema and world generation are shared by the Python
plan and DuckDB reference, so correlated errors remain possible.

A [12-task authored engineering suite](evaluation/full-contract-sql-suite.md)
performs 222 legal-world differential evaluations, separate reference
searches and serialized replay for nine positive controls, with three
complete finite negatives. These tasks reuse developer-authored examples;
they are neither external adoption nor a blind benchmark. The original
private DataProof-100 ledger was restored after the first candidate build.
An [exact-Wheel reassessment](evaluation/dataproof-100-architecture-postchange.md)
accounted for all 100 unchanged IDs: 34 direct authored controls retained
their outcomes, 28/28 complete finite references agreed and 20/20 positive
witnesses replayed. The 50 public-origin records still provide **zero complete
as-stated executable tasks**, so original-task success remains 0/50. Other
authored control types were not newly rerun. Paper 1, Paper 2 and Phase 6C
primary practical gates
remain negative. No scientific novelty, general speedup, production
readiness or broad SQL utility is established.

Before a separately authorized release, review the exact source commit and
privacy inventory; verify Python 3.11/3.12 Ubuntu PR **and post-merge** CI,
full local gates, fresh Wheel and sdist installs, CLI/replay, dependency and
license notices, artifact hashes and human approval. Do not create a tag,
GitHub Release, PyPI upload or claim a completed 100-ID reassessment merely
because this candidate builds.
