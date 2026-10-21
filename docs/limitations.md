# Current limitations

The NoUndo limits are:

- One table, one grouped retained view, one scalar aggregate metric, at most three rows per world and at most four finite values per column. A result applies only to those explicit bounds and values.
- One direct grouping column and at most one guarded row predicate (`INTEGER =` signed integer literal, `IS NULL`, or `IS NOT NULL`) per query. `MIN`/`MAX` accept only one direct INTEGER column, not DATE or scalar two-argument forms. No compound or other `WHERE` conditions, joins, subqueries, `ORDER BY`, windows, UDFs, arithmetic expressions, multiple views, foreign keys, strings, decimals, floating point or timestamps. SQL must use DuckDB semantics.
- The current optimizer minimizes total synthetic source rows within the finite model and chooses a stable lexicographic witness. This is **not** a globally minimal SQL counterexample or a minimum among unrestricted databases.
- `BOUNDED_NO_COUNTEREXAMPLE` never means universal determinacy. SUM roll-up is not a theorem here; the included daily SUM case is checked only in its finite domain.
- No PostgreSQL or other engine differential claim, no general dbt integration beyond the narrowly scoped Proof2Test adapter, no production data access, no cloud adapter, no profiler, and no performance benchmark comparison.
- Replayed synthetic data may still encode user-entered identifiers in a spec. Use only synthetic or approved non-sensitive domains. Artifact directories are user-selected; review them before sharing.
- Python and DuckDB version changes may affect SQL behavior. The exact tested environment is recorded in each result; current public CI exercises Ubuntu with Python 3.11/3.12, not macOS.

The strongest open correctness risks are a SQLGlot AST change not caught by the guard, an SMT/DuckDB mismatch in an untested boundary case, and an untested platform-specific DuckDB behavior. Adversarial, exhaustive and replay tests reduce these risks but do not eliminate them.

An **unreleased, separate** [bounded two-table INNER JOIN check](bounded-join.md)
is available in development source. It does not extend the published
`v0.1.0a1` Wheel or the one-table/Z3 command. Its complete finite Python
search and DuckDB reference are capped at 500 analytical combined worlds;
they share admission/world-generation assumptions. Deadline checks are
cooperative, not an OS hard timeout or memory ceiling. Outer joins, filters,
dbt graphs and unrestricted SQL remain unsupported. No original public task
has been demonstrated solved unchanged by this addition.

Doppelgänger is a separate, one-dataset workflow. It accepts one synthetic table, one to four named existing-test assertions and one separately supplied invariant, each expressed as a guarded scalar aggregate compared with an integer literal. `NULL`/UNKNOWN is neither a passing test nor a confirmed invariant failure. It does not infer business rules, run arbitrary dbt tests or Python, connect to production, or prove test adequacy from a bounded miss. A supplied rationale is an input assertion, not independently established business truth. See the [exact contract](doppelganger.md).

Proof2Test exports only a validated Doppelgänger witness plus an explicitly supplied finite expected output bag. Its pytest target is a guarded same-schema one-table DuckDB SELECT, not an arbitrary SQL or Python implementation. Its dbt Core adapter emits only a one-ref local unit test for nonempty, non-NULL INTEGER fixtures; version and project compatibility outside the tested local setup are unverified. A passing fixture does not prove global target correctness or that the user-declared expected behavior is the right business policy. NoUndo export is unsupported. See the [exact export contract](proof2test.md).
