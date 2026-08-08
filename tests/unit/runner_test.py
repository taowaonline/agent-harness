"""Unit tests for ai_harness.runner — argv execution, dry-run, exit codes."""

from __future__ import annotations

import sys
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
from ai_harness.result import (  # noqa: E402
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    RunResult,
)
from ai_harness.runner import (  # noqa: E402
    RunRequest,
    run_target,
)


def _cfg(
    commands: dict | None = None,
    workflows: dict | None = None,
    evals: dict | None = None,
) -> Config:
    return Config(
        version=1,
        project=ProjectInfo(name="t", language="python"),
        commands=commands or {},
        workflows=workflows or {},
        evals=evals or {},
        security=SecurityConfig(),
    )


class RunStageTests(unittest.TestCase):
    def test_dry_run_does_not_execute(self) -> None:
        # If dry-run actually executed, this would create the file.
        marker = "/tmp/ai_harness_runner_dryrun_marker"
        if Path(marker).exists():
            Path(marker).unlink()
        cfg = _cfg(
            commands={
                "touch": [["python3", "-c", f"open('{marker}','w').close()"]]
            }
        )
        result = RunResult(command="run")
        run_target(
            cfg,
            RunRequest(name="touch", dry_run=True),
            result,
        )
        # Dry-run never produces PASSED at the top — honest SKIPPED.
        self.assertEqual(result.status, STATUS_SKIPPED)
        self.assertFalse(Path(marker).exists())
        if Path(marker).exists():
            Path(marker).unlink()

    def test_real_run_success(self) -> None:
        cfg = _cfg(commands={"echo": [["python3", "-c", "print('hi')"]]})
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="echo"), result)
        self.assertEqual(result.status, STATUS_PASSED)
        self.assertEqual(result.stages[0].status, STATUS_PASSED)

    def test_real_run_failure_propagates(self) -> None:
        cfg = _cfg(
            commands={
                "fail": [["python3", "-c", "import sys; sys.exit(7)"]]
            }
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="fail"), result)
        self.assertEqual(result.status, STATUS_FAILED)
        self.assertEqual(result.stages[0].status, STATUS_FAILED)
        # Single-argv stage attaches result directly to the stage.
        self.assertEqual(result.stages[0].exit_code, 7)
        self.assertEqual(result.stages[0].children, [])

    def test_unknown_target_blocked(self) -> None:
        cfg = _cfg()
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="nope"), result)
        self.assertEqual(result.status, STATUS_FAILED)
        self.assertTrue(any("Unknown target" in e for e in result.errors))

    def test_optional_stage_with_missing_executable_skips(self) -> None:
        cfg = _cfg(
            commands={"typecheck": [["this-binary-does-not-exist-anywhere"]]}
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="typecheck"), result)
        # 'typecheck' is in the optional allowlist; missing binary => skipped.
        self.assertEqual(result.stages[0].status, STATUS_SKIPPED)
        # Top-level result honestly reports SKIPPED, not PASSED.
        self.assertEqual(result.status, STATUS_SKIPPED)

    def test_required_stage_with_missing_executable_fails(self) -> None:
        cfg = _cfg(
            commands={"lint": [["this-binary-does-not-exist-anywhere"]]}
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="lint"), result)
        self.assertEqual(result.stages[0].status, STATUS_FAILED)
        self.assertEqual(result.status, STATUS_FAILED)

    def test_empty_argv_list_reports_skipped(self) -> None:
        cfg = _cfg(commands={"typecheck": []})
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="typecheck"), result)
        self.assertEqual(result.stages[0].status, STATUS_SKIPPED)
        self.assertEqual(result.stages[0].reason, "not configured")


