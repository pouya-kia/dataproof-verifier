# Advanced SQL Wave A — bounded expression slice

This document covers the in-progress `0.1.0a3.dev0` source, **not** the
published `v0.1.0a1` release or the preserved `0.1.0a2` candidate. It is an
engineering regression, not a scientific benchmark or independent-user study.

The separate, complete finite two-table NoUndo backend now admits finite
printable-ASCII `STRING` domains (1–32 characters), direct string equijoins,
case-sensitive binary equality/inequality filters, grouping, `COUNT` and
`COUNT(DISTINCT ...)`. It also admits integer addition/subtraction with a
statically checked signed-32-bit domain interval, identity `CAST(... AS
INTEGER)`, and searched/simple `CASE` expressions with up to three typed arms
inside aggregate arguments. A missing `ELSE` yields SQL NULL. Compound WHERE
still uses SQL TRUE/FALSE/UNKNOWN. Exact input caps, accepted grammar and
unsupported casts/collations are in [the contract](../bounded-join.md).

The one-table Z3 NoUndo, Doppelgänger and Proof2Test grammars are **unchanged**.
Neither a parser acceptance nor a finite witness implies general SQL support.
For the new slice, the Python finite evaluator and DuckDB execution of the
original admitted query were compared on every legal world of targeted small
schemas, including NULL, duplicate bags, empty joins, string case sensitivity,
CASE arms and overflow rejection. Shared schema admission and world enumeration
remain correlated-error risks. The 500-world cap and cooperative timeout remain;
there is no OS-hard memory or child-process ceiling for joined search.

The immutable original DataProof-100 catalog and first-run evidence were not
changed. A new private, versioned post-change derivative records all 100 IDs.
Its direct rerun executed 34 synthetic obligations: 28 complete finite-oracle
agreements, zero disagreements, 20 positive serialized replays and no status
changes. Thirteen further authored controls were run separately, including
expected generated-test failures, invalid/unsupported exports, mock-only
resource classifications and artifact isolation. Thus 47/50 authored controls
were exercised; A22/A27/A30 remain inadmissible. All 50 public-origin records
retain their original denominator: **0/50 fully eligible and 0/50 solved**;
29 remain unsupported as stated, two lack complete original contracts and 19
are not applicable to a DataProof verification obligation. New isolated syntax
does not supply absent retained views, KPIs, invariants or expected output.

The private derivative is
`postchange-wavea-a3-complete-100.jsonl` (SHA-256
`b7acfd89b86964fed7570a284e22afccb687575f7b355d348e4494e6690601ad`).
It contains local paths and is **not published**. This summary does not expose
third-party source text or raw local logs. Paper 1, Paper 2 and Phase 6C failed
primary practical gates remain unchanged. No general speed or novelty claim
follows from this feature work.

Further Wave A expressions and Waves B–D are not represented by this slice.
RIGHT/FULL/three-table joins, CTEs/subqueries, timestamps/periods and windows
remain unsupported until separately implemented and independently checked.
