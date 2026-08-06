# Release policy

The harness defines a release pipeline contract. It does **not** run
production deploys itself — your platform owns that. The pipeline is:

```
PR checks
  -> full eval
  -> staging / shadow
  -> human approval (standard / high-risk)
  -> canary
  -> health / quality / cost gate
  -> gradual rollout
  -> rollback if breached
```

## Stages

| Stage | Owner | Trigger | Gate |
|---|---|---|---|
| PR checks | Author | Every PR | `./harness run check` |
| Full eval | Release manager | `workflow_dispatch` or schedule | `./harness eval full` |
| Staging / shadow | Platform | Automatic after eval | SLO + quality gate |
| Human approval | Release manager | For `standard` and `high-risk` profiles | Explicit |
| Canary | Platform | After approval | Error rate / quality / cost |
| Gradual rollout | Platform | Canary healthy | Percentage-based |
| Rollback | On-call | Gate breach | Last stable version |

## Configuration requirements

Releases must support:

- **Environment protection.** Production is a protected environment with
  required reviewers.
- **Single-concurrency deploy per environment.** No two releases run in
  parallel against the same environment.
- **Version tagging.** Every release is tagged with a monotonic version
  and a git SHA. The harness records both in the eval report.
- **Rollback to the previous stable version.** The previous stable
  version is always known and quickly redeployable.

## Rolling back

A rollback is triggered when any of the following breach:

- Success rate SLI drops below threshold for >5 minutes.
- P95 latency exceeds budget for >5 minutes.
- Cost per request exceeds budget for >5 minutes.
- Quality proxy (eval smoke against live traffic samples) drops below
  threshold.
- Security block rate spikes (indicates abuse or model regression).
- A human operator declares rollback.

The rollback target is the previous stable version tag. The harness
records the version of every run in its structured result, so the
on-call can identify the last stable version by inspecting eval reports.

## Prompts, models, and tools

A prompt, model, or tool change is a release. It must:

- Be versioned (`prompts/manifest.example.toml`).
- Pass full eval with no regression beyond `max_regression`.
- Update or add eval samples that demonstrate the new behavior.
- Record the baseline diff in the PR description.

If a model upgrade fails the gate, the rollback is the previous model
snapshot — not a code rollback. Configure `[model]` to require an
explicit version bump; never auto-upgrade.
