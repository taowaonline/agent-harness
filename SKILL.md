---
name: agent_harness
description: >-
  Vendor-neutral control plane for AI-assisted development and AI application
  lifecycle. Use when the user wants to set up or audit local CI/CD for an AI
  project, validate a harness.toml, run offline deterministic evals, audit
  security posture (secret redaction, tool allowlist, approval gates), compare
  eval baselines, or discover the stable command surface (doctor / validate /
  list / run / eval). Stable stage names map to language-specific tools via
  profiles; the harness itself never depends on a target language, model
  vendor, or AI framework.
---

# agent_harness

A coding Agent uses this skill when the project has adopted the harness
(detect `./harness` and `harness.toml` at the repo root). The Agent invokes
the CLI directly; it does not reinvent command chains.

Skill root (this folder) layout:

- `harness` — executable entry point
- `harness.toml` — this repo's own config (also the reference example)
- `src/agent_harness/` — control plane (Python 3.11+ stdlib only)
- `profiles/{languages,workloads,risk}/` — copy-and-override snippets
- `examples/<lang>-<workload>/harness.toml` — four cross-language references
- `evals/datasets/*.example.jsonl` — offline datasets with fixture outputs
- `docs/` — architecture, security-model, observability, release-policy, ADRs

## When to use

Invoke `./harness` when the user asks to:

- Set up local CI for an AI / agent / RAG / chat / extraction project.
- Run `doctor`, `validate`, `list`, `run`, or `eval` for a repo that has
  a `harness.toml`.
- Run offline AI evals without model keys.
- Audit secret redaction, tool allowlist, or approval gates.
- Compare two eval reports or diff against a checked-in baseline.
- Understand which stable stage names map to which tools.

## Do not

- Guess command names. Run `./agent_harness list` first; stage names are stable
  but their argv are profile-supplied.
- Use `shell=True` or string-concat commands when extending the harness —
  argv arrays only.
- Treat `skipped` as `passed`. Always surface the skip reason.
- Run online model evals unless the user explicitly asks. Offline is the
  default.
- Modify `evals/baselines/` inside an eval run. Baseline updates are an
  explicit, reviewable operation.
- Bypass failing quality gates, approval gates, or release gates.

## Stable command surface

| Command | Meaning |
|---|---|
| `./agent_harness --help` | Show stable commands |
| `./agent_harness doctor` | Check harness, config, datasets, declared toolchain |
| `./agent_harness validate` | Validate harness.toml + datasets + workflow refs |
| `./agent_harness list` | List stages, workflows, evals, security policy |
| `./agent_harness run <name>` | Run a stage or workflow |
| `./agent_harness run <name> --dry-run` | Print argv order without executing |
| `./agent_harness run <name> --json` | Stable machine-readable result |
| `./agent_harness eval smoke --offline` | Fast PR-level eval on fixtures |
| `./agent_harness eval full --offline` | Full regression eval on fixtures |
| `./agent_harness run security` | Built-in: redaction probe + policy + secret scan |
| `./agent_harness baseline compare <a> <b>` | Diff two reports |

Stable stage names: `bootstrap`, `format`, `lint`, `typecheck`,
`test-unit`, `test-integration`, `eval-smoke`, `eval-full`, `security`.
Built-in: `eval-smoke`, `eval-full`, `security` (can be overridden via
`[commands]`). Names and result semantics are stable; argv are
profile-supplied.

Exit codes:

- `0` success
- `1` validation failure (config invalid)
- `2` stage failure (subprocess returned non-zero)
- `3` policy gate failure (threshold / regression / security block)
- `4` internal error

## Agent checklist

1. If the project's toolchain looks uncertain, run `./agent_harness doctor`
   first; report missing optional tools but do not fail the run on them.
2. Before proposing a change, run `./agent_harness validate` to ensure config
   and datasets are well-formed.
3. To discover what a project actually runs, use `./agent_harness run <stage>
   --dry-run`; do not guess from `harness.toml` alone (workflows can
   nest).
4. After changes that touch AI behavior (prompts, models, tools,
   retrieval), run `./agent_harness eval smoke --offline` at minimum; for
   release-candidate changes, run `./agent_harness run release-check`.
5. If a stage reports `skipped`, surface the reason to the user; do not
   rephrase as success.
6. If the user asks for online evals, confirm secret availability before
   running; never log or persist secrets.
7. Compare release candidates against `evals/baselines/latest.json`
   using `./agent_harness baseline compare`.

## Profiles (do not auto-install)

`profiles/languages/{python,typescript,go,rust,jvm,dotnet}.toml`,
`profiles/workloads/{chat,rag,agent,extraction}.toml`,
`profiles/risk/{prototype,standard,high-risk}.toml`.

Copy a snippet into the project's `harness.toml`; never auto-install the
underlying tools (Ruff, ESLint, golangci-lint, Clippy, etc.). Their
absence should surface as `skipped` with a reason, not as a failure.

## Defaults

| Behavior | Default |
|---|---|
| Online eval | off (offline only by default) |
| Baseline overwrite | off (explicit manual operation) |
| `shell=True` | never |
| Redaction of inputs / outputs / argv | on |
| Tool allowlist | deny-by-default |
| Required approval for writes/deletes/payment/deploy | on |

## References

- Architecture: [docs/architecture.md](docs/architecture.md)
- Security model: [docs/security-model.md](docs/security-model.md)
- Evaluation policy: [docs/evaluation-policy.md](docs/evaluation-policy.md)
- Release policy: [docs/release-policy.md](docs/release-policy.md)
- Observability: [docs/observability.md](docs/observability.md)
- Development workflow: [docs/development-workflow.md](docs/development-workflow.md)
- ADRs: [docs/adr/](docs/adr/)
