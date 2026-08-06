# ADR 0001 — Control plane in Python 3.11+ standard library only

Status: Accepted
Date: 2026-08-02

## Context

The harness must support projects in Python, TypeScript, Go, Rust, JVM,
and .NET. Its own implementation language must not become a constraint on
the target project. The control plane also needs to be cheap to install
in CI: no compiling, no large dependency tree, no version conflicts with
the project's own dependencies.

## Decision

Implement the control plane CLI in Python 3.11+ standard library only.
Use `tomllib` (in stdlib since 3.11) for config parsing, `subprocess`
for argv execution, `unittest` for tests. No runtime third-party
dependencies.

## Consequences

- **Pro:** Single language to install in CI. `actions/setup-python` is
  enough.
- **Pro:** No version conflicts with the target project's own
  dependencies.
- **Con:** We give up some convenience — no `pydantic`, no `rich`,
  no `click`. Hand-rolled argparse and dataclasses are sufficient.
- **Con:** No `jsonschema` library; we maintain a hand-written
  validator that matches `harness.schema.json`. Tests cover the parity.

## Alternatives considered

- **Go binary.** Strong single-binary story, but cross-compiling for
  every target OS adds release complexity, and Go's TOML story is
  third-party.
- **Node CLI.** Pervasive in frontend projects but adds `node_modules`
  weight to every CI run.
- **Rust binary.** Excellent single-binary story, slow dev cycle.
