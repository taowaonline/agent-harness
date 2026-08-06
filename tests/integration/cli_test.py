"""End-to-end CLI integration tests.

Exercises the CLI through the same entry point a user would, but with a
temporary working directory so we do not depend on this repository's own
harness.toml.
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
from ai_harness.policy import (  # noqa: E402
    EXIT_STAGE_FAILED,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
)


HARNESS_TOML = """
version = 1

[project]
name = "demo"
language = "python"
workload = "rag"
risk = "standard"

[commands]
lint = [["python3", "-m", "py_compile", "src/ai_harness/__init__.py"]]
test-unit = [["python3", "-c", "print('ok')"]]
typecheck = []

[workflows]
check = ["lint", "typecheck", "test-unit"]

[evals.smoke]
dataset = "smoke.jsonl"
min_pass_rate = 0.9
"""


SMOKE_DATASET = """{"id":"s1","input":{"query":"hello","output":{"answer":"hello world"}},"expected":{"contains":["hello"]},"tags":["smoke"]}
{"id":"s2","input":{"query":"bye","output":{"answer":"goodbye world"}},"expected":{"contains":["bye"]},"tags":["smoke"]}
"""


class CLIIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        (self.dir / "harness.toml").write_text(HARNESS_TOML, encoding="utf-8")
        (self.dir / "smoke.jsonl").write_text(SMOKE_DATASET, encoding="utf-8")
        # Subdir for py_compile to validate against.
        sub = self.dir / "src" / "ai_harness"
        sub.mkdir(parents=True)
        (sub / "__init__.py").write_text("'''demo package'''\n", encoding="utf-8")
        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(list(argv))
        return rc, out_buf.getvalue(), err_buf.getvalue()

    def test_doctor(self) -> None:
        rc, out, err = self._run("doctor", "--json")
        self.assertEqual(rc, EXIT_SUCCESS, err + out)
        data = json.loads(out)
        self.assertEqual(data["command"], "doctor")
        self.assertTrue(data["summary"]["config_loadable"])

    def test_validate(self) -> None:
        rc, out, err = self._run("validate", "--json")
        self.assertEqual(rc, EXIT_SUCCESS, err + out)
        data = json.loads(out)
        self.assertIn("validated", data["summary"])

    def test_list(self) -> None:
        rc, out, err = self._run("list", "--json")
        self.assertEqual(rc, EXIT_SUCCESS, err + out)
        data = json.loads(out)
        self.assertEqual(
            data["summary"]["stages"],
            ["lint", "test-unit", "typecheck"],
        )

    def test_run_check_dry_run(self) -> None:
        rc, out, err = self._run("run", "check", "--dry-run", "--json")
        self.assertEqual(rc, EXIT_SUCCESS, err + out)
        data = json.loads(out)
        # Dry-run keeps top-level status as passed (skipped is not failure).
        self.assertEqual(data["status"], "passed")
        # The workflow stage is reported as skipped with reason dry-run.
        wf = data["stages"][0]
        self.assertEqual(wf["status"], "skipped")
        self.assertEqual(wf["reason"], "dry-run")

    def test_run_check_real(self) -> None:
        rc, out, err = self._run("run", "check", "--json")
        self.assertEqual(rc, EXIT_SUCCESS, err + out)
        data = json.loads(out)
        self.assertEqual(data["status"], "passed")
        wf = data["stages"][0]
        statuses = [c["status"] for c in wf["children"]]
        # typecheck should be skipped; lint and test-unit should pass.
        self.assertIn("skipped", statuses)
        self.assertIn("passed", statuses)

    def test_run_failure_returns_nonzero(self) -> None:
        (self.dir / "harness.toml").write_text(
            HARNESS_TOML.replace(
                "print('ok')",
                "import sys; sys.exit(1)",
            ),
            encoding="utf-8",
        )
        rc, out, err = self._run("run", "test-unit", "--json")
        self.assertEqual(rc, EXIT_STAGE_FAILED, out)

    def test_eval_smoke_offline(self) -> None:
        rc, out, err = self._run("eval", "smoke", "--offline", "--json")
        self.assertEqual(rc, EXIT_SUCCESS, err + out)
        data = json.loads(out)
        self.assertEqual(data["status"], "passed")
        eval_stage = data["stages"][0]
        self.assertEqual(eval_stage["kind"], "eval")
        self.assertGreaterEqual(
            eval_stage["metrics"]["summary"]["pass_rate"], 0.9
        )

    def test_baseline_compare(self) -> None:
        # Generate two reports via offline eval, then compare them.
        self._run("eval", "smoke", "--offline", "--json")
        reports = sorted((self.dir / "evals" / "reports").glob("*.json"))
        self.assertEqual(len(reports), 1)
        rc, out, err = self._run(
            "baseline", "compare", str(reports[0]), str(reports[0]), "--json"
        )
        self.assertEqual(rc, EXIT_SUCCESS, err + out)
        data = json.loads(out)
        self.assertEqual(data["summary"]["comparison"]["verdict"], "unchanged")

    def test_validate_rejects_unknown_field(self) -> None:
        (self.dir / "harness.toml").write_text(
            HARNESS_TOML + "[unknown_section]\nx = 1\n",
            encoding="utf-8",
        )
        rc, out, err = self._run("validate", "--json")
        self.assertEqual(rc, EXIT_VALIDATION)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
