# Report persistence isolation

**Decision:** Eval reports persist as
`{name}-{timestamp}-{run_id[:8]}.json` via a PID-scoped temp file
(`.{pid}-{run_id[:8]}.tmp`) and `os.replace`. Baselines are checked-in
files promoted by explicit copy + PR; reports are gitignored.

**Why:** Two stacked incidents. First, second-precision timestamps let
same-second runs overwrite each other (SECOND_REVIEW P1.5) — run_id in
the filename fixed naming, and `os.replace` made the write atomic so an
interrupted process never leaves half a JSON. Second, the third quality
review (§11.3) observed transient unit failures when multiple harness
processes shared `evals/reports/`: the deterministic `.json.tmp` suffix
was the remaining collision point, so temp files became PID-scoped. The
10-thread concurrent-persist test locks the no-corruption guarantee.

**How to apply:** Any new artifact writer follows the same recipe:
unique-per-run final name, PID-scoped temp, `os.replace`. Baseline
updates stay manual-by-design — an auto-promoting baseline lets a
regression rewrite its own measuring stick (ADR 0006). When a report
format changes, bump or version the schema fields rather than mutating
silently, because baselines are compared across SHAs.
