# Development workflow

This is the canonical workflow for a coding Agent (or human) working in a
project that has adopted this harness.

## 1. Understand the task

```bash
./harness explain check
./harness explain eval-smoke
./harness list
./harness doctor
```

Read `AGENTS.md`. Confirm the acceptance criteria in your own words.

## 2. Plan the change

For non-trivial changes, write a short plan as a checklist. Mark each
item as it lands.

## 3. Implement

- Modify only files in scope.
- Use small, reviewable commits.
- Never `shell=True`. Never hard-code secrets.

## 4. Local checks

```bash
./harness validate
./harness run check           # format, lint, typecheck, test-unit
./harness eval smoke --offline
```

If you changed AI behavior (prompt, model, tool, retrieval):

```bash
./harness eval full --offline
./harness baseline compare evals/baselines/latest.json evals/reports/<new>.json
```

## 5. Open a PR

Use `.github/pull_request_template.md`. Fill in every section. If a
section does not apply, say "no change" rather than leaving it blank.

## 6. Address review

- Respond to every comment.
- Do not bypass failing checks. If a check fails, fix the root cause or
  escalate.
- Do not enable `--no-verify` or equivalent bypasses.

## 7. After merge

- Watch the canary metrics for the relevant workload.
- If a gate breaches, follow `docs/release-policy.md` to roll back.

## Common pitfalls

- **Reporting `skipped` as `passed`.** The harness distinguishes them;
  your PR description should too.
- **Using an unknown command.** Run `./harness list` — names are stable.
- **Forgetting to update eval samples** when changing AI behavior.
- **Hard-coding a model name in code** instead of `prompts/manifest`.