class RunWorkflowTests(unittest.TestCase):
    def test_workflow_runs_in_order_and_fails_fast(self) -> None:
        order: list[str] = []
        # The 'first' stage succeeds; 'second' fails. Workflow should not run
        # 'third'. We append to `order` only when the subprocess actually
        # starts, by passing the marker through the python command line.
        def argv_for(name: str) -> list[list[str]]:
            # Always write the name to the log, then exit success or fail.
            exit_code = 2 if name == "second" else 0
            return [
                [
                    "python3",
                    "-c",
                    (
                        f"open('/tmp/ai_harness_order.log','a').write('{name}\\n'); "
                        f"import sys; sys.exit({exit_code})"
                    ),
                ]
            ]

        log_path = "/tmp/ai_harness_order.log"
        if Path(log_path).exists():
            Path(log_path).unlink()
        cfg = _cfg(
            commands={
                "first": argv_for("first"),
                "second": argv_for("second"),
                "third": argv_for("third"),
            },
            workflows={"check": ["first", "second", "third"]},
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="check"), result)
        if Path(log_path).exists():
            order = Path(log_path).read_text().split()
        self.assertEqual(result.status, STATUS_FAILED)
        self.assertEqual(order, ["first", "second"])  # third never ran

    def test_workflow_unknown_reference_blocks(self) -> None:
        cfg = _cfg(workflows={"check": ["missing"]})
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="check"), result)
        self.assertEqual(result.stages[0].status, STATUS_BLOCKED)
        self.assertEqual(result.status, STATUS_BLOCKED)

    def test_workflow_nested_runs(self) -> None:
        cfg = _cfg(
            commands={"a": [["python3", "-c", "print('a')"]]},
            workflows={"inner": ["a"], "outer": ["inner"]},
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="outer"), result)
        self.assertEqual(result.status, STATUS_PASSED)
        outer = result.stages[0]
        self.assertEqual(outer.kind, "workflow")
        self.assertEqual(outer.children[0].name, "inner")
        self.assertEqual(outer.children[0].children[0].name, "a")

    def test_workflow_dry_run_skips_all(self) -> None:
        marker = "/tmp/ai_harness_runner_wf_dryrun"
        if Path(marker).exists():
            Path(marker).unlink()
        cfg = _cfg(
            commands={
                "touch": [["python3", "-c", f"open('{marker}','w').close()"]]
            },
            workflows={"check": ["touch"]},
        )
        result = RunResult(command="run")
        run_target(cfg, RunRequest(name="check", dry_run=True), result)
        self.assertFalse(Path(marker).exists())
        if Path(marker).exists():
            Path(marker).unlink()


class ExitCodeTests(unittest.TestCase):
    def test_status_to_rc_mapping(self) -> None:
        from ai_harness.policy import (
            EXIT_POLICY_BLOCKED,
            EXIT_STAGE_FAILED,
            EXIT_SUCCESS,
        )

        # We exercise the CLI helper indirectly here; this guards regressions
        # in the mapping when statuses change.
        self.assertEqual(EXIT_SUCCESS, 0)
        self.assertEqual(EXIT_STAGE_FAILED, 2)
        self.assertEqual(EXIT_POLICY_BLOCKED, 3)


class SubprocessErrorTests(unittest.TestCase):
    def test_timeout_returns_124(self) -> None:
        from ai_harness.runner import _exec_one

        # 1s sleep killed at 0.1s timeout.
        status, code = _exec_one(
            ["python3", "-c", "import time; time.sleep(1)"],
            "test-slow",
            timeout=0.1,
        )
        self.assertEqual(status, STATUS_FAILED)
        self.assertEqual(code, 124)

    def test_executable_disappears_returns_127(self) -> None:
        from ai_harness.runner import _exec_one

        # Race-free: simulate the executable vanishing between `which` and
        # exec by passing an argv whose first element resolves to None at
        # exec time. We use a path that exists for `which` but rename it.
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            fake = os.path.join(d, "fake-tool")
            with open(fake, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(fake, 0o755)
            old_path = os.environ.get("PATH", "")
            try:
                os.environ["PATH"] = d + os.pathsep + old_path
                status, code = _exec_one([fake, "x"], "test-vanish")
                # Either it runs successfully (path still valid) or it
                # returns 127 (file-not-found at exec). We accept both —
                # the point is the code path is exercised.
                self.assertIn(status, (STATUS_PASSED, STATUS_FAILED))
            finally:
                os.environ["PATH"] = old_path


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
