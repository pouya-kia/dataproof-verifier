# Relational SQL contract — `0.1.0a4` release

This is a **finite Alpha-release contract**, not the grammar of the
earlier `v0.1.0a1` Wheel. Use `dataproof-verifier join preflight SPEC` before
search. The full [joined syntax and limits](bounded-join.md) remain normative;
this page makes workflow and backend boundaries explicit.

| Workflow | Parser and backend | Admitted SQL | Independent check | Not inherited |
| --- | --- | --- | --- | --- |
| Classic NoUndo | Guarded one-table IR; Z3 bounded pair search | One retained grouped aggregate, one scalar KPI, INTEGER/DATE, max 3 rows and 4 columns/domains, PK/nullable UNIQUE, one optional guarded predicate | DuckDB original SQL plus tiny complete reference enumerator | Joins, STRING, TIMESTAMP, CTEs |
| Joined NoUndo | SQLGlot guarded admission; version-1 finite bag plan; max 500 analytical two-table worlds | Two declared tables with max 2 rows/table and 3 columns/effective values, 1–2 typed equijoin keys, INNER/LEFT/RIGHT/FULL; restricted three-valued WHERE, CASE/integer arithmetic, up to two direct grouping keys, direct aggregate arguments, naive TIMESTAMP day/month grouping; projection-only row-preserving CTE sources **or** one nonrecursive, once-referenced grouped aggregate CTE/derived source with a second aggregate stage | Separate DuckDB execution of admitted **original SQL** on all legal worlds; serialized positive replay | Z3, three-table trees, general CTE graphs, nested scalar subqueries, windows, timezone conversions |
| Doppelgänger | Guarded one-table scalar assertion IR; Z3 | 1–4 existing assertions and a separately declared invariant over the original INTEGER/DATE fragment | DuckDB tests must be SQL TRUE and invariant SQL FALSE, plus finite reference | Joined or materialized plans; invariant inference |
| Proof2Test | Validated Doppelgänger witness plus separate target-output contract | Restricted one-table target SELECT / limited dbt unit-test YAML adapter | Generated pytest compares the declared output bag; original invariant is a consistency guard | NoUndo pair export; automatic expected output; generic dbt graph |

The shared plan is **currently used by joined NoUndo only**. The original
one-table Z3 and other workflows are deliberately not routed through a plan
whose admission does not encode their obligations. This is architectural
reuse, not a claim that every command accepts the same SQL.

Joined NoUndo admits one retained view and one scalar KPI, each as one SELECT.
The new aggregate pipeline is shaped like:

```sql
WITH x AS (
  SELECT o.cid AS cid, o.id AS oid, COUNT(*) AS n
  FROM orders AS o INNER JOIN customers AS c ON o.cid = c.cid
  GROUP BY o.cid, o.id
)
SELECT x.cid AS cid, SUM(x.n) AS total FROM x GROUP BY x.cid
```

The metric may independently use `SELECT MAX(x.n) AS peak FROM x` after
the same admitted CTE. The inner grouped output is a materialized **bag**.
The outer query may group by one or two direct output columns and use direct
`COUNT(*)`, `COUNT(col)`, `COUNT(DISTINCT col)`, or INTEGER `SUM/MIN/MAX`.
`HAVING`, outer WHERE, multiple/recursive CTEs, extra joins, correlated
references, arbitrary expressions over the materialized fields, `ORDER BY`,
`LIMIT`, writes and multiple statements are rejected. Original source aliases
and materialized output names are scope-checked. No SQL is sent to a production
database; DuckDB is in-memory with external access disabled. This is not a
proof of safe execution for hostile SQL.

Output rows are unordered bags; output column order is fixed by the SELECT.
NULL join keys do not match; WHERE keeps only SQL TRUE. COUNT ignores NULL
except `COUNT(*)`; `COUNT(DISTINCT)` also removes duplicate non-NULL values.
Empty grouped input yields an empty bag. An empty scalar aggregate yields 0
for COUNT and NULL for SUM/MIN/MAX. Equal retained bags plus **different**
nullable-aware scalar KPI values give a finite counterexample, not a statement
about actual deletion of raw data. A bounded negative requires complete
finite enumeration and DuckDB agreement, not a universal theorem. Deadline
checks are cooperative and there is no OS-hard process-memory cap.

Plan version 1 is recorded on new joined results. Older versionless joined
evidence remains readable; an unknown plan version is rejected. This does
not reinterpret the classic witness format. See the [architecture decision](architecture/relational-core.md)
and [replay contract](bounded-join.md) for correlated-error and integrity limits.
