# AI Development Harness

A vendor-neutral, language-agnostic **control plane** for AI-assisted software
development and AI application lifecycle management.

The harness gives every project — regardless of target language, model vendor,
or AI framework — one stable entry point:

```
requirement / acceptance criteria
  -> agent fetches controlled context
  -> plan & small-step implementation
  -> format, lint, type check, tests
  -> AI smoke eval, full regression, adversarial eval
  -> PR gate & human review
  -> staged rollout with rollback
  -> production traces flow back as new regression samples
```

## Why this exists

Two workflows are usually treated as separate concerns:

1. **AI-assisted software development** — helping a coding Agent understand a
   project, plan changes, run checks, and submit reviewable diffs.
2. **AI application lifecycle** — versioning prompts, models, tools, datasets,
   evals, tracing, security gates, and release rollback.

This harness unifies them behind a single set of commands so a project that
*uses* AI can also be *developed with* AI without juggling two toolchains.

## Stable command surface

| Command | Meaning |
|---|---|
| `doctor` | Check harness, config, and toolchain availability |
| `validate` | Validate config, datasets, and policy files |
| `list` | List stages, workflows, and config sources |
| `run <stage-or-workflow>` | Run a stage or workflow |
| `run <stage-or-workflow> --dry-run` | Print what would run without executing |
| `run <stage-or-workflow> --json` | Emit stable machine-readable result |
| `eval <smoke\|full> --offline` | Run an offline deterministic eval |

Stage names map to language-specific tools (Ruff, ESLint, `tsc`, `go vet`,
Clippy, `dotnet format`, …) but the **names and result semantics are stable**.

See `docs/architecture.md` and `docs/development-workflow.md` for the full
mental model.

## Quick start

```bash
./harness doctor
./harness validate
./harness list
./harness run check --dry-run
./harness run check
./harness eval smoke --offline
```

The control plane is implemented in Python 3.11+ standard library only — no
runtime third-party dependencies. Tests run with the built-in `unittest`
module.

## What's inside

- `harness` — executable entry point (no need to remember a Python module path)
- `harness.toml` — this repository's own config
- `harness.schema.json` — machine-readable config contract
- `src/agent_harness/` — control plane implementation
- `tests/` — unit, integration, and fixture-driven tests
- `evals/` — datasets, graders, baselines, and generated reports
- `profiles/` — copy-and-override profiles for languages, workloads, risk levels
- `prompts/` — prompt manifest example
- `docs/` — architecture, security, observability, release, evaluation policy
- `examples/` — cross-language reference projects
- `.github/` — CI, eval, and security workflows plus templates

## Design principles

1. **Stable core, replaceable adapters.** The CLI contract never depends on a
   target language, model vendor, or AI framework.
2. **No surprise side effects.** External commands are argv arrays; no
   `shell=True`; high-risk writes require explicit human approval gates.
3. **Reproducible.** Prompts, tools, models, datasets, graders, and thresholds
   are all versioned. Offline fixtures produce stable results.
4. **Progressive adoption.** Without model keys, `doctor`, `validate`, harness
   self-tests, and offline eval still run. Missing optional stages report
   `skipped` with a reason — they never silently claim `passed`.

## Status

This is the initial reference implementation scaffold. See
`docs/adr/` for design decisions.
