# ADR 0003 — Stable stage names, profile-supplied argv

Status: Accepted
Date: 2026-08-02

## Context

A target project may use Ruff, Black, ESLint, Prettier, golangci-lint,
Clippy, Spotless, or `dotnet format`. We do not want to hard-code any of
these in the harness core, but downstream tools (CI, IDE plugins, other
Agents) need stable verbs to invoke.

## Decision

Define a fixed set of stage names: `bootstrap`, `format`, `lint`,
`typecheck`, `test-unit`, `test-integration`, `eval-smoke`, `eval-full`,
`security`. Each name maps to one or more argv arrays supplied by the
project's `harness.toml`. Three built-in stages (`eval-smoke`,
`eval-full`, `security`) have harness-provided defaults that the project
may override.

## Consequences

- **Pro:** A coding Agent or CI workflow can call `./agent-harness run check`
  without knowing the target language.
- **Pro:** Profile snippets under `profiles/languages/` are
  copy-and-paste; no forking of the core.
- **Con:** Stage names are a public contract — renaming one is a
  breaking change. Document in an ADR before doing so.

Workflows compose stages by name. Cycles are detected at config load.
