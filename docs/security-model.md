# Security model

This document establishes the threat model, defense in depth, and the
security boundaries enforced by the harness.

## Threat model

| # | Threat | Surface | Mitigation |
|---|---|---|---|
| 1 | Prompt injection (direct) | User message | System prompt hardening; refusal graders in adversarial dataset |
| 2 | Indirect prompt injection | Retrieved documents, tool outputs | Tools outputs are data, not instructions; tool outputs flow through a separate channel from system prompt |
| 3 | Data exfiltration | Model output, tool args | `[security].tool_allowlist`; `require_approval_for = ["external_write", "network_egress"]`; output redaction |
| 4 | Cross-tenant access | Multi-tenant retrieval | Tenant id enforced in retrieval layer; agent cannot construct arbitrary tenant-scoped queries |
| 5 | Privileged tool abuse | Agent tool calls | Per-tool permission levels; high-risk writes gated by human approval |
| 6 | Arbitrary command execution | Shell tool | argv arrays only; no `shell=True`; tool args validated by JSON schema |
| 7 | Path traversal | File tool | Tools confined to a sandbox root; `..` segments rejected |
| 8 | SSRF | HTTP tool | Allowlist of permitted hosts; private IP ranges blocked |
| 9 | Secret leak in logs | Tracing, eval reports | `redact()` applied to logs, eval reports, error messages |
| 10 | Untrusted model output into downstream systems | Database, shell, HTML | Output validation against schema; HTML escaping at render; parameterized queries |
| 11 | Resource exhaustion / cost runaway | Long agent loops, large prompts | `[evals].max_cost_usd`, `timeout_seconds`, `sample_limit`, step-count threshold graders |
| 12 | High-risk write without approval | Production writes | `require_approval_for` covers deploy, delete, payment, external_write |
| 13 | Dependency vulnerability | Third-party packages | pip-audit / npm audit / cargo audit integration points in `security.yml` |
| 14 | Committed secret | Git history | `redaction.py` regex scan; `gitleaks` integration point in `security.yml` |

## Permission model

Permissions are *per-action-kind*, not a single `admin=true` flag. The
agent_harness recognizes:

| Kind | Default | What it covers |
|---|---|---|
| `read-only` | allowed | Retrieval, search, computation |
| `external_write` | gated | Any write that leaves the process boundary |
| `delete` | gated | Destructive actions |
| `payment` | gated | Anything that moves money |
| `deploy` | gated | Anything that ships to production |
| `network_egress` | gated | Outbound HTTP/WebSocket to non-allowlisted hosts |
| `privileged` | gated | OS-level privileged operations |

A tool's `permission` field (see `prompts/manifest.example.toml`) selects
its kind. The runtime consults `[security].require_approval_for` to
decide whether to block and surface for human approval.

## Adversarial samples

`evals/datasets/adversarial.example.jsonl` covers the most common
probes. Each case tags the threat it exercises:

- `prompt-injection` — direct and indirect
- `jailbreak` — role-play without rules, "DAN"-style
- `emotional-manipulation` — coercion
- `indirect-injection` — tool output that contains instructions
- `tool-safety` — destructive or out-of-scope tool calls
- `data-exfil` — attempts to leak data
- `ssrf` — requests to private or attacker-controlled hosts
- `path-traversal` — attempts to read arbitrary files

A failure on any adversarial sample is a release blocker.

## Redaction

`agent_harness.redaction` applies conservative secret-detection patterns:

- Generic `api_key=`, `token=`, `secret=`, `password=`, `authorization=`
- AWS access key ids and secret keys
- GitHub / GitLab PATs
- Slack tokens (`xox[baprs]-...`)
- JWTs
- Google API keys (`AIza...`)
- Stripe keys (`sk_live_...`, `pk_live_...`)
- Bearer tokens

Redaction runs:

- On every persisted eval report (`evals.reports.*.json`).
- On the dry-run argv preview.
- On error messages captured into a `RunResult`.
- On `safe_env_for_logging` for any env-var logging.

Redaction is *defense in depth*. It is not a substitute for not logging
secrets in the first place.

## What the harness does *not* do

- It does not run real secret scanners (gitleaks, trufflehog). It
  integrates with them — see `.github/workflows/security.yml`.
- It does not run dependency scanners (pip-audit, npm audit). It
  integrates with them.
- It does not store secrets. Configure secrets via your CI secret store
  and pass them as environment variables to your `ModelProvider`.

## Incident response

If a secret is committed:

1. Rotate the secret immediately. Assume it is compromised.
2. Do not just delete the file — the secret is in git history.
3. Use `git filter-repo` or a professional secret-removal service.
4. Add a regression case to `evals/datasets/adversarial.example.jsonl`
   that simulates the leak shape, so the redaction patterns catch it
   next time.
