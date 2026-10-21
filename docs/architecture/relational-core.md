# Relational core ADR — version 1 compatibility slice

Status: implemented for the existing two-table finite NoUndo workflow and one
guarded aggregate CTE/derived pipeline. Broader multi-stage and cross-workflow
migrations remain pending. This ADR describes code in `join_model.py`,
`relational_pipeline.py`, `relational_core.py`, `join_reference.py`, and
`join_replay.py`, not a promise of arbitrary SQL support.

## Decision and obligation

NoUndo seeks two legal finite databases with equal full *bags* of retained
view rows and SQL-distinct scalar KPIs. Doppelgänger seeks one legal database
where all supplied assertions are SQL TRUE and a separately justified
invariant is SQL FALSE. Proof2Test requires a replay-validated Doppelgänger
witness **and** independently supplied expected target-output rows. These
obligations remain separate.

The joined workflow keeps the existing guarded SQLGlot admission and typed
`JoinQuery` in `join_model.py`. Its compatibility adapter compiles admitted
queries to `RelationalPlan(version=1)` containing `Scan`, `Join`, optional
`Filter`, and `Aggregate` nodes. One guarded aggregate CTE or derived SELECT
adds a `Materialize` node followed by a second `Aggregate`. The plan records source and output names;
`Ref(table,column)` was scope- and type-checked by admission. A `Scan` tracks
the source index, and every node tracks which source tables contribute its
row slots. The evaluator in `relational_core.py` is now the **only active
Python bag evaluator** of this joined fragment. `join_reference.py` retains
finite-world search and a separate DuckDB execution path, not duplicate
Python SQL semantics. The classic one-table/Z3 and Doppelgänger parsers and
solvers are deliberately unchanged. The plan is not yet a universal IR: it
admits only one materialized aggregate source referenced once, not arbitrary
CTE reuse, correlated subqueries or a third aggregation stage.

The evaluator keeps duplicate row instances. Equality joins do not match
NULL keys. Outer joins null-extend missing sides without reordering the
declared join. `Filter` keeps only SQL TRUE; UNKNOWN is filtered out.
Aggregate groups coalesce NULL key components. A grouped aggregate over no
rows emits no rows, whereas a scalar aggregate emits one row, with COUNT 0
and SUM/MIN/MAX NULL. View equality is `Counter` bag equality, not sorted-row
or set equality. A finite negative status requires full legal-world search
and a completed DuckDB reference with matching verdict. Timeouts, exceptions
and disagreement are inconclusive. The same 500-world analytical cap and
cooperative deadline apply; no OS-hard memory or query cancellation is
claimed. No witness minimality or universal determinacy is claimed.

## Trust and compatibility boundaries

DuckDB runs the original admitted SQL in an isolated in-memory connection
with external access disabled. The Python plan and DuckDB agree over the
same legal worlds but share schema parsing and world generation. This is an
independent SQL-execution differential check, not a wholly independent
oracle. The existing join witness schema remains version 1; new results
carry `plan_version: 1`. Serialized replay accepts historical schema-1 join
witnesses without a plan field, rejects an unknown plan version, and reruns
the original SQL. No classic witness or exit code changes. Hashes protect
internal consistency, not external authenticity of a rewritten bundle.

Only guarded SELECT ASTs are admitted. The parser excludes statements,
arbitrary functions, unsafe source clauses, unrecognized AST options and
unsupported nesting before DuckDB execution. This is defense in depth, not
a proof of hostile-SQL sandboxing. The source SQL length and finite domains
are capped. Source constraints use existing per-table legal-world checks.

## Dependency DAG and migration gate

1. Existing two-table parser and world generator -> version-1 plan adapter ->
   shared bag evaluator -> complete finite NoUndo search -> original-SQL
   DuckDB reference -> serialized replay. This is implemented and regression
   checked against existing joined cases.
2. Scoped materialized output names and types -> one aggregate/filter CTE
   admission -> second aggregate stage -> exhaustive tiny-domain differential
   tests -> existing NoUndo CLI and replay artifacts. **Implemented for the
   guarded two-table pipeline only.** General CTE reuse remains deferred.
3. Generic N-table legal-world representation and bound -> three-table
   declared join-tree admission/evaluation -> differential oracle. **Not yet
   implemented.** A two-table plan does not imply three-table support.
4. Independently checked scalar Boolean plan/replay contract -> optional
   Doppelgänger finite adapter -> separately justified Proof2Test export.
   **Not yet implemented.** Existing Z3 workflows stay stable meanwhile.

Subqueries and order-dependent windows require additional typed scope,
cardinality and tie semantics. They are rejected until reference checks can
cover them. One functioning vertical slice is preferable to an untested
general plan or a silent migration of the classic Z3 path.
