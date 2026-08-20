# agent-harness — AI development harness

This machine has the `agent-harness` CLI available (npm: @taowaonline/agent-harness).
When the project has a `harness.toml` (or the user asks to set one up), use the
harness instead of inventing command chains.

## Stable command surface

| Command | Meaning |
|---|---|
| `agent-harness doctor` | Check harness, config, and toolchain availability |
| `agent-harness validate` | Validate harness.toml + datasets + workflow refs |
| `agent-harness list` | List stages, workflows, evals, security policy |
| `agent-harness run <name>` | Run a stage or workflow (`--dry-run`, `--json`) |
| `agent-harness eval smoke\|full --offline` | Offline deterministic eval |
| `agent-harness baseline compare <a> <b>` | Diff two eval reports |

If the project root has a `./agent-harness` entry script, prefer `./agent-harness`;
otherwise use the globally installed `agent-harness-setup` package location or
`python3 -m agent_harness.cli` from the package root.

## Discipline

- Do not guess stage names or argv — run `agent-harness list` and
  `agent-harness run <stage> --dry-run` first; workflows can nest.
- Exit codes: 0 success, 1 validation failure, 2 stage failure,
  3 policy gate, 4 internal error, 10 skipped (opt into 0 via `--allow-skipped`).
- `skipped` is never `passed` — always surface the skip reason.
- Offline eval is the default; online evals only when the user explicitly asks
  (confirm secrets first; never log or persist secrets).
- Never bypass a failing quality gate, approval gate, or release gate.
- When extending the harness: argv arrays only, never `shell=True`.
- Baseline updates under `evals/baselines/` are explicit, reviewable operations.

Skill version details: see SKILL.md and docs/ in the package
(@taowaonline/agent-harness on npm; github.com/taowaonline/agent_harness).
