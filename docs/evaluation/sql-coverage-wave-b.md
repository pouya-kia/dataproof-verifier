# Advanced SQL Wave B — bounded composite and outer equijoins

This is an in-progress `0.1.0a3.dev0` **engineering** extension in the
separate finite two-table NoUndo backend. It is not in the published Alpha
`v0.1.0a1` and it is not independent-user or scientific performance evidence.

The admitted original DuckDB SQL has exactly one explicit INNER, LEFT, RIGHT
or FULL [OUTER] JOIN between the two declared tables, with one or two
distinct, same-type direct column equalities in `ON`. Every matched pair is
retained with bag multiplicity. RIGHT/FULL generate one NULL-extended row for
each unmatched right row instance, and FULL also retains unmatched left row
instances. `WHERE` remains a post-extension SQL three-valued filter; it is
not moved into `ON`. The view may group by one or two direct columns from
either side, including generated NULL components. PK and nullable-UNIQUE
schema constraints retain their previous semantics. New foreign-key rules
were **not** added. Exact domain/row/world limits and all rejected forms are
in the [bounded join contract](../bounded-join.md).

On targeted small schemas, the Python bag evaluator and DuckDB execution of
the original admitted SQL agreed for every legal world across all four join
forms with composite nullable/string keys, duplicates, empty sides, generated
NULL grouping, COUNT and post-join filters. Positive RIGHT and FULL witnesses
passed independent serialized DuckDB replay; zero-input cases were complete
bounded negatives. The [RIGHT example](../../examples/join/right_missing_match.json)
is synthetic: a retained count of one can accompany zero or one matched
order. Shared schema admission/world enumeration remain correlated-error
risks. The 500 analytical-world cap and cooperative deadline remain; no hard
process memory ceiling or universal determinacy proof is claimed.

The original DataProof-100 baseline and holdout were not modified. The
private post-change 100-ID derivative is
`postchange-waveb-a3-complete-100.jsonl`, SHA-256
`b6ff45754e887ec78ee21f06320666d9c3986cddacfd03451077a9f39c826094`.
Its 34 direct authored obligations retained 28 complete finite-oracle
agreements, zero disagreements, 20 valid positive serialized replays and no
status change. Thirteen further authored controls were run separately; 47/50
authored controls were exercised, while A22/A27/A30 remain inadmissible.
The 50 original public-origin records remain **0/50 fully eligible and 0/50
solved**, with 29 unsupported as stated, two lacking original contracts and
19 not applicable. This is not an estimate of SQL coverage in the wild.

Three-table joins remain unsupported. This is a concrete architecture and
verification boundary: the `JoinSpec`, world type, parser alias map,
candidate serializer and DuckDB replay are all explicitly two-sided. Merely
allowing a third parsed JOIN would misstate legal-world completeness and
null-extension behavior. A future extension would need a generalized
three-table legal-world enumerator, typed alias/scope resolution, correct
left-deep versus nested outer-join grouping, independent DuckDB all-world
checks, explicit combined-world caps and serialized replay regression tests.
Semi/anti/lateral/cross joins, arbitrary `ON` filters, more than two equality
keys and foreign-key declarations remain rejected. Paper 1, Paper 2 and
Phase 6C negative primary practical results remain unchanged.
