# Test fixtures

Shared fixtures used by both unit and integration tests. Each fixture is a
small, deterministic data file (JSONL, JSON, TOML, plain text).

## Conventions

- All fixtures are safe to commit publicly — no real secrets, no real
  user data.
- Use the `*.example.jsonl` naming convention for dataset fixtures.
- Keep fixtures small. Tests should be fast.
- When a fixture represents a real-world shape (e.g. a production trace
  redacted into a regression sample), record its provenance in a comment
  at the top of the file.
