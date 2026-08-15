# Strict-mode status must match exit code

**Decision:** When `validate --strict` escalates warnings to failures,
the JSON result's `status` is `failed` and `errors` is populated (each
entry prefixed `strict warning:`) before returning exit 1. Plain
`validate` keeps `status: passed` and surfaces warnings in
`summary.warnings` plus stderr with exit 0.

**Why:** The first `--strict` implementation returned exit 1 while the
JSON still read `status: passed, errors: []` (SIXTH_REVIEW P1-3). Any
consumer parsing the JSON — CI summarizers, other agents — would
conclude success from the body while the shell saw failure. Structured
output and process exit code are two views of one truth; when they
disagree, whichever the consumer reads becomes a lie. The `strict
warning:` prefix exists for the same reason: consumers must be able to
distinguish "strict mode rejected advisory findings" from "config is
invalid" without parsing prose.

**How to apply:** Any new flag that changes severity or exit behavior
must set the corresponding structured status in the same code path —
never rely on the caller to reconcile. If a mode can fail, its failure
mode is part of the output contract and gets a regression test asserting
both surfaces together (see
`eval_enforcement_test.py::StrictStatusConsistencyTests`).
