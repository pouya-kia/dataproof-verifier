# Contributing to the DataProof Alpha

Thanks for helping test the bounded production tool. Please report the original task, whether it is supported, the exact finite schema/domains/bounds, and the expected versus observed CLI status. Unsupported and incomplete tasks are valuable reports; do not rewrite them into easier tasks solely to make DataProof pass.

For reproducible bugs, use [ISSUE_TEMPLATE.md](ISSUE_TEMPLATE.md). For an independently motivated SQL task, use [ORIGINAL_SQL_PROBLEM_TEMPLATE.md](ORIGINAL_SQL_PROBLEM_TEMPLATE.md). Include a minimal **synthetic or authorized** specification, exact CLI command and exit code, Python/OS/package versions, and redacted artifacts only with permission. Never post credentials, production rows, personal information, confidential SQL, company infrastructure details, private paths, or unpublished research materials. For a vulnerability, use the private reporting route in [SECURITY.md](SECURITY.md); do not post details publicly.

For code changes, start with a failing regression, then run affected tests and the complete engineering gate: `ruff check .`, `ruff format --check .`, `mypy src`, `pytest -q`, and `git diff --check`. Explain any skipped check. Keep correctness claims bounded to the admitted fragment and require independent DuckDB replay for positive witnesses. Use Angular-style Conventional Commits. Any new SQL syntax needs parser, solver, replay, finite-oracle and adversarial-test coverage before it can be called supported.

This Alpha's examples are synthetic engineering demonstrations, not independent evidence of adoption or performance advantage. See [semantics](docs/semantics.md) and [limitations](docs/limitations.md).
