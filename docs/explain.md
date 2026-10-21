# Read-only witness explanations

`dataproof-verifier explain PATH/TO/witness.json` prints a plain-text explanation of a
positive NoUndo or Doppelgänger witness. It performs no solver search and writes
no artifacts. A successful explanation requires a schema-1 positive witness,
its matching `result.json`, the exact `replay.sql`, and a fresh independent
DuckDB replay. If a DataProof ownership marker is present, the three evidence
files must also match its recorded hashes. Committed example evidence predates
the marker and is accepted only after the other checks succeed.

```sh
dataproof-verifier explain examples/no_undo/evidence/witness.json
dataproof-verifier explain examples/doppelganger/evidence/witness.json
```

The NoUndo output labels D1 and D2 source rows, shows retained view rows as
unordered bags with explicit multiplicities, and compares the replayed KPI
values. `NULL` and `DATE` are displayed explicitly; grouped aggregate columns
use their admitted SQL projection names. Equal retained bags and unequal KPI
values are a **bounded counterexample** to determinacy under the declared
finite schema, not a universal statement about other data or deletion of source
records.

The Doppelgänger output shows the one synthetic dataset, each supplied test's
actual scalar value and SQL `TRUE` comparison, and the separately supplied
invariant's actual scalar value and SQL `FALSE` comparison. SQL `UNKNOWN` is
neither a passing existing test nor a confirmed invariant violation. The
rationale is user-provided and DataProof does not establish its real-world
correctness. Proof2Test additionally requires a separate target-output
contract; an explanation does not infer one.

The command reports the witness, matching result and replay-SQL paths and a
replay command. It does not change existing `check`, `replay`, `--json`, export,
or exit-code contracts. A missing, inconsistent, symlinked or malformed
evidence file yields `EXPLANATION_UNAVAILABLE` and a nonzero exit. No negative,
unsupported, invalid or inconclusive result can be explained as a positive
witness. Copied evidence can be checked for internal consistency but is not a
cryptographic authenticity signature: without the original input file, this
command cannot prove that an `input_sha256` corresponds to a live source file
or detect a self-consistently rewritten bundle without an external trusted
hash. Only run this command on trusted, synthetic evidence; DuckDB is
configured without external access, but replaying untrusted SQL is not a
substitute for OS process isolation.
