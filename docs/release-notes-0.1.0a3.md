# DataProof 0.1.0a3 — untagged Alpha source candidate

This document describes a locally buildable candidate. It is **not** a
GitHub Release, Git tag or PyPI upload. The published `v0.1.0a1` tag, Wheel,
sdist and source history are unchanged; the earlier unpublished `0.1.0a2`
candidate is not overwritten.

Since that earlier candidate, the separate bounded two-table NoUndo path
admits finite ASCII STRING equality and grouping, limited CASE and integer
expressions, one or two direct equijoin keys, RIGHT/FULL null extension,
row-preserving projection-only CTE/derived sources, and UTC-naive timestamp
DAY/MONTH grouping. Each change has finite Python/original-DuckDB differential
tests, positive serialized replay, negative/unsupported regressions and
reviewable wave documentation. The one-table Z3, Doppelgänger and Proof2Test
SQL contracts did not expand.

The [exact joined contract](bounded-join.md) and [final coverage accounting](evaluation/sql-coverage-a3-candidate.md)
are required reading. The separate join backend still has two tables, two
rows per table, at most three columns/effective values per table and 500
analytical combined worlds. Its timeout is cooperative and it has no OS hard
memory limit. General CTE/subquery pipelines, three-table joins, timezone
conversions and ordered windows are not supported. No original public-origin
DataProof-100 task became fully eligible or solved (0/50). Synthetic examples
demonstrate finite behavior, not independent adoption or production readiness.
Paper 1, Paper 2 and Phase 6C prespecified primary practical gates remain
negative. No algorithmic novelty or general performance claim follows.

Before any separate owner-authorized release, verify the exact source commit,
privacy-screened source inventory, full Linux Python 3.11/3.12 CI, fresh
Wheel and sdist installation, CLI replay, artifact hashes, dependency and
license notices, and human approval. No tag, upload or release should be
created merely because this candidate builds.
