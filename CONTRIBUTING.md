# Contributing to the DataProof Alpha

DataProof v0.1.0a1 is an experimental, bounded SQL tool. The `dataproof-verifier` distribution is available from the [GitHub prerelease](https://github.com/pouya-kia/dataproof-verifier/releases/tag/v0.1.0a1), **not PyPI**. The import is `dataproof_verifier` and the CLI is `dataproof-verifier`. Python 3.11 or 3.12 is supported.

## Set up from the public repository

On Linux or macOS, make sure `python3` is Python 3.11 or 3.12 (`python3 --version`), then run:

```sh
git clone https://github.com/pouya-kia/dataproof-verifier.git
cd dataproof-verifier
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m mypy src
git diff --check
```

Try a supported synthetic NoUndo example without a production database:

```sh
.venv/bin/dataproof-verifier preflight no-undo examples/no_undo/daily_distinct.json
.venv/bin/dataproof-verifier check examples/no_undo/daily_distinct.json --output artifacts/no-undo
.venv/bin/dataproof-verifier replay artifacts/no-undo/witness.json
.venv/bin/dataproof-verifier explain artifacts/no-undo/witness.json
```

The output is a finite witness, not a universal theorem or a production-data claim. See [semantics](docs/semantics.md), [limitations](docs/limitations.md), and the [full demo](docs/demo.md). macOS may report an upstream Z3 wheel-platform metadata warning from `pip check` even when the CLI and tests work; include the exact warning if it affects your setup.

## Report a task or problem

Use the [bug report form](https://github.com/pouya-kia/dataproof-verifier/issues/new?template=bug_report.yml), [original SQL problem form](https://github.com/pouya-kia/dataproof-verifier/issues/new?template=original_sql_problem.yml), or [feature request form](https://github.com/pouya-kia/dataproof-verifier/issues/new?template=feature_request.yml). The root [issue template](ISSUE_TEMPLATE.md) and [original-task template](ORIGINAL_SQL_PROBLEM_TEMPLATE.md) remain available as readable references. Unsupported and incomplete original tasks are valuable; do not rewrite SQL solely to fit DataProof, invent an invariant, or claim eligibility without checking it.

Public issues are visible to everyone. Share only minimal synthetic or authorized redacted specifications and artifacts. Do not post credentials, tokens, production rows, personal information, confidential SQL, proprietary schemas without permission, internal infrastructure identifiers, private paths, or unpublished research. Report vulnerabilities through the private route in [SECURITY.md](SECURITY.md), never in a public issue.

## Propose a code change

Open a focused branch and Pull Request against `main`, explain the original problem and finite scope, and include a regression test for functional changes. Start with affected tests, then run the complete commands above and `.venv/bin/python -m pip check`. Report the known macOS Z3 metadata warning rather than hiding it; CI performs the dependency check on Ubuntu. The GitHub Actions workflow checks Python 3.11 and 3.12 on Ubuntu: import and installed CLI, Ruff lint/format, strict mypy, all public pytest tests, Wheel identity/entry point, and dependency consistency. Do not merge while a required check is failing or missing.

Use Angular-style Conventional Commits. New SQL features require coordinated parser, Z3 solver, DuckDB replay, finite-reference-oracle, NULL/bag, and adversarial regression coverage; a parser-only change does not make syntax supported. Keep the offline core and bounded claims intact. Feature requests are evaluated for usefulness and correctness, not promised implementation. This Alpha's synthetic examples are engineering demonstrations, not independent adoption or comparative-performance evidence.
