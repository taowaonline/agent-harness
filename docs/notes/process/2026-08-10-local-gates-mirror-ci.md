# Local gates mirror CI lanes

**Decision:** The workflow names a developer runs locally are exactly the
CI lane names: `check` locally is what CI's harness job runs,
`release-check` maps to the release lane. CI never invents a gate the
developer cannot run with the same name, and local gate output is the
unit of evidence pasted into PRs.

**Why:** Observed in deepseek-harness's `run-gates.ts`, where local
`check:all` is by construction the `ci-primary` lane, so "works on my
machine" and "CI is red" name the same command. Our earlier drift — CI
invoked `validate --strict` while local muscle memory said `validate` —
produced a gate that looked stricter than it was (SIXTH_REVIEW P1-1
lineage). Same-name gates make that class of drift visible in review,
because a workflow yml that runs anything not in `agent-harness list`
is immediately suspect.

**How to apply:** New CI lanes are added by first adding the named
workflow to `harness.toml` (or documenting the built-in), then pointing
the yml step at that name — never by inlining a bespoke command chain in
the yml. If a check must be CI-only (cost, secrets), it still gets a
name and a `list` entry with the constraint documented, so the mirror is
broken explicitly rather than silently.
