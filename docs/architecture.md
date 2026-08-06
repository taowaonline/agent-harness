# Architecture

## Goal

A vendor-neutral control plane that gives every project a stable command
surface for AI-assisted development and AI application lifecycle management.

The harness is **not** a model gateway, distributed trace backend, secret
manager, CI platform, or deployment automation. Those are integration points.

## Layers

```
+---------------------------------------------------------------+
| CLI  (./harness) — stable command semantics                   |
+---------------------------------------------------------------+
| Control plane  (src/ai_harness)                               |
|   config  ·  runner  ·  result  ·  policy  ·  evals  ·        |
|   redaction                                                   |
+---------------------------------------------------------------+
| Adapters  (profiles/)                                         |
|   language · workload · risk                                  |
+---------------------------------------------------------------+
| Project integration points                                    |
|   prompts  ·  datasets  ·  graders  ·  traces  ·  tools      |
+---------------------------------------------------------------+
```

## Stable command semantics

The CLI exposes stable verbs: `doctor`, `validate`, `list`, `run`, `eval`.
Stage names (`bootstrap`, `format`, `lint`, `typecheck`, `test-unit`,
`test-integration`, `eval-smoke`, `eval-full`, `security`) are also stable —
their **implementation** is a profile-supplied argv array, but the names and
result semantics are fixed.

## Result contract

Every execution returns a structured result:

```json
{
  "schema_version": 1,
  "run_id": "...",
  "status": "passed|failed|skipped|blocked",
  "started_at": "ISO-8601 UTC",
  "duration_ms": 123,
  "stages": [
    {"name": "...", "kind": "command|workflow|eval",
     "status": "...", "argv": ["..."], "exit_code": 0}
  ],
  "summary": {},
  "errors": []
}
```

Exit codes are coarse-grained:

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | validation failure (config invalid) |
| 2 | stage failure (subprocess returned non-zero) |
| 3 | policy gate failure (threshold, regression, security block) |
| 4 | internal error (unhandled exception) |

## Configuration model

`harness.toml` is the source of truth. It is loaded, validated against
`harness.schema.json`, then compiled into a runtime `Config` object.

- `[commands]` map a stable stage name to one or more argv arrays.
- `[workflows]` compose stages or other workflows.
- `[evals.smoke]` and `[evals.full]` configure datasets, limits, thresholds.
- `[security]` controls redaction, tool allowlist, and approval gates.

Cycle detection runs at load time. Unknown fields raise a validation error
(strict-by-default) unless explicitly permitted.

## Execution model

`runner.run_stage` invokes argv arrays via `subprocess.run(args=[...])` —
never `shell=True`. A stage fails fast: the first non-zero exit stops the
workflow with status `failed` unless the stage is explicitly optional.

Dry-run prints argv arrays (with secrets redacted) without spawning
subprocesses.

## Reproducibility

- Config has a `version` field; unknown majors are rejected.
- Prompts, models, tools, datasets, graders, and thresholds are versioned in
  the repo (see `prompts/`, `evals/`).
- Offline fixtures produce deterministic results; model API calls are never
  required by the unit or integration tests.

## Progressive adoption

`doctor`, `validate`, harness self-tests, and offline eval must work without
model keys. Missing optional stages report `skipped` with a reason — they
never silently claim `passed`.

## What is intentionally out of scope

See `HARNESS_IMPLEMENTATION_BRIEF.md` §17. The harness defines interfaces and
policies; it does not own commercial model routing, distributed tracing
storage, secret management, or production deployment.
