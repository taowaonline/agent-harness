#!/usr/bin/env python3
"""Fake subprocess runner for harness eval tests.

Reads one Case JSON per line from stdin, writes one Result JSON per line
to stdout. Implements a deterministic mapping that exercises both pass
and fail paths:

  - If the case's expected.contains list is non-empty AND any of the
    needles appears in the case's input.query, the runner outputs
    {"answer": <query itself>} so the contains grader passes.
  - Otherwise outputs {"answer": "i do not know"} so the grader fails.

This is intentionally simple — the point is to verify the JSONL Runner
protocol works end-to-end, not to be a real model.

Usage in harness.toml:
  [evals.smoke]
  dataset = "..."
  runner = ["python3", "tests/fixtures/fake_provider.py"]

Non-zero exit on `--fail` argv for testing runner-error paths.
"""

import json
import sys


def main() -> int:
    if "--fail" in sys.argv:
        sys.stderr.write("fake_provider: simulated runner failure\n")
        return 2
    if "--slow" in sys.argv:
        # Sleep past any reasonable per-case timeout to test timeout path.
        import time
        time.sleep(60)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError:
            # Mirror a malformed input — write back an error result.
            sys.stdout.write(
                json.dumps({"case_id": "?", "output": {}, "error": "bad input"})
                + "\n"
            )
            sys.stdout.flush()
            continue
        case_id = case.get("id", "")
        query = (case.get("input") or {}).get("query", "")
        expected = case.get("expected") or {}
        contains = expected.get("contains") or []
        if contains and any(n in query for n in contains):
            answer = query
        else:
            answer = "i do not know"
        sys.stdout.write(
            json.dumps(
                {
                    "case_id": case_id,
                    "output": {"answer": answer},
                    "trace": {"runner": "fake_provider"},
                }
            )
            + "\n"
        )
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
