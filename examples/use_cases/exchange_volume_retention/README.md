# Exchange-volume snapshot retention (synthetic)

This practitioner-inspired example models a polling pipeline that records a
rolling 24-hour *reported* trading-volume snapshot. It is researcher-authored
synthetic engineering evidence, **not** an observed production incident, an
independently supplied developer task, or a live exchange data set. The unit is
illustrative integer thousands of USDT. Real API values need not be integers.
Adding overlapping rolling-24-hour snapshots is **not** actual daily traded
volume; `sampled_volume_total` is only the sum of recorded samples.

The retention job keeps `day`, `COUNT(*)` and `SUM(volume_24h_kusdt)` and then
discards individual polls. An alert needs `MAX(volume_24h_kusdt)` across polls.
Can the retained summary determine that peak? In the declared one-day,
at-most-two-row model, the answer is no. `loss.json` describes the source table,
finite domains, key, retained SQL and KPI. Two legal golden worlds in
`golden_worlds.json` both produce the retained bag
`(2026-10-01, 2, 30)`, while their peak KPIs are 20 and 15.

`repaired.json` adds `MAX(volume_24h_kusdt) AS retained_peak` to the retained
view, without changing the KPI. Within **this** declared finite model, a
complete 16-world independent enumeration finds no remaining pair with equal
repaired bags and different KPIs. This is not a universal SQL determinacy proof.
Another practical repair is to retain the original polls; whether that is
allowed depends on a real retention and storage policy not asserted here.

## Reproduce from a clean source installation

Install the current development source and its CLI according to the repository
README, then run from this repository root. Choose a new output directory for
each invocation; never use `examples/` as the output directory.

```sh
dataproof-verifier preflight no-undo examples/use_cases/exchange_volume_retention/loss.json --json
dataproof-verifier check examples/use_cases/exchange_volume_retention/loss.json --output /tmp/dataproof-exchange-loss
dataproof-verifier replay /tmp/dataproof-exchange-loss/witness.json
dataproof-verifier explain /tmp/dataproof-exchange-loss/witness.json
dataproof-verifier preflight no-undo examples/use_cases/exchange_volume_retention/repaired.json --json
dataproof-verifier check examples/use_cases/exchange_volume_retention/repaired.json --output /tmp/dataproof-exchange-repaired
python examples/use_cases/exchange_volume_retention/oracle.py
```

Use fresh, nonexisting output paths in place of the `/tmp` examples. Expected
statuses/exit codes: both preflights `ELIGIBLE`/0; original check
`COUNTEREXAMPLE_FOUND`/0; serialized replay and explanation/0; repaired check
`BOUNDED_NO_COUNTEREXAMPLE`/3. The solver need not return the golden worlds;
any legal pair is acceptable only after independent DuckDB validation.

The standalone `oracle.py` does **not** call DataProof's world generator,
parser, plan evaluator or solver. `itertools` yields exactly 16 legal worlds:
one empty, six one-row and nine two-row worlds with unique `poll_id`. It runs
the **unchanged SQL** in isolated DuckDB connections for every world, compares
complete unordered output bags with multiplicities, checks the golden worlds,
and counts positive pairs for the original and repaired views. At the current
fixture, it finds 2 original witness pairs and 0 repaired witness pairs.
`tests/test_exchange_volume_retention.py` additionally checks the actual CLI
result and executes its serialized `replay.sql` in a fresh DuckDB connection.
DuckDB execution is independent of the Z3 formula, although the shared SQL
text and finite problem specification remain common assumptions.

An ordinary regression test on the two golden databases is simpler if those
two input instances are already known and the only need is to check their
expected outputs. DataProof adds a *search* for a second legal database that
preserves the retained view while changing the separately declared KPI, a
replayable bounded counterexample, and a bounded check of the proposed repair.
It does not infer the KPI or retention policy. The historical DataProof-100
count of independently solved original public tasks remains **0/50**.
