# AGENTS.md — Agent contract for this repository

This file is the binding contract for any coding Agent (human or model-assisted)
working in this repository. Read it before making changes.

## Before you change anything

1. Read `README.md`, `docs/architecture.md`, and the test that covers the area
   you are touching.
2. Read the relevant source file in `src/agent_harness/` end-to-end before
   editing.
3. Confirm the acceptance criteria of the task in your own words. For complex
   tasks, post a short plan first.

## While you work

- Only modify files within the task scope. Preserve user changes that are
  out of scope.
- Prefer small, reviewable diffs. Do not refactor unrelated code.
- Do not invent commands. Discover them through `./agent-harness list` or the docs.
- Use argv arrays for any subprocess invocation. Never `shell=True`.
- Do not read, print, or commit secrets. If you accidentally see one, redact
  it and notify the user.
- Never write a secret-shaped literal — including documented example keys,
  and including inside docs that describe incidents. Construct at runtime
  or describe the shape ([post-mortem 0001](docs/postmortem/0001-github-secret-scanning-blocked-pushes.md)).

## Code discipline

- **Local runs match the surface; CI owns the matrix.** Never default to
  the full suite or repeat a passing check for commit or push. Focused
  unit file for behavior, offline eval for dataset/grader changes,
  `run check` before push, `release-check` before release
  ([testing policy](docs/testing-policy.md)).
- **Misconfiguration fails loud** at load when self-contained, otherwise
  at the earliest resolvable point; never silently skip a missing
  referent. A `skipped` result must carry its reason
  ([why](docs/notes/architecture/2026-08-08-honest-skipped-semantics.md)).
- **Trust types at same-process boundaries.** Do not add runtime
  validation, fallbacks, or hostile-input tests solely for values the
  type system already guarantees within this codebase; validate at real
  boundaries — config files, datasets, subprocess output, wire formats.
- **An empty `catch` names what it swallows** and why nothing else can
  reach it; keep the `try` to one statement.
- **Do not comment on facts obvious from code.** Comments state
  contracts and non-obvious context, not reasoning transcripts.
- **Tests describe behavior, not correctness.** When behavior changes,
  change its tests in the same diff and say why in the PR.
- TODO markers by urgency: `FIXME` (broken now) / `TODO` (known gap) /
  `XXX` (hazard).
- Files end with exactly one trailing newline; `git diff --cached
  --check` gates it.

## Before you declare done

Run the harness checks that match the change's risk:

```bash
./agent-harness validate
./agent-harness run check           # format, lint, typecheck, unit tests
./agent-harness eval smoke --offline
```

For changes affecting prompts, models, tools, or eval behavior, also run:

```bash
./agent-harness eval full --offline
./agent-harness baseline compare <old-report> <new-report>
```

For a new regression test, prove the guard: introduce the regression,
watch the new test go red, revert
([testing policy](docs/testing-policy.md#a-guard-only-guards-if-the-regression-actually-fails-it)).

## Hard rules

- Never bypass a failing test, quality threshold, human approval, or release
  gate. If a check fails, fix the root cause.
- Never describe `skipped` as `passed`. Always report the reason a stage was
  skipped.
- If a step cannot be completed, report the root cause and remaining work —
  do not paper over it.
- Do not commit cache, virtualenv, generated reports, or local secret files.
  See `.gitignore`.

## Decision records

Non-trivial changes add or update a note under `docs/notes/` in the same
PR; only mechanical/local edits are exempt. Notes are dated, categorized,
and immutable once merged — current authority lives in code and this
file, with notes carrying the rationale. See
[docs/notes/README.md](docs/notes/README.md). Post-mortems live under
[docs/postmortem/](docs/postmortem/README.md) and are cited by number
from policy docs.

## Acceptance criteria are mandatory

Every change must state its acceptance criteria and demonstrate evidence in
the PR description. See `.github/pull_request_template.md`.
