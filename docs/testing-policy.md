# Testing policy

How this repo tests, tier by tier, and the rules that keep a green suite
meaningful. Adapted from practices observed in
[deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)
(`docs/testing.md`), with the rules re-scoped to a small pure-Python
control plane rather than a plugin monorepo.

## Tiers

| Tier | Command | Key required | Purpose |
|---|---|---|---|
| Unit | `agent_harness run test-unit` | no | Parser, runner, graders, redaction, policy logic |
| Integration | `agent_harness run test-unit` (same suite) | no | CLI end-to-end through `main()` in tempdirs |
| Offline eval | `agent_harness eval smoke/full --offline` | no | Dataset/grader/threshold protocol regression |
| Runner eval | `agent_harness eval <kind> --snapshot-mode=diff` | no (if runner is local) | Real subprocess SUT behavior vs recorded fixtures |
| Online eval | future provider integration | yes | Real model behavior; self-skips without key |

Tests live next to the area they exercise (`tests/unit/*_test.py`) and run
under stdlib `unittest` — the control plane deliberately has no third-party
runtime or test dependencies.

## Rules

### An uncovered line is usually dead code

Do not bolt a test onto an uncovered line to satisfy a coverage number.
An uncovered line in this codebase is more often dead state the gate is
correctly flagging for deletion. The canonical example here is
`_authRefreshToken` in iLanguage: written on login/refresh/logout, never
read — the lint warning was right and the field is gone.

### Mock only the expensive or non-deterministic boundary

Keep everything downstream of the boundary real. In our tests the mocked
boundaries are: the subprocess runner (mocked in grader tests via fixtures
and synthetic runners), the filesystem (tempdirs), and the clock where it
matters. The config loader, graders, redaction, and report writer always
run for real. A hand-rolled stand-in proves the bridge moves bytes, not
that the shipping grader behaves as asserted.

### Verify the world, not the self-report

An assertion should re-read the file, re-check the exit code, or re-run
the command — not keyword-probe a status string the code under test
produced. This applies doubly to eval graders: a `contains` grader is a
self-report check and lets a cheating SUT pass. When a case claims an
external effect (file created, artifact written, exit code), prefer an
external-effect grader that checks the world. The harness does not yet
ship external-effect graders; when it does, they gate harder than
keyword graders. See [evaluation-policy.md](evaluation-policy.md).

### A guard only guards if the regression actually fails it

When adding a regression test, introduce the regression, watch the new
test go red, then revert. The `HARNESS_SIXTH_REVIEW` P0-2 fix (malformed
runner output) is the worked example: the failing path was first
reproduced black-box (`stage_status=passed` with `errors=1`), the hard
failure was added, and the reproduction flipped to blocked.

### Test the real entry path

The CLI entry (`agent_harness`) is exercised black-box in
`tests/unit/project_root_test.py` and `skipped_semantics_test.py` by
copying `agent_harness + src/` to a tempdir and running `--version` with
`HARNESS_HOME` unset. That catches launcher regressions that importing
`agent_harness.cli` directly masks. The `--vendor` init path has the same
style of test (`sixth_review_regression_test.py`).

### Self-skip without a key is not a cost signal

Online/real-model tests (when they land) self-skip when their provider key
is absent, so keyless CI and keyless contributors stay green. Skipping is
a availability statement, never a budget statement. Do not convert a
self-skip into a silent pass: the result must report `skipped` with the
missing-key reason.

### Local runs match the surface; CI owns the matrix

Never default to the full suite locally. Match evidence to the surface:
focused unit file for behavior, offline eval for dataset/grader changes,
`run check` before push, `release-check` before release. CI owns
exhaustive coverage and the platform matrix. Repeating a passing check
buys nothing.

### Prove skip semantics stay honest

`skipped` must never silently become `passed`. This is locked by
`skipped_semantics_test.py` and the `--allow-skipped` opt-in with exit
code 10. Any change to skip propagation must add or update those tests in
the same change.

## Concurrency

Report persistence is PID-scoped-temp + `os.replace` (see
`schema_and_reports_test.py::test_concurrent_persist_does_not_corrupt`).
Still, avoid running multiple `agent_harness eval` processes against the
same project directory simultaneously; the harness does not lock the
dataset file.
