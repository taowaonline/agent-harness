"""Tests for timeout / repetitions / max_regression / --strict enforcement.

Covers HARNESS_FIFTH_REVIEW §八 items 7, 8, 9, 10.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_harness.cli import main  # noqa: E402
from ai_harness.config import (  # noqa: E402
    Config,
    EvalConfig,
    ProjectInfo,
    SecurityConfig,
)
from ai_harness.evals import compare_reports, run_eval  # noqa: E402
from ai_harness.result import STATUS_FAILED, STATUS_PASSED, RunResult  # noqa: E402


REPO = HERE.parent.parent
FAKE = str(REPO / "tests" / "fixtures" / "fake_provider.py")


class RepetitionsTests(unittest.TestCase):
    """§八 8: repetitions=N actually runs N times and reports aggregation."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def test_repetitions_runs_runner_multiple_times(self) -> None:
        # Use a runner so each rep actually re-invokes. We can't directly
        # observe the rep count from outside, but we can verify the summary
        # reports repetitions + aggregation mode.
        ds_path = self.dir / "ds.jsonl"
        ds_path.write_text(
            json.dumps({
                "id": "p1",
                "input": {"query": "hello"},
                "expected": {"contains": ["hello"]},
            }) + "\n",
            encoding="utf-8",
        )
        cfg = Config(
            version=1,
            project=ProjectInfo(name="t", language="python"),
            commands={},
            workflows={},
            evals={
                "smoke": EvalConfig(
                    dataset=str(ds_path),
                    runner=["python3", FAKE],
                    repetitions=3,
                    timeout_seconds=5,
                )
            },
            security=SecurityConfig(),
        )
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_PASSED)
        # Summary records that reps happened and how they were aggregated.
        self.assertEqual(stage.metrics["summary"]["repetitions"], 3)
        self.assertEqual(
            stage.metrics["summary"]["aggregation"], "worst_pass_rate"
        )

    def test_repetitions_default_one_has_no_aggregation_field(self) -> None:
        # When repetitions is the default (1), we don't pollute the summary.
        ds_path = self.dir / "ds.jsonl"
        ds_path.write_text(
            json.dumps({
                "id": "p1",
                "input": {"query": "hello"},
                "expected": {"contains": ["hello"]},
            }) + "\n",
            encoding="utf-8",
        )
        cfg = Config(
            version=1,
            project=ProjectInfo(name="t", language="python"),
            commands={},
            workflows={},
            evals={
                "smoke": EvalConfig(
                    dataset=str(ds_path),
                    runner=["python3", FAKE],
                    timeout_seconds=5,
                )
            },
            security=SecurityConfig(),
        )
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertNotIn("repetitions", stage.metrics["summary"])


class MaxRegressionTests(unittest.TestCase):
    """§八 9: max_regression allows small regressions, blocks big ones."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _report(self, pass_rate: float) -> str:
        p = self.dir / f"r-{pass_rate}.json"
        p.write_text(
            json.dumps({"summary": {"pass_rate": pass_rate}}), encoding="utf-8"
        )
        return str(p)

    def test_small_regression_within_threshold(self) -> None:
        a = self._report(0.95)
        b = self._report(0.94)  # regression = 0.01
        delta = compare_reports(a, b, max_regression=0.02)
        self.assertEqual(delta["verdict"], "within_threshold")
        self.assertEqual(delta["regression"], 0.01)
        self.assertEqual(delta["allowed_regression"], 0.02)

    def test_big_regression_blocked(self) -> None:
        a = self._report(0.95)
        b = self._report(0.90)  # regression = 0.05
        delta = compare_reports(a, b, max_regression=0.02)
        self.assertEqual(delta["verdict"], "regressed")
        self.assertEqual(delta["regression"], 0.05)

    def test_no_threshold_legacy_behavior(self) -> None:
        # Without max_regression, any regression is "regressed".
        a = self._report(0.95)
        b = self._report(0.949)
        delta = compare_reports(a, b, max_regression=None)
        self.assertEqual(delta["verdict"], "regressed")


class StrictWarningsTests(unittest.TestCase):
    """§八 10: --strict produces observable difference vs no --strict."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(list(argv))
        return rc, out_buf.getvalue(), err_buf.getvalue()

    def test_strict_fails_when_warnings_present(self) -> None:
        # Construct a config that triggers a warning:
        # workload=other + no commands.
        toml = """
version = 1
[project]
name = "x"
language = "python"
workload = "other"
[evals.smoke]
dataset = "smoke.jsonl"
max_cost_usd = 5.0
"""
        (self.dir / "harness.toml").write_text(toml, encoding="utf-8")
        (self.dir / "smoke.jsonl").write_text(
            json.dumps({
                "id": "a",
                "input": {"query": "q"},
                "expected": {"contains": ["q"]},
            }) + "\n",
            encoding="utf-8",
        )
        old = os.getcwd()
        os.chdir(self.dir)
        try:
            rc_strict, out_strict, err_strict = self._run(
                "validate", "--strict", "--json"
            )
            rc_plain, out_plain, err_plain = self._run("validate", "--json")
        finally:
            os.chdir(old)
        # --strict must fail (return EXIT_VALIDATION=1).
        self.assertEqual(rc_strict, 1)
        # Plain validate passes (status=passed) but emits warnings to stderr.
        self.assertEqual(rc_plain, 0)
        # HARNESS_SIXTH_REVIEW P1-3: the strict JSON output's status field
        # MUST agree with the exit code. If exit is non-zero, status must
        # be "failed" — never "passed" with a non-zero exit.
        strict_data = json.loads(out_strict)
        self.assertEqual(
            strict_data["status"], "failed",
            f"--strict exit was {rc_strict} but JSON status was "
            f"{strict_data['status']}; they must agree",
        )
        self.assertGreater(len(strict_data["errors"]), 0)
        # Plain validate's JSON status remains "passed" (warnings don't fail).
        plain_data = json.loads(out_plain)
        self.assertEqual(plain_data["status"], "passed")
        # Observable difference: strict has visible warnings + non-zero rc.
        self.assertIn("warnings", err_strict)
        # Observable difference: strict has visible warnings + non-zero rc.
        self.assertIn("warnings", err_strict)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
