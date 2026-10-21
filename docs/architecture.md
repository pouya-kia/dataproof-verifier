# Phase 1 architecture

```text
typed spec + guarded SQL
          │
          ▼
       typed IR ─────► independent tiny-world enumerator (test baseline)
          │
          ▼
    Z3 pair-world search ──candidate──► DuckDB original-SQL validation
                                         │
                                         ▼
                              serialized JSON + replay.sql
                                         │
                                         ▼
                              independent DuckDB replay
```

`models.py` parses a bounded typed JSON/YAML contract and rejects malformed domains or constraints. `parser.py` inspects SQLGlot AST nodes and emits the small `ir.py` aggregate representation. `solver.py` encodes two finite row-slot worlds in Z3, exact group presence and aggregate values, equal view outputs, and unequal scalar metrics. A lexicographic objective picks a stable small witness within the bound. Z3 `UNSAT` is reported only as a finite bounded result.

`reference_enumerator.py` independently enumerates all tiny legal bags and evaluates admitted aggregates in Python. Tests compare its output with direct DuckDB SQL for every world in a tiny domain and compare its search verdict with Z3. `replay.py` creates two legal synthetic worlds in an in-memory DuckDB connection with external access disabled. It executes the original guarded SQL, compares full unordered view multisets and scalar metrics, and executes the generated standalone `replay.sql`. JSON world hash and recorded SQL outputs are checked during serialized replay. `cli.py` emits only accepted status codes and artifacts. `report.py` supplies stable JSON and software versions.

Trust boundaries: the parser rejects all source SQL outside the fragment before a solver or DuckDB run. Z3 output is only a candidate; DuckDB acceptance and serialized replay are mandatory. Input domains and row counts are capped. No production connection or external file access is used. A solver/replay disagreement becomes `INVALID_CANDIDATE` with no successful result.

Phase 2 keeps the same fragment. Replay snapshot names cannot collide with admitted source identifiers; fault-injected Z3 unknown/memory/exception and backend-error paths are inconclusive. The finite differential corpus now checks NULL/bag/key/aggregate combinations against direct DuckDB and a golden serialized replay, while the paired tiny benchmark records every repeat and its limitations.

The corrective Phase 2 artifact guard records hashes of DataProof-owned fixed-name outputs. A reused directory is preflighted before mutation: unknown, modified, symlinked, or non-file occupants of reserved names cause a fail-closed refusal. Only previously recorded unchanged files are cleared. On a non-successful run, candidate witness and replay outputs are removed before the ownership record is published. Result JSON writes use a staged atomic replacement. This is a serial-run directory protocol, not a concurrent-writer transaction or a way to infer the output path from malformed input.

Dependency rationale: SQLGlot supplies AST parsing, not proof; Z3 encodes finite search, not unbounded determinacy; DuckDB is the independent SQL execution engine. PyYAML uses safe loading. All runtime dependencies are pinned in `pyproject.toml` for the initial test matrix and should be updated only with the full gate and a recorded compatibility review. The research reference oracle is deliberately separate from the SMT encoding.
