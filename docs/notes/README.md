# Agent Notes

Dated, categorized decision records. Each note answers *why* a rule,
architecture choice, or process exists — the rule itself lives where it
is authoritative (AGENTS.md, policy docs, code). Notes are written in the
same PR as the change they explain; once merged they are immutable
history, not current authority.

## When to write one

Non-trivial changes add or update a note in the same PR. Mechanical or
purely local edits are exempt. If you find yourself explaining the same
"why" twice in review, it should have been a note.

## Layout

```
docs/notes/
  architecture/   structural decisions in src/agent_harness
  process/        how we work: review cadence, gates, commits
  testing/        test strategy and specific regression lessons
```

Filename: `YYYY-MM-DD-<short-slug>.md`.

## Format

Lead with the decision, then **Why:** (the constraint or incident that
forced it) and **How to apply:** (when this note should shape future
work). Cite post-mortems by number where relevant.

## Index

### architecture

- [2026-08-08 — Honest skipped semantics](architecture/2026-08-08-honest-skipped-semantics.md) — skipped exits 10 by default; --allow-skipped is the explicit opt-in
- [2026-08-08 — Entry distribution model](architecture/2026-08-08-entry-distribution-model.md) — no canonical path; ./src → HARNESS_HOME → import; --vendor for self-contained installs
- [2026-08-10 — Report persistence isolation](architecture/2026-08-10-report-persistence-isolation.md) — PID-scoped temp + os.replace; run_id in filenames

### process

- [2026-08-10 — Review-driven iteration](process/2026-08-10-review-driven-iteration.md) — numbered audit docs as the engine; quick-win sprint before strategy work
- [2026-08-10 — Local gates mirror CI lanes](process/2026-08-10-local-gates-mirror-ci.md) — local check names equal CI lane names

### testing

- [2026-08-08 — Runner protocol hard-fails](testing/2026-08-08-runner-protocol-hard-fails.md) — malformed/mismatched runner output blocks the stage, never degrades to skip
- [2026-08-10 — Strict-mode status must match exit code](testing/2026-08-10-strict-status-exit-parity.md) — --strict failures report status=failed
