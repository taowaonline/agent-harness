# Honest skipped semantics

**Decision:** `STATUS_SKIPPED` maps to exit code 10 by default. Exit 0
under skip requires the explicit `--allow-skipped` flag. Any workflow
containing a skipped child reports `skipped` at the top (with a
`partial: N passed, M skipped` reason when mixed), and dry-runs are
always `skipped`, never `passed`.

**Why:** Every prior review round (SECOND through FIFTH) reproduced the
same trap: a workflow whose stages were all skipped (tool missing,
`typecheck = []`, dry-run) reported top-level `passed` with exit 0 — a
green result that proved nothing ran. The integration test
`test_run_check_dry_run` even *asserted* the wrong behavior ("Dry-run
keeps top-level status as passed"), locking the bug in. Failures keep
priority over skips so a real break is never re-labelled.

**How to apply:** Never add a path that maps skip to success without an
explicit opt-in. When a stage legitimately skips (optional tool absent,
integration not configured), the surface must carry the reason — CI
scripts that accept skips pass `--allow-skipped` and the JSON still says
`skipped`. Any change to skip propagation updates
`tests/unit/skipped_semantics_test.py` and
`tests/integration/cli_test.py` in the same diff.
