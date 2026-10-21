# Relational-core engineering gates — development source

The `0.1.0a4.dev0` source is not a tagged release. These are engineering
checks on researcher-authored finite inputs, not an independent-use study or
a new Paper 1/2/3 experiment. Exact PR/CI evidence and source revision must
be read from the repository; a prior run does not validate later edits.

| Slice | Finite reference and replay | Local gate at PR review | Residual limit |
| --- | --- | --- | --- |
| Version-1 plan over existing two-table joins | Tiny legal-world differential tests execute admitted **original SQL** in DuckDB; old joined CLI witnesses remain replayable | PR #13: 316 passed, one optional skip; Ruff/mypy, build and fresh Wheel CLI passed; Ubuntu 3.11/3.12 PR and post-merge jobs passed | Parser, schema and world generation are shared; one-table Z3 and other workflows unchanged |
| One grouped aggregate CTE/derived source and outer aggregate | New `test_relational_pipeline.py` compares every one of 18 legal worlds to original SQL; separate positive CLI check/replay/explain and paired 18-world complete negative; NULL/duplicate COUNT DISTINCT, empty scalar and inner WHERE checks | PR #14: 329 passed, one optional skip; Ruff/mypy, sdist/Wheel, fresh Python 3.11 installed CLI replay passed; Ubuntu 3.11/3.12 PR jobs passed | Positive search stopped after 14 worlds, not exhaustive over all pairs; finite negative exhausted 18 worlds; no hard OS resource cap |
| Authored full-contract v1 controls | Twelve pinned-input NoUndo questions; 222 legal-world evaluations in the complete differential loop, nine reference positives and three fully exhausted negatives; nine serialized CLI positives replayed | Focused manifest/task suite: 13 passed. Existing examples were known before suite construction; this is not a blind study | No independent developer tasks, no new Doppelgänger or Proof2Test contract, no general-SQL evidence |

The two paths agree on a validated positive only after original-SQL DuckDB
replay. For a complete negative, both finite evaluators must enumerate the
same declared legal-world set and agree; a deadline, backend exception,
tampering or semantic disagreement yields inconclusive/error handling, not a
proof. Each accepted query is a guarded SELECT in an isolated, in-memory
DuckDB connection with external access disabled. The AST allowlist rejects
multiple statements, writes, COPY/ATTACH, unsupported functions, arbitrary
CTE graphs and unknown output fields; it is not a demonstrated hostile-SQL
sandbox. Existing ownership markers and replay tamper tests remain in the
full regression suite. New joined evidence records plan version 1; old
versionless joined witnesses retain their compatibility path.

The restored private DataProof-100 baseline now supports a [separate
unchanged-ID reassessment](dataproof-100-architecture-postchange.md): all
100 IDs accounted for, 34 unchanged direct authored inputs checked on the
exact current Wheel, 28/28 preserved finite-oracle agreements and 20/20
positive independent DuckDB replays. The 50 public-origin records still
have no complete as-stated executable fixture: **0/50 independently solved**.
Other authored Proof2Test/injected reliability controls were not rerun in
this pass, and no authored control is an external developer task. Three-table
joins, scalar subqueries, windows, shared workflow adapters, general SQL and
publication-level scientific claims are not validated by these gates.
