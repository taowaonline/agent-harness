"""Regression tests for skipped-status semantics (HARNESS_FIFTH_REVIEW §八 1-5).

These lock down the contract that SKIPPED must not silently become PASSED,
and that dry-run / pure-skipped / partial-skipped workflows report an
honest top-level status. The exit-code mapping is exercised via the CLI
in tests/integration/.
"""

from __future__ import annotations

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
    ProjectInfo,
    SecurityConfig,
)
from ai_harness.result import (  # noqa: E402
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    RunResult,
)
from ai_harness.runner import RunRequest, run_target  # noqa: E402


def _cfg(commands=None, workflows=None) -> Config:
    return Config(
        version=1,
        project=ProjectInfo(name="t", language="python"),
        commands=commands or {},
        workflows=workflows or {},
        evals={},
        security=SecurityConfig(),
    )


class SkippedSemanticsTests(unittest.TestCase):
    """§八 items 1, 2, 3: pure-skipped, partial-skipped, dry-run."""

    def test_pure_skipped_workflow_top_level_not_passed(self) -> None:
        # All children skipped (missing executables on optional stages).
        cfg = _cfg(
            commands={
                "typecheck": [["this-binary-does-not-exist"]],
            },
            workflows={"check": ["typecheck"]},
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="check"), result)
        self.assertEqual(result.status, STATUS_SKIPPED)
        self.assertNotEqual(result.status, STATUS_PASSED)

    def test_partial_skipped_workflow_top_level_skipped(self) -> None:
        # Mix of PASSED and SKIPPED. Top must be SKIPPED, not PASSED.
        cfg = _cfg(
            commands={
                "lint": [["python3", "-c", "print('ok')"]],
                "typecheck": [["this-binary-does-not-exist"]],
            },
            workflows={"check": ["lint", "typecheck"]},
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="check"), result)
        self.assertEqual(result.status, STATUS_SKIPPED)
        wf = result.stages[0]
        self.assertEqual(wf.status, STATUS_SKIPPED)
        # Reason must mention the partial mix.
        self.assertIn("partial", wf.reason or "")
        self.assertIn("typecheck", wf.reason or "")

    def test_dry_run_top_level_not_passed(self) -> None:
        # Dry-run must never report PASSED at the top.
        cfg = _cfg(
            commands={
                "lint": [["python3", "-c", "print('ok')"]],
            },
            workflows={"check": ["lint"]},
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="check", dry_run=True), result)
        self.assertEqual(result.status, STATUS_SKIPPED)
        wf = result.stages[0]
        self.assertEqual(wf.status, STATUS_SKIPPED)
        self.assertEqual(wf.reason, "dry-run")

    def test_all_passed_workflow_still_passed(self) -> None:
        # Sanity check: when nothing is skipped, top stays PASSED.
        cfg = _cfg(
            commands={
                "lint": [["python3", "-c", "print('ok')"]],
                "test": [["python3", "-c", "print('ok')"]],
            },
            workflows={"check": ["lint", "test"]},
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="check"), result)
        self.assertEqual(result.status, STATUS_PASSED)

    def test_failed_takes_precedence_over_skipped(self) -> None:
        # If one stage fails and another would skip, FAILED wins (fail-fast).
        cfg = _cfg(
            commands={
                "lint": [["python3", "-c", "import sys; sys.exit(1)"]],
                "typecheck": [["this-binary-does-not-exist"]],
            },
            workflows={"check": ["lint", "typecheck"]},
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="check"), result)
        self.assertEqual(result.status, STATUS_FAILED)


class EntryDistributionTests(unittest.TestCase):
    """§八 items 4, 5: entry works without canonical home, init target runs."""

    def test_entry_no_hardcoded_canonical_path(self) -> None:
        # The harness script must not contain machine-specific paths.
        repo_root = HERE.parent.parent
        entry = (repo_root / "harness").read_text(encoding="utf-8")
        self.assertNotIn("/Users/tommacmini4", entry)
        self.assertNotIn("_CANONICAL_HOME", entry)

    def test_entry_runs_in_isolated_copy(self) -> None:
        # Copy the harness script + src/ to a temp dir; unset HARNESS_HOME;
        # run --help. Must succeed without any canonical fallback.
        import shutil
        import subprocess

        repo_root = HERE.parent.parent
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # Copy harness script
            shutil.copy2(repo_root / "harness", d / "harness")
            (d / "harness").chmod(0o755)
            # Copy src/ so the script finds ai_harness adjacent
            shutil.copytree(repo_root / "src", d / "src")
            # Run with cleared HARNESS_HOME
            env = {k: v for k, v in os.environ.items() if k != "HARNESS_HOME"}
            env["PATH"] = os.environ.get("PATH", "")
            proc = subprocess.run(
                [str(d / "harness"), "--version"],
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("harness", proc.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
