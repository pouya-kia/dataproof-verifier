# Reproducible DataProof issue

Do not include credentials, production rows, private paths, personally identifiable information, confidential SQL, company infrastructure details, or proprietary SQL without permission. Prefer a minimal synthetic reproduction and redact artifacts before sharing. For a potential vulnerability, read [SECURITY.md](SECURITY.md) and do not put exploit details in a public issue.

- DataProof version or Wheel SHA-256:
- Python version, operating system, architecture:
- CLI command (with private paths replaced):
- Exit code and status/reason code:
- Expected behavior and why:
- Actual behavior:
- Minimal synthetic schema, finite domains, constraints, and SQL:
- Declared row/domain bounds:
- Independent DuckDB replay result, if a witness exists:
- Redacted witness/replay artifact hashes, if safe to share:
- Was the original task supported, unsupported, or incompletely specified?
- Can an ordinary SQL query or test already resolve this task more simply?

Please preserve failures and unsupported cases. A bounded no-witness result is not a proof about unrestricted data.
