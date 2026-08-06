# Observability

The harness defines a vendor-neutral Trace/Event schema. The internal
core does not bind to any commercial tracing platform — it just emits
the schema, and your platform maps it.

## Trace / event schema

Every execution produces records with these fields:

| Field | Type | Notes |
|---|---|---|
| `trace_id` | string | Top-level correlation id; shared across spans in one user turn |
| `span_id` | string | Unique within a trace |
| `parent_span_id` | string? | Optional; forms a tree |
| `run_id` | string | Harness RunResult.run_id — ties to a CLI invocation |
| `ts` | ISO-8601 UTC | Event time |
| `env` | enum | `local`, `ci`, `staging`, `production` |
| `git_sha` | string | Captured automatically by the harness |
| `app_version` | string | Application-supplied; semver or equivalent |
| `prompt_id` | string? | From `prompts/manifest` |
| `prompt_version` | string? | Same manifest |
| `model_provider` | string? | `anthropic`, `openai`, etc. |
| `model_name` | string? | Specific model name |
| `model_snapshot` | string? | Vendor snapshot/date if pinned |
| `temperature` | float? | Inference parameter |
| `reasoning_effort` | string? | If applicable |
| `max_output_tokens` | int? | |
| `input_tokens` | int? | Billed usage |
| `output_tokens` | int? | |
| `cache_read_tokens` | int? | |
| `cache_write_tokens` | int? | |
| `latency_ms` | int | Wall time of the span |
| `retries` | int | |
| `estimated_cost_usd` | float? | Project-supplied rate card |
| `tool_name` | string? | When the span is a tool call |
| `tool_status` | enum? | `ok`, `error`, `blocked`, `timeout` |
| `tool_permission` | enum? | `read-only`, `write`, `privileged` |
| `eval_result` | enum? | `passed`, `failed`, `error`, `skipped` |
| `error_kind` | string? | Stable error category |
| `user_feedback` | enum? | `up`, `down`, `report` |

## Defaults

- The raw input and raw output are **never** logged by default. A
  project may opt in per-field after a privacy review.
- Sampling, redaction, and retention are configurable.
- Retention is bounded — production traces are deleted after a fixed
  window, not stored forever.

## OpenTelemetry mapping

The fields above map cleanly to OTel semantic conventions:

- `trace_id`, `span_id`, `parent_span_id` -> OTel trace context.
- `model_provider`, `model_name`, `input_tokens`, `output_tokens`,
  `estimated_cost_usd` -> `gen_ai.*` conventions.
- `tool_name`, `tool_status` -> `gen_ai.tool.*`.
- `git_sha`, `app_version`, `env` -> resource attributes.

Use the OTel SDK's attribute redaction processor to enforce the
"never log raw input/output" rule at the SDK boundary.

## Minimum SLI

Every workload reports at least:

| SLI | Definition |
|---|---|
| Success rate | `passed / (passed + failed)` over a window |
| P50 latency | Median end-to-end latency |
| P95 latency | Tail latency |
| Cost per request | Estimated cost / request count |
| Quality proxy | Smoke eval pass rate against live-traffic samples |
| Tool failure rate | `failed_tool_calls / total_tool_calls` |
| Security block rate | `blocked / total` for security-gated actions |

A breach on any SLI is a candidate rollback signal — see
`docs/release-policy.md`.
