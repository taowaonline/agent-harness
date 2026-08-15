# Runner protocol hard-fails

**Decision:** Every violation of the subprocess runner contract —
malformed JSON on a stdout line, wrong line count, missing or
non-string `case_id`, positional `case_id` mismatch, non-zero runner
exit, timeout — raises `_RunnerError` and fails the whole eval stage.
There is no soft path that converts a protocol error into a per-case
skip.

**Why:** The first implementation wrote malformed-JSON errors to
`result.errors` but still graded the case from a missing fixture,
producing `stage_status=passed, skipped=1` with an error parked in a
side channel (SIXTH_REVIEW P0-2, reproduced black-box). A runner
protocol violation means the transport is broken; grading a subset of
cases through a broken transport reports a number that looks like
evidence and is not. Positional validation (results must arrive in input
order with matching ids) makes duplicate/unknown ids unreachable — any
reordering surfaces as a mismatch on the first affected line — so the
explicit duplicate check that existed briefly was dead code and was
deleted rather than kept as decoration.

**How to apply:** New runner-side error classes hard-fail the same way
and carry the offending line/id in the message. If a future feature
genuinely needs per-case degradation (e.g. flaky-network retries), it
must be an explicit, configured behavior with its own result status —
never a silent fallback inside protocol parsing. Regression coverage
lives in `tests/unit/runner_protocol_test.py` and
`sixth_review_regression_test.py` (malformed / mismatch / missing /
line-count / non-zero exit paths).
