# Post-mortem 0001: GitHub secret scanning blocked three consecutive pushes

Status: resolved

## Executive summary

While publishing this repo, GitHub's push-protection secret scanning
rejected the same push three times in a row. Each fix uncovered another
copy of a Stripe-documented example test key in a different file class:
first in Python source, then in a Markdown audit doc quoting the first
incident, then in the regression test written to cover the fix. The root
pattern: documenting or testing redaction with real-shaped literals.

## Impact

No secret ever leaked (every match was a documented example key). The
cost was three blocked pushes and two history rewrites (`git reset --soft`
squashes) to keep the literals out of any pushed commit — once a literal
lands in a pushed commit, removing it from HEAD is not enough.

## Timeline

1. Push 1 rejected: Stripe's documented example test key (prefix
   `sk_test_`, 24+ alphanumeric chars — the literal is deliberately not
   reproduced here; see rule 1 below) in
   `src/agent_harness/security.py`'s redaction probe and
   `tests/unit/security_test.py`'s fixture.
2. Fix: construct at runtime — `"sk_" + "test_" + "a" * 28` — so no
   literal secret shape appears in source. Squashed and pushed.
3. Push 2 rejected: the same literal now inside
   `HARNESS_EVALUATION_AND_IMPROVEMENTS.md`, which *documented incident 1
   by quoting the offending string*.
4. Fix: describe the shape instead of quoting it ("prefix `sk_test_` plus
   24 alphanumeric characters").
5. Push 3 rejected: the literal inside the *new regression test* that
   verified redaction still catches real-shaped keys.
6. Fix: the test constructs its key at runtime too. Squashed, pushed
   clean.

## Root cause

Treating "a string that looks like a secret" as safe because it is a
publicly documented example. Push protection matches shape, not
provenance — correctly, because shape is what leaks.

Secondary cause: each fix was verified with `grep sk_test_ <one file>`
instead of the whole tree, so the next copy was always a surprise.

## What the gates missed

Nothing at push time — GitHub caught it. Everything before push: local
lint and tests are shape-agnostic; the harness's own `security` stage
exempts test files and the redaction module itself (where these literals
legitimately live), so it never fired.

## Fix and the rule it produced

Rules:

1. **Never write a secret-shaped literal**, including documented example
   keys and including inside docs that describe incidents. Construct at
   runtime (`"sk_" + "test_" + "a" * 28`) or describe the shape.
2. Before pushing a repo that touches secret handling, run the
   shape-level grep across the *entire* tree:
   `git ls-files | xargs grep -lE "(sk_(live|test)_[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{30,}|AKIA[A-Z0-9]{16})"`.
3. Once a literal is in a pushed commit, history rewrite is the only
   clean removal — prefer never pushing it.
