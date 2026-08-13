# Evaluation policy

This document defines the rules every project's AI evaluation must follow
when using this harness. The rules are intentionally conservative: it is
cheaper to over-evaluate than to ship a regression.

## Dataset partitioning

- Maintain at least three partitions: **train/dev** (for prompt
  iteration), **test** (for release gates), and **adversarial** (for
  safety probes).
- Never mix partitions. A sample used to tune a prompt must not appear in
  the test set used to gate a release.
- Production feedback samples are a fourth partition. They must be
  redacted, deduplicated, and reviewed before being added to any of the
  above.
- Each sample's `metadata.source` field records its provenance:
  `synthetic`, `golden`, or `production-feedback`.

## Repetitions and determinism

- Tasks with non-determinism (chat, agent traces) run with
  `repetitions >= 3`. Report mean, p50, and p95 — not a single run.
- Deterministic tasks (extraction at temperature 0) may run with
  `repetitions = 1`.
- Offline evals must produce identical reports when run twice against the
  same fixtures. If they do not, file a bug.

## Thresholds and regression gates

- Each `[evals.*]` declares `min_pass_rate` and (for full evals)
  `max_regression`.
- A category-level failure is a release blocker, even if the overall
  pass rate is acceptable. The harness reports per-tag breakdowns; do
  not let an aggregate score hide a high-risk category regression.
- Baselines are checked in under `evals/baselines/`. Updating a baseline
  is an explicit, reviewable operation — it must never happen silently
  inside a test run.

## Model judges

When a model-based grader is used:

- The judge prompt is versioned in `prompts/` — same rules as any other
  prompt.
- The judge model is pinned. Upgrades require a baseline comparison.
- A model must not grade its own outputs without calibration samples
  that a human has reviewed.
- For high-stakes evals, sample at least 5% of judge decisions for human
  review.

## Cost and budget

- `[evals.smoke].max_cost_usd` is small (default $2). PR runs that
  exceed it fail.
- `[evals.full].max_cost_usd` is larger (default $50) but still bounded.
- Online evals require an explicit `--online` flag and a configured
  secret. They never run on fork PRs.

## Adversarial samples

Every workload should carry at least a small set of adversarial probes
(prompt injection, tool abuse, data exfiltration attempts). They live in
`evals/datasets/adversarial.example.jsonl` and are tagged
`risk = "adversarial"`. A failure on any adversarial sample is a release
blocker.

## Production feedback loop

To turn a production failure into a regression sample:

1. Capture the trace (see `docs/observability.md`).
2. Redact all PII and secrets using `agent_harness.redaction.redact`.
3. Extract the input and the expected corrected output.
4. Add the case to the appropriate dataset with
   `metadata.source = "production-feedback"` and a date stamp.
5. Run `./agent_harness eval smoke --offline` to confirm the new sample is
   well-formed.
6. Open a PR with the new case — dataset changes are reviewed like code.
