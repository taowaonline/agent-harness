# Evals

The harness ships with a small, deterministic, offline eval system. Three
datasets are provided as references — copy and override them in your own
project.

## Datasets

| File | Purpose | Default trigger |
|---|---|---|
| `datasets/smoke.example.jsonl` | PR-level fast feedback | `eval smoke --offline`, workflow `eval-smoke` |
| `datasets/regression.example.jsonl` | Full regression before release | `eval full --offline`, workflow `eval-full` |
| `datasets/adversarial.example.jsonl` | Safety and tool-abuse probes | `eval full --offline` or manual |

`*.example.jsonl` files include a fixture `output` so the offline runner
produces a deterministic result. In production, drop the `output` field and
attach a real `ModelProvider` (see `src/agent_harness/evals.py`).

## Record schema

```json
{
  "id": "stable-unique-id",
  "input": {
    "query": "...",
    "output": {"answer": "..."}    // fixture only; omitted in production
  },
  "expected": {
    "contains": ["..."],
    "not_contains": ["..."],
    "regex": "...",
    "graders": [
      {"kind": "tool_call", "tool": "cancel_order", "args": {"order_id": "1234"}},
      {"kind": "json_field", "field": "name", "equals": "Ada"}
    ]
  },
  "tags": ["smoke", "rag", "zh-CN"],
  "metadata": {
    "source": "synthetic | golden | production-feedback",
    "risk": "normal | adversarial"
  }
}
```

`id` must be stable and unique. `metadata.source` distinguishes hand-curated
golden samples from synthetic data and from production feedback (which must
be redacted before it lands here — see `docs/observability.md`).

## Graders

The harness ships with deterministic graders. See `src/agent_harness/evals.py`
for the registry:

| Kind | Use |
|---|---|
| `exact` | Exact string match |
| `contains` / `not_contains` | Substring presence |
| `regex` | Regex match |
| `json_parse` | Output must be valid JSON |
| `json_field` | Specific JSON field equals expected value |
| `tool_call` | Tool called with expected name (and optionally args) |
| `threshold` | Numeric metric (latency, tokens, cost) below limit |

To register a custom grader (e.g. semantic similarity, model judge), call
`agent_harness.evals.register_grader(name, fn)` from your project. The base
unit and integration tests never depend on a model API.

## Snapshot modes (replay / record / diff)

Eval runs in one of three snapshot modes (`--snapshot-mode`, adapted from
dsh's record/replay/refresh state machine):

| Mode | What it does | Writes dataset? | Typical use |
|---|---|---|---|
| `replay` (default; `--offline` is an alias) | Grade against the fixture `output` recorded in the dataset | no | Keyless CI protocol gate |
| `record` | Run the configured `[evals.*].runner`, write its outputs back into the dataset as fixtures, then grade | **yes** (atomic rewrite) | After intentionally changing behavior; a human reviews the dataset diff |
| `diff` | Run the runner and compare its outputs against the recorded fixtures per case | no | "Did behavior change?" gate in CI or pre-commit |

Rules:

- `record` and `diff` require a configured `runner`; they fail loudly without one.
- `diff` fails the stage on **any** mismatch, including a missing fixture. The
  failure message names each case and shows fixture-vs-actual, truncated.
- The intended loop: `diff` goes red after a behavior change → you review why →
  `record` refreshes the fixtures → the dataset diff goes through normal PR
  review. Never auto-promote on a red `diff` — that is how regressions rewrite
  their own measuring stick (see [ADR 0006](../docs/adr/0006-reports-vs-baselines.md)).

## Reports

Reports are written to `evals/reports/` (gitignored — they are generated
artifacts, not source of truth). Each report records the harness version,
git SHA, dataset path, summary metrics, threshold config, and per-case
results.

## Baselines

A baseline is a checked-in report under `evals/baselines/`. Compare two
reports with:

```bash
./agent_harness baseline compare evals/baselines/old.json evals/reports/new.json
```

A regression (negative pass-rate delta) is surfaced as a non-zero exit code.

## Online evals

Online evals are *not* run by default. To enable them:

1. Configure `[evals.smoke]` / `[evals.full]` with cost, sample, and timeout
   limits in `harness.toml`.
2. Implement a `ModelProvider` callable.
3. Run via your own integration; never check a real API key into the repo.

See `docs/evaluation-policy.md` for the rules that govern model judges,
repetitions, and sampling.
