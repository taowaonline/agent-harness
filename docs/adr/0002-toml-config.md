# ADR 0002 — TOML for project config

Status: Accepted
Date: 2026-08-02

## Context

We need a config format that supports nested tables, arrays of arrays
(for argv arrays), inline comments, and is human-friendly. Candidates:
TOML, YAML, JSON.

## Decision

Use TOML, parsed by the stdlib `tomllib` module. Configuration is
`harness.toml` at the project root.

## Consequences

- **Pro:** `tomllib` is in stdlib since 3.11 — no new dependency.
- **Pro:** Native support for arrays-of-arrays (perfect for argv).
- **Pro:** Comments are first-class, useful for documenting overrides.
- **Con:** Some users prefer YAML. We do not support YAML for the
  control plane; users may convert if needed.

A companion `harness.schema.json` documents the contract. We do not
enforce schema parity through a JSON Schema library — we hand-write
validators that match. The schema file is for tooling and humans.
