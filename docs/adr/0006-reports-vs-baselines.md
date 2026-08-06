# ADR 0006 — Generated reports gitignored, baselines checked in

Status: Accepted
Date: 2026-08-02

## Context

Every eval run produces a JSON report. If these are checked in, the
repository grows without bound and PRs are polluted with diff noise. If
none are checked in, there is no stable baseline to compare against.

## Decision

- `evals/reports/` is gitignored. Generated artifacts.
- `evals/baselines/` is checked in. A baseline is a frozen report
  promoted deliberately, by copying a report file into `baselines/` and
  opening a PR.

## Consequences

- **Pro:** PR diffs stay focused on code and dataset changes.
- **Pro:** Comparisons always reference a known-good baseline.
- **Con:** Baseline updates require manual action — this is
  intentional. Silent baseline drift would mask regressions.
