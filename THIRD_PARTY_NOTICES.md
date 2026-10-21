# Direct runtime dependencies

DataProof does not vendor these packages. Installation retrieves their distributions separately; this file records the direct pins and upstream license references, not legal approval of a particular binary artifact or its transitive contents.

| Package | Pinned version | Upstream license reference |
| --- | --- | --- |
| DuckDB | 1.5.6 | [DuckDB license](https://github.com/duckdb/duckdb/blob/main/LICENSE), MIT |
| SQLGlot | 29.0.1 | [SQLGlot license](https://github.com/tobymao/sqlglot/blob/main/LICENSE), MIT |
| Z3 Solver | 5.3.1.0 | [Z3 license](https://github.com/Z3Prover/z3/blob/master/LICENSE.txt), MIT |
| PyYAML | 6.0.3 | [PyYAML license](https://github.com/yaml/pyyaml/blob/main/LICENSE), MIT |

The selected macOS Z3 wheel has a documented platform-tag metadata mismatch: installation and CLI tests can work while `pip check` reports that the wheel is unsupported on that platform. The Z3 PyPI release also has upstream packaging/provenance caveats. Neither condition is silently fixed by altering an installed wheel or changing the pinned solver version. Before public distribution, the owner should review the exact dependency artifacts, their notices and provenance; this file is not a full transitive or legal audit.
