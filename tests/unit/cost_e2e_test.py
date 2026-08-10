"""End-to-end test for cost enforcement via TOML config + CLI.

This is the integration-level companion to cost_enforcement_test.py (which
tests the Python API directly). It verifies the full path:
  harness.toml → load_config → run_eval → CLI exit code

Addresses HARNESS_CURRENT_CHANGE_QUALITY_EVALUATION §11.4:
"补充 cost_usd 端到端超预算阻断测试"
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_harness.cli import main  # noqa: E402

REPO = HERE.parent.parent
FAKE = str(REPO / "tests" / "fixtures" / "fake_provider.py")


class CostEnforcementE2ETests(unittest.TestCase):
    """Write a harness.toml with enforce_max_cost + runner, invoke CLI."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def _write_cost_runner(self, cost_per_case: float) -> str:
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

    def _write_config(self, runner: str, *, enforce: bool, max_cost: float) -> None:
        (self.dir / "harness.toml").write_text(
            textwrap.dedent(f"""
                version = 1
                [project]
                name = "cost-e2e"
                language = "python"
                [evals.smoke]
                dataset = "ds.jsonl"
                runner = ["python3", "{runner}"]
                enforce_max_cost = {str(enforce).lower()}
                max_cost_usd = {max_cost}
                min_pass_rate = 0.0
                timeout_seconds = 10
            """),
            encoding="utf-8",
        )
        (self.dir / "ds.jsonl").write_text(
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

    def _run_cli(self, *argv: str) -> tuple[int, str, str]:
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(list(argv))
        return rc, out_buf.getvalue(), err_buf.getvalue()

    def test_enforce_blocks_overage_via_cli(self) -> None:
        """$1.00/case × 1 case = $1.00 > $0.10 budget → exit 2 (stage failed)."""
        runner = self._write_cost_runner(1.00)
        self._write_config(runner, enforce=True, max_cost=0.10)
        rc, out, err = self._run_cli("eval", "smoke", "--offline", "--json")
        data = json.loads(out)
        self.assertEqual(data["status"], "failed")
        self.assertIn("cost gate", " ".join(data["errors"]))
        # Exit code: STATUS_FAILED → EXIT_STAGE_FAILED = 2
        self.assertEqual(rc, 2)

    def test_enforce_under_budget_via_cli(self) -> None:
        """$0.01/case × 1 case = $0.01 < $1.00 budget → exit 0."""
        runner = self._write_cost_runner(0.01)
        self._write_config(runner, enforce=True, max_cost=1.00)
        rc, out, err = self._run_cli("eval", "smoke", "--offline", "--json")
        data = json.loads(out)
        self.assertEqual(data["status"], "passed")
        self.assertEqual(rc, 0)
        summary = data["stages"][0]["metrics"]["summary"]
        self.assertIn("cost_usd", summary)

    def test_advisory_does_not_block_via_cli(self) -> None:
        """$100/case, enforce=false → passed even though massively over budget."""
        runner = self._write_cost_runner(100.0)
        self._write_config(runner, enforce=False, max_cost=0.01)
        rc, out, err = self._run_cli("eval", "smoke", "--offline", "--json")
        data = json.loads(out)
        self.assertEqual(data["status"], "passed")
        self.assertEqual(rc, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
