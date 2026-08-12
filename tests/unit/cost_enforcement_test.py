"""Tests for [evals.*].enforce_max_cost (R2 from CURRENT_CHANGE_QUALITY_EVALUATION)."""

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

from agent_harness.config import (  # noqa: E402
    Config,
    EvalConfig,
    ProjectInfo,
    SecurityConfig,
)
from agent_harness.evals import run_eval  # noqa: E402
from agent_harness.result import STATUS_FAILED, STATUS_PASSED, RunResult  # noqa: E402

REPO = HERE.parent.parent
FAKE = str(REPO / "tests" / "fixtures" / "fake_provider.py")


class CostEnforcementTests(unittest.TestCase):
    """R2: enforce_max_cost=true blocks on overage; default is advisory."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def _write_cost_runner(self, cost_per_case: float) -> str:
        """Write a runner that emits a fixed cost_usd per case."""
        script = self.dir / "cost_runner.py"
        script.write_text(
            f"""import sys, json
for line in sys.stdin:
    case = json.loads(line)
    sys.stdout.write(json.dumps({{
        "case_id": case["id"],
        "output": {{"answer": case["input"].get("query", "")}},
        "cost_usd": {cost_per_case},
    }}) + "\\n")
""",
            encoding="utf-8",
        )
        script.chmod(0o755)
        return str(script)

    def _make_cfg(
        self,
        runner: str,
        *,
        enforce: bool,
        max_cost: float,
        min_pass: float = 0.5,
    ) -> Config:
        ds = self.dir / "ds.jsonl"
        ds.write_text(
            json.dumps(
                {
                    "id": "a",
                    "input": {"query": "hello"},
                    "expected": {"contains": ["hello"]},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return Config(
            version=1,
            project=ProjectInfo(name="t", language="python"),
            commands={},
            workflows={},
            evals={
                "smoke": EvalConfig(
                    dataset=str(ds),
                    runner=["python3", runner],
                    enforce_max_cost=enforce,
                    max_cost_usd=max_cost,
                    min_pass_rate=min_pass,
                    timeout_seconds=10,
                )
            },
            security=SecurityConfig(),
        )

    def test_enforce_blocks_on_overage(self) -> None:
        # $0.50/case × 1 case = $0.50 total; budget $0.10 → over.
        runner = self._write_cost_runner(0.50)
        cfg = self._make_cfg(runner, enforce=True, max_cost=0.10, min_pass=0.0)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_FAILED)
        joined = " ".join(result.errors)
        self.assertIn("cost gate", joined)
        self.assertIn("exceeds budget", joined)
        self.assertIn("0.5", joined)

    def test_enforce_passes_under_budget(self) -> None:
        # $0.01/case × 1 case = $0.01; budget $1.00 → under.
        runner = self._write_cost_runner(0.01)
        cfg = self._make_cfg(runner, enforce=True, max_cost=1.0, min_pass=0.5)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_PASSED)
        self.assertIn("cost_usd", stage.metrics["summary"])

    def test_advisory_default_does_not_block_on_overage(self) -> None:
        runner = self._write_cost_runner(100.0)
        cfg = self._make_cfg(runner, enforce=False, max_cost=0.01, min_pass=0.5)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        # Even $100 case doesn't block when advisory (default).
        self.assertEqual(stage.status, STATUS_PASSED)
        self.assertEqual(stage.metrics["summary"]["cost_usd"], 100.0)

    def test_no_cost_field_no_gate(self) -> None:
        # Runner doesn't emit cost_usd → enforce_max_cost is a no-op
        # even if true. No crash, no false gate.
        ds = self.dir / "ds.jsonl"
        ds.write_text(
            json.dumps(
                {
                    "id": "a",
                    "input": {"query": "hello"},
                    "expected": {"contains": ["hello"]},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        cfg = Config(
            version=1,
            project=ProjectInfo(name="t", language="python"),
            commands={},
            workflows={},
            evals={
                "smoke": EvalConfig(
                    dataset=str(ds),
                    runner=["python3", FAKE],
                    enforce_max_cost=True,
                    max_cost_usd=0.01,
                    min_pass_rate=0.5,
                    timeout_seconds=10,
                )
            },
            security=SecurityConfig(),
        )
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_PASSED)
        self.assertNotIn("worst_cost_usd", stage.metrics["summary"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
