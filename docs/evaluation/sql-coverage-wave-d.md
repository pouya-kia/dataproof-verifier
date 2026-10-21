# Advanced SQL Wave D — finite timestamp reporting periods

The bounded two-table NoUndo backend now admits exact second-precision,
UTC-naive `TIMESTAMP` finite domains and direct-column `DATE_TRUNC` grouping
for `DAY` and `MONTH`. This permits finite period counts and distinct counts
over the already admitted aggregate expressions. NULL timestamps produce one
NULL group; empty grouped input produces an empty bag. A timestamp can also
be compared to another TIMESTAMP column in a guarded `WHERE`. The original
SQL is independently executed by DuckDB over every legal world in targeted
differential tests, including a month transition, duplicate source rows and
NULL timestamps. Serialized positive witnesses are replayed unchanged.

This is not timezone-aware or rolling analytics. The parser rejects offsets,
fractional seconds, implicit date/time conversions, unsupported bucketing
units, arbitrary date arithmetic and all `OVER` windows. In particular,
`ROW_NUMBER`, `RANK`, `DENSE_RANK` and ordered window frames would require
an explicit ordered intermediate relation and tie/frame semantics absent
from the current grouped-bag NoUndo IR. Treating unordered bag outputs as
ordered rows would be unsound; the finite verifier does not guess an order.
No production one-table Z3, Doppelgänger or Proof2Test timestamp support is
claimed. The full fragment remains subject to the 500-world analytical cap,
cooperative deadline and no hard process-memory limit.

The [monthly synthetic example](../../examples/join/monthly_timestamp_distinct.json)
demonstrates retained period counts versus an overall distinct-order KPI. It
is authored engineering evidence, not an authentic external case. The original
DataProof-100 public-origin tasks must retain their original requirements;
none is counted solved merely because a TIMESTAMP expression parses.

The private post-change derivative
`postchange-waved-a3-complete-100.jsonl` has SHA-256
`be7e28b7167ad60b2abc7f73d5f5151e8c3086a0ed0dae204d1d1d4a6fae6a78`.
All 100 original IDs are present. The 34 direct authored reruns had 28/28
available finite-oracle agreements, 20 valid positive replays and no changed
status. Thirteen further authored controls were run; 47/50 authored controls
were exercised, and A22/A27/A30 remained inadmissible. The 50 original
public-origin tasks remain **0/50 fully eligible and 0/50 solved**. The
original ledger and holdout first-run observations are unchanged.
