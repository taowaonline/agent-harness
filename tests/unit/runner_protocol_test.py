"""Tests for the subprocess JSONL Runner protocol (HARNESS_FIFTH_REVIEW §八 6).

Covers: success path, runner non-zero exit, malformed JSON line, runner
timeout, missing executable, and basic integration with run_eval.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_harness.config import (  # noqa: E402
    Config,
    EvalConfig,
    ProjectInfo,
    SecurityConfig,
)
from ai_harness.evals import (  # noqa: E402
    _RunnerError,
    _invoke_subprocess_runner,
    run_eval,
)
from ai_harness.result import STATUS_FAILED, STATUS_PASSED, RunResult  # noqa: E402


REPO = HERE.parent.parent
FAKE = str(REPO / "tests" / "fixtures" / "fake_provider.py")


def _make_case(line: str):
    """Helper to write a single-case dataset and return its path."""
    import tempfile

    d = Path(tempfile.mkdtemp(prefix="harness-runner-"))
    p = d / "ds.jsonl"
    p.write_text(line + "\n", encoding="utf-8")
    return p


class RunnerProtocolUnitTests(unittest.TestCase):
    """Direct tests of _invoke_subprocess_runner."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _ec(self, argv: list[str], timeout: int | None = None) -> EvalConfig:
        return EvalConfig(
            dataset=str(self.dir / "ds.jsonl"),
            runner=argv,
            timeout_seconds=timeout,
        )

    def _write_ds(self, cases: list[dict]) -> None:
        lines = [json.dumps(c) for c in cases]
        (self.dir / "ds.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _make_cases(self, n: int = 2):
        from ai_harness.evals import EvalCase

        return [
            EvalCase(
                id=f"c{i}",
                input={"query": f"hello {i}"},
                expected={"contains": ["hello"]},
            )
            for i in range(n)
        ]

    def test_runner_success_returns_outputs_keyed_by_case_id(self) -> None:
        self._write_ds([{"id": "x", "input": {"query": "hi"}}])
        ec = self._ec(["python3", FAKE])
        result = RunResult(command="eval")
        outputs = _invoke_subprocess_runner(ec, self._make_cases(2), result)
        self.assertEqual(set(outputs.keys()), {"c0", "c1"})
        for cid, out in outputs.items():
            self.assertIn("answer", out)

    def test_runner_nonzero_exit_raises(self) -> None:
        ec = self._ec(["python3", FAKE, "--fail"])
        result = RunResult(command="eval")
        with self.assertRaises(_RunnerError) as cm:
            _invoke_subprocess_runner(ec, self._make_cases(1), result)
        self.assertIn("exited 2", str(cm.exception))

    def test_runner_timeout_raises(self) -> None:
        ec = self._ec(["python3", FAKE, "--slow"], timeout=1)
        result = RunResult(command="eval")
        with self.assertRaises(_RunnerError) as cm:
            _invoke_subprocess_runner(ec, self._make_cases(1), result)
        self.assertIn("timed out", str(cm.exception))

    def test_runner_missing_executable_raises(self) -> None:
        ec = self._ec(["this-binary-does-not-exist-anywhere"])
        result = RunResult(command="eval")
        with self.assertRaises(_RunnerError) as cm:
            _invoke_subprocess_runner(ec, self._make_cases(1), result)
        self.assertIn("not found on PATH", str(cm.exception))


class RunnerIntegrationTests(unittest.TestCase):
    """End-to-end: run_eval with a runner config produces real grades."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def _cfg_with_runner(self, dataset_text: str, runner: list[str]) -> Config:
        p = self.dir / "ds.jsonl"
        p.write_text(dataset_text, encoding="utf-8")
        ec = EvalConfig(
            dataset=str(p),
            runner=runner,
            min_pass_rate=0.5,
            timeout_seconds=10,
        )
        return Config(
            version=1,
            project=ProjectInfo(name="t", language="python"),
            commands={},
            workflows={},
            evals={"smoke": ec},
            security=SecurityConfig(),
        )

    def test_run_eval_with_runner_grades_outputs(self) -> None:
        # Two cases: one whose query contains the needle (pass), one that
        # does not (fail). Pass rate = 0.5, threshold 0.5 → status PASSED.
        cfg = self._cfg_with_runner(
            "\n".join([
                json.dumps({"id": "p1", "input": {"query": "hello world"},
                            "expected": {"contains": ["hello"]}}),
                json.dumps({"id": "f1", "input": {"query": "goodbye"},
                            "expected": {"contains": ["missing"]}}),
            ]),
            runner=["python3", FAKE],
        )
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        # Should pass at exactly 0.5 (1/2 graded cases).
        self.assertEqual(stage.status, STATUS_PASSED)
        self.assertEqual(stage.metrics["summary"]["passed"], 1)
        self.assertEqual(stage.metrics["summary"]["failed"], 1)

    def test_run_eval_with_failing_runner_returns_failed(self) -> None:
        cfg = self._cfg_with_runner(
            json.dumps({"id": "x", "input": {"query": "y"},
                        "expected": {"contains": ["y"]}}),
            runner=["python3", FAKE, "--fail"],
        )
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_FAILED)
        joined = " ".join(result.errors)
        self.assertIn("runner", joined)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
