# Static eligibility preflight

Use `dataproof-verifier preflight no-undo SPEC.json` or
`dataproof-verifier preflight doppelganger SPEC.json` before a solver search. Add `--json`
for a machine-readable status, reason, declared limits and caution. The command
uses the same schema and SQL validators as the corresponding `check` command.
It reads the input specification only: it does not solve, execute SQL, write a
result, touch the specification's `output_dir`, or create a witness. An
unexpected validator failure is `INCONCLUSIVE`, never `ELIGIBLE`.

`ELIGIBLE` exits 0; `UNSUPPORTED` exits 5; `INVALID_INPUT` exits 6; and an
unexpected validation error exits 8. Existing search/replay statuses and exit
codes are unchanged. `UNSUPPORTED` means the requested feature is outside the
admitted fragment; `INVALID_INPUT` means the specification is malformed or
violates an input bound. The reason is the authoritative validator's message.
Some SQLGlot rejection messages identify a clause only generically; preflight
does not guess which unsupported construct the user intended or rewrite SQL.

## Copyable synthetic starters

- [NoUndo starter](../examples/preflight/no_undo_starter.json): one `orders`
  table, a daily distinct-customer view and a monthly distinct-customer KPI.
- [Doppelgänger starter](../examples/preflight/doppelganger_starter.json): an
  existing nonempty-order assertion and a separately declared synthetic
  nonnegative-amount invariant. Its rationale is an input assertion, not an
  independently verified business requirement.
- [Rejected JOIN example](../examples/preflight/unsupported_join.json): a
  NoUndo view requesting a second table. It must report `UNSUPPORTED`, not
  silently drop the join.

For example:

```sh
dataproof-verifier preflight no-undo examples/preflight/no_undo_starter.json --json
dataproof-verifier preflight doppelganger examples/preflight/doppelganger_starter.json
dataproof-verifier preflight no-undo examples/preflight/unsupported_join.json
```

Replace the synthetic columns/domains with approved finite values only. Declare
one table, 1–4 `INTEGER`/`DATE` columns and 1–4 values per declared domain;
`nullable`, primary-key and nullable-UNIQUE constraints must match the intended
source semantics. Set `max_rows` from 0 through 3. NoUndo needs exactly one
grouped retained view and one scalar KPI. Doppelgänger needs 1–4 existing
scalar-aggregate assertions and one separately justified invariant. Admitted
aggregates are `COUNT(*)`, `COUNT(column)`, `COUNT(DISTINCT column)`, integer
`SUM`, `MIN` and `MAX`. Each query may use at most one supported row filter:
integer-column equality to an integer literal, `IS NULL` or `IS NOT NULL`.
Joins, compound predicates, arbitrary SQL and additional models remain
unsupported. See [full limitations](limitations.md).

`ELIGIBLE` means only that static input validation passed. It does **not**
guarantee a counterexample, solver completion, DuckDB replay success or
universal correctness. A search may later return `INCONCLUSIVE` due to a
timeout, memory limit or backend problem. A `BOUNDED_NO_COUNTEREXAMPLE` or
`BOUNDED_NO_BLIND_SPOT` result means no witness was found within the declared
finite scope, not that the property holds for all possible data. Contradictory
Doppelgänger tests can instead produce `INCONSISTENT_TESTS`.

Proof2Test has no standalone static eligibility verdict. Its exporter requires
a **replay-validated Doppelgänger witness** and a separate target contract
declaring an expected output bag and rationale; both require DuckDB checks
that this static preflight intentionally does not perform. See the
[Proof2Test contract](proof2test.md) and its
[synthetic target-contract example](../examples/proof2test/clamp_amount.contract.json).

## Editable-environment troubleshooting

If a macOS editable install has a `dataproof-verifier` entry point but raises
`ModuleNotFoundError`, first verify the installed package and the editable
`.pth` file with that environment's `python -m pip show -f dataproof-verifier` and
`ls -lO` on the listed `.pth` file. Python skips a `.pth` file marked with
macOS's `hidden` flag. **Only if that exact file is the cause**, remove the
flag from that file with `chflags nohidden PATH_TO_VERIFIED_PTH`, then retry
`dataproof-verifier --help`. This changes file metadata, not package code. A separate
new virtual environment and `python -m pip install .` is a safer fallback;
do not delete or overwrite an existing environment to troubleshoot it.

Separately, the currently pinned `z3-solver==5.3.1.0` macOS wheel installs and
the CLI runs, but a fresh macOS `pip check` can report an unsupported platform:
the wheel filename advertises macOS 13.0 while its internal metadata records
13.3. This is an [upstream wheel-tag issue](https://github.com/Z3Prover/z3/issues/10689),
not evidence that preflight or a solver result is valid or invalid. Do not
silently edit installed wheel metadata or change solver versions to suppress
the warning; any dependency update needs its own compatibility gate.
