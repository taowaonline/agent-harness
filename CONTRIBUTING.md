# Contributing

Thanks for helping improve the harness. Read `AGENTS.md` first — it is the
binding contract for any contributor (human or model-assisted).

## Definition of Done

A change is done when **all** of these hold:

1. Acceptance criteria are met and demonstrable.
2. Relevant documentation and ADR entries are updated.
3. Format, lint, type check, and applicable tests pass.
4. AI behavior changes are covered by a new or updated eval sample.
5. No unexplained quality, cost, or latency regression.
6. No secret was leaked and no tool permission was widened.
7. Observability is sufficient to diagnose failures in production.
8. Rollout and rollback path is documented in the PR.

If you cannot satisfy one of these, say so explicitly in the PR rather
than approximating completion.

## Workflow

1. Open or claim an issue. Link it from the PR description.
2. Branch from `main`. Keep diffs small and reviewable.
3. Run `./agent_harness validate` and `./agent_harness run check` locally.
4. Open a PR using `.github/pull_request_template.md`.
5. Address review comments inline. Do not force-push history that
   reviewers are actively reading unless asked.
6. Required CI checks must be green (or explicitly waived) before merge.

## Branch protection and required checks

Recommended branch protection for `main`:

- Require pull request before merge.
- Require status checks to pass before merging:
  - `harness checks` (from `ci.yml`)
  - `secret scanning` (from `security.yml`)
- Require branches to be up to date before merging.
- Dismiss stale approvals when new commits are pushed.
- Limit force-pushes and deletions.

Path-filtered workflows that result in a required check never reporting
success/failure are forbidden — every PR must produce a terminal status
for every required check.

## Communication norms

- Prefer written, asynchronous updates over real-time pings.
- Distinguish facts (test results, eval reports) from opinions.
- Disagree constructively; propose alternatives, not vetoes.
