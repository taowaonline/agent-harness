# ADR 0004 — Offline deterministic graders first

Status: Accepted
Date: 2026-08-02

## Context

If unit and integration tests depend on a model API, they become flaky,
slow, and expensive. They also cannot run in CI without secrets.

## Decision

Ship only deterministic graders in the harness core: exact, contains,
not_contains, regex, json_parse, json_field, tool_call, threshold.
Provide a `register_grader` plugin point for semantic similarity or
model-judge graders, but never require them for the base test suite.

Datasets include a fixture `output` field for offline runs. Dropping
the `output` field and attaching a real `ModelProvider` is the
production path.

## Consequences

- **Pro:** The whole CI runs without secrets.
- **Pro:** Test failures are reproducible.
- **Con:** Some quality dimensions (fluency, helpfulness) cannot be
  graded deterministically. Projects opt into model-judge graders
  explicitly and accept the calibration burden.
