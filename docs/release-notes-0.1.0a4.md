# DataProof v0.1.0a4 — experimental GitHub Alpha prerelease

DataProof searches for small legal SQL counterexamples under declared finite
assumptions and records independently replayable DuckDB evidence. This release
is distributed as a GitHub Wheel and source archive, **not on PyPI**. It is not
production-ready and does not establish independent adoption, scientific
novelty, a general speed advantage, or support for unrestricted SQL. The
earlier `v0.1.0a1` release remains available and unchanged.

## What is included

- The existing NoUndo, Doppelgänger, Proof2Test, preflight, replay and
  explanation workflows retain their separate one-table contracts. NoUndo
  searches for two legal worlds with equal retained-view bags and a different
  declared scalar KPI. Doppelgänger searches for one world passing declared
  assertions while violating a separately supplied invariant. Proof2Test
  needs a replay-validated witness and an independently supplied expected
  output; it does not infer business truth.
- The separate bounded two-table NoUndo workflow admits guarded INNER,
  LEFT, RIGHT and FULL equijoins, restricted three-valued WHERE predicates,
  limited ASCII STRING and UTC-naive TIMESTAMP values, at most two grouping
  expressions, and one nonrecursive, once-referenced aggregate CTE or derived
  source feeding one outer aggregate. It uses complete finite Python bag
  search plus original-SQL DuckDB execution, not the one-table Z3 encoding.
  See the [exact joined contract](bounded-join.md) and [workflow matrix](relational-sql-contract.md).
- `dataproof-verifier demo` runs an installed, offline synthetic exchange-volume
  retention example. Two legal worlds keep the same daily COUNT/SUM bag but
  have different largest *reported rolling-24-hour snapshots*. Serialized
  and separate DuckDB replays validate the witness. Adding MAX to the retained
  summary returns a **bounded-negative**, not a universal proof. An independent
  DuckDB enumeration covers all 16 declared legal worlds. These overlapping
  snapshots are **not actual daily traded volume** or a production incident.
- Adversarial, property-based and differential engineering tests exercise the
  supported finite semantics. The release preserves existing artifact formats
  and fail-closed rejection of unsupported input or validation disagreement.

## Install and try

Use Python 3.11 or 3.12 in a fresh virtual environment. Download the
`dataproof_verifier-0.1.0a4-py3-none-any.whl` asset from the
[v0.1.0a4 prerelease](https://github.com/pouya-kia/dataproof-verifier/releases/tag/v0.1.0a4),
then run:

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install ./dataproof_verifier-0.1.0a4-py3-none-any.whl
.venv/bin/dataproof-verifier demo
```

The `demo` command works outside a source checkout and uses no cloud account,
LLM or API key. Dependency installation may require a network. Use
`demo --output-dir NEW_DIRECTORY` to retain its artifacts without overwriting
an existing path. See the [first-run guide](first-five-minutes.md).

## Exact limitations and evidence

Classic one-table NoUndo and Doppelgänger admit at most three rows, four
columns and four declared domain values per column in their guarded
INTEGER/DATE fragment. The separate two-table NoUndo path admits at most two
rows and three columns/effective values **per source**, with a 500-world
analytical combined cap. It does not implement three-table joins, general
CTE graphs, scalar subqueries, windows, arbitrary dbt projects, timezone
conversion, incremental state or production database access. Its deadline
is cooperative, not an OS-hard process/memory limit. DuckDB query execution
is separate from the finite Python evaluator, but admission, schema and
world generation are shared. A finite no-witness result is not a theorem
about unbounded databases. The [limitations](limitations.md) and [semantics](semantics.md)
give the detailed contracts.

All examples are synthetic or developer-authored. The historical DataProof-100
public-origin tasks remain 0/50 fully eligible and solved as stated. The
separate preregistered Paper 1, Paper 2 and Phase 6C studies did **not** meet
their primary practical-success criteria; this release does not revise those
findings. No independent-user effectiveness claim is made.

DataProof is licensed under [MIT](../LICENSE). Direct runtime pins and
upstream license references appear in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
The macOS Z3 wheel has a known platform-tag metadata caveat: the installed
CLI can work while `pip check` reports an unsupported wheel on that platform.
Report original, even unsupported, SQL problems using the
[privacy-conscious issue form](https://github.com/pouya-kia/dataproof-verifier/issues/new?template=original_sql_problem.yml).
