# AGENTS.md — Agent contract for this repository

This file is the binding contract for any coding Agent (human or model-assisted)
working in this repository. Read it before making changes.

## Before you change anything

1. Read `README.md`, `docs/architecture.md`, and the test that covers the area
   you are touching.
2. Read the relevant source file in `src/ai_harness/` end-to-end before
   editing.
3. Confirm the acceptance criteria of the task in your own words. For complex
   tasks, post a short plan first.

## While you work

- Only modify files within the task scope. Preserve user changes that are
  out of scope.
- Prefer small, reviewable diffs. Do not refactor unrelated code.
- Do not invent commands. Discover them through `./harness list` or the docs.
- Use argv arrays for any subprocess invocation. Never `shell=True`.
- Do not read, print, or commit secrets. If you accidentally see one, redact
  it and notify the user.

## Before you declare done

Run the harness checks that match the change's risk:

```bash
./harness validate
./harness run check           # format, lint, typecheck, unit tests
./harness eval smoke --offline
```

For changes affecting prompts, models, tools, or eval behavior, also run:

```bash
./harness eval full --offline
./harness baseline compare <old-report> <new-report>
```

## Hard rules

- Never bypass a failing test, quality threshold, human approval, or release
  gate. If a check fails, fix the root cause.
- Never describe `skipped` as `passed`. Always report the reason a stage was
  skipped.
- If a step cannot be completed, report the root cause and remaining work —
  do not paper over it.
- Do not commit cache, virtualenv, generated reports, or local secret files.
  See `.gitignore`.

## Acceptance criteria are mandatory

Every change must state its acceptance criteria and demonstrate evidence in
the PR description. See `.github/pull_request_template.md`.
