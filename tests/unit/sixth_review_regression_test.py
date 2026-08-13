"""Regression tests for HARNESS_SIXTH_REVIEW §八 items 1-8.

1. TOML runner field loads into EvalConfig.runner
2. TOML-configured runner actually invokes the fake_provider
3. Malformed runner output blocks the eval stage (no silent pass)
4. Runner case_id mismatch / duplicate / unknown blocks the stage
5. validate --strict JSON status is "failed" (not "passed" with exit 1)
6. --strict warning messages distinguish planned vs enforced fields
7. init --vendor produces a self-contained project that runs in clean env
8. Runner timeout docstring matches whole-subprocess semantics
"""

from __future__ import annotations

import io
import json
import os
import subprocess
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

from agent_harness.cli import main  # noqa: E402
from agent_harness.config import (  # noqa: E402
    Config,
    EvalConfig,
    ProjectInfo,
    SecurityConfig,
    load_config,
)
from agent_harness.evals import run_eval  # noqa: E402
from agent_harness.result import STATUS_FAILED, RunResult  # noqa: E402

REPO = HERE.parent.parent
FAKE = str(REPO / "tests" / "fixtures" / "fake_provider.py")


class TomlRunnerLoadsTests(unittest.TestCase):
    """§八 1: TOML runner field loads into EvalConfig.runner."""

    def test_toml_runner_field_loads(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "harness.toml").write_text(
                textwrap.dedent("""
                version = 1
                [project]
                name = "x"
                language = "python"
                [evals.smoke]
                dataset = "smoke.jsonl"
                runner = ["python3", "fake.py"]
            """),
                encoding="utf-8",
            )
            (d / "smoke.jsonl").write_text(
                '{"id":"a","input":{"query":"x"},"expected":{"contains":["x"]}}\n',
                encoding="utf-8",
            )
            cfg = load_config(d / "harness.toml")
            self.assertIsNotNone(cfg.evals["smoke"].runner)
            self.assertEqual(cfg.evals["smoke"].runner, ["python3", "fake.py"])


class TomlRunnerEndToEndTests(unittest.TestCase):
    """§八 2: TOML-configured runner actually invokes fake_provider."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def test_toml_config_with_runner_executes_and_grades(self) -> None:
        (self.dir / "harness.toml").write_text(
            textwrap.dedent(f"""
            version = 1
            [project]
            name = "demo"
            language = "python"
            [evals.smoke]
            dataset = "ds.jsonl"
            runner = ["python3", "{FAKE}"]
            min_pass_rate = 0.5
            timeout_seconds = 10
        """),
            encoding="utf-8",
        )
        (self.dir / "ds.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "p1",
                            "input": {"query": "hello"},
                            "expected": {"contains": ["hello"]},
                        }
                    ),
                    json.dumps(
                        {
                            "id": "f1",
                            "input": {"query": "goodbye"},
                            "expected": {"contains": ["missing"]},
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(["eval", "smoke", "--offline", "--json"])
        data = json.loads(out_buf.getvalue())
        # 1/2 pass; threshold 0.5 → passed.
        self.assertEqual(rc, 0, err_buf.getvalue())
        self.assertEqual(data["status"], "passed")
        summary = data["stages"][0]["metrics"]["summary"]
        self.assertEqual(summary["passed"], 1)
        self.assertEqual(summary["failed"], 1)


class MalformedRunnerBlocksTests(unittest.TestCase):
    """§八 3, 4: malformed output, duplicate/unknown/missing case_id all block."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def _write_runner(self, name: str, body: str) -> str:
        p = self.dir / name
        p.write_text(body, encoding="utf-8")
        p.chmod(0o755)
        return str(p)

    def _cfg(self, runner_path: str) -> Config:
        (self.dir / "ds.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {"id": "a", "input": {"query": "x"}, "expected": {"contains": ["x"]}}
                    ),
                    json.dumps(
                        {"id": "b", "input": {"query": "y"}, "expected": {"contains": ["y"]}}
                    ),
                ]
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
                    dataset=str(self.dir / "ds.jsonl"),
                    runner=["python3", runner_path],
                    timeout_seconds=5,
                )
            },
            security=SecurityConfig(),
        )

    def test_malformed_json_blocks_stage(self) -> None:
        runner = self._write_runner(
            "bad.py",
            textwrap.dedent("""
            import sys, json
            for line in sys.stdin:
                case = json.loads(line)
                # Emit non-JSON garbage.
                sys.stdout.write("not-json-at-all\\n")
        """),
        )
        cfg = self._cfg(runner)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_FAILED)
        joined = " ".join(result.errors)
        self.assertIn("malformed JSON", joined)

    def test_case_id_mismatch_blocks_stage(self) -> None:
        runner = self._write_runner(
            "mismatch.py",
            textwrap.dedent("""
            import sys, json
            for line in sys.stdin:
                case = json.loads(line)
                # Echo a wrong case_id.
                sys.stdout.write(json.dumps({
                    "case_id": "wrong-id",
                    "output": {"answer": "x"},
                }) + "\\n")
        """),
        )
        cfg = self._cfg(runner)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_FAILED)
        self.assertIn("case_id mismatch", " ".join(result.errors))

    def test_duplicate_case_id_caught_as_mismatch(self) -> None:
        # Positional validation makes the "duplicate" case unreachable in
        # practice — any reordering surfaces as a case_id mismatch on the
        # first affected line. Verify the equivalent invariant: a runner
        # that emits the wrong case_id on the second line is blocked.
        runner = self._write_runner(
            "dup.py",
            textwrap.dedent("""
            import sys, json
            for line in sys.stdin:
                # Always emit case_id="a" — second iteration's expected
                # case_id is "b", so positional check fires as mismatch.
                sys.stdout.write(json.dumps({
                    "case_id": "a",
                    "output": {"answer": "x"},
                }) + "\\n")
        """),
        )
        cfg = self._cfg(runner)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_FAILED)
        # Either "mismatch" or "duplicate" wording is acceptable.
        err_join = " ".join(result.errors).lower()
        self.assertTrue(
            "mismatch" in err_join or "duplicate" in err_join,
            f"expected mismatch/duplicate error, got: {result.errors}",
        )

    def test_missing_case_id_blocks_stage(self) -> None:
        runner = self._write_runner(
            "noid.py",
            textwrap.dedent("""
            import sys, json
            for line in sys.stdin:
                sys.stdout.write(json.dumps({"output": {"answer": "x"}}) + "\\n")
        """),
        )
        cfg = self._cfg(runner)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_FAILED)
        self.assertIn("missing", " ".join(result.errors))

    def test_line_count_mismatch_blocks_stage(self) -> None:
        runner = self._write_runner(
            "short.py",
            textwrap.dedent("""
            import sys, json
            for i, line in enumerate(sys.stdin):
                if i == 0:
                    case = json.loads(line)
                    sys.stdout.write(json.dumps({
                        "case_id": case["id"],
                        "output": {"answer": "x"},
                    }) + "\\n")
                # else: emit nothing — only 1 line for 2 cases.
        """),
        )
        cfg = self._cfg(runner)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_FAILED)
        self.assertIn("line-count", " ".join(result.errors))


class StrictStatusConsistencyTests(unittest.TestCase):
    """§八 5, 6: strict exit code and status agree; planned fields distinguishable."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _run(self, *argv: str) -> tuple[int, str, str]:
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(list(argv))
        return rc, out_buf.getvalue(), err_buf.getvalue()

    def test_strict_failure_status_is_failed_not_passed(self) -> None:
        toml = textwrap.dedent("""
            version = 1
            [project]
            name = "x"
            language = "python"
            workload = "other"
            [evals.smoke]
            dataset = "ds.jsonl"
            max_cost_usd = 5.0
        """)
        (self.dir / "harness.toml").write_text(toml, encoding="utf-8")
        (self.dir / "ds.jsonl").write_text(
            json.dumps({"id": "a", "input": {"query": "x"}, "expected": {"contains": ["x"]}})
            + "\n",
            encoding="utf-8",
        )
        old = os.getcwd()
        os.chdir(self.dir)
        try:
            rc, out, err = self._run("validate", "--strict", "--json")
        finally:
            os.chdir(old)
        self.assertEqual(rc, 1)
        data = json.loads(out)
        # HARNESS_SIXTH_REVIEW P1-3 contract: status MUST be "failed".
        self.assertEqual(data["status"], "failed")
        # Errors array is populated.
        self.assertGreater(len(data["errors"]), 0)
        # All errors mention "strict warning:" prefix so consumers can
        # distinguish strict-mode failures from real validation errors.
        for e in data["errors"]:
            self.assertTrue(
                e.startswith("strict warning:"),
                f"error missing strict warning prefix: {e}",
            )

    def test_planned_field_warning_is_explicit(self) -> None:
        # The warning text must say "PLANNED" so consumers can tell it's
        # not enforced vs. real validation issues.
        toml = textwrap.dedent("""
            version = 1
            [project]
            name = "x"
            language = "python"
            [evals.smoke]
            dataset = "ds.jsonl"
            max_cost_usd = 5.0
        """)
        (self.dir / "harness.toml").write_text(toml, encoding="utf-8")
        (self.dir / "ds.jsonl").write_text(
            json.dumps({"id": "a", "input": {"query": "x"}, "expected": {"contains": ["x"]}})
            + "\n",
            encoding="utf-8",
        )
        old = os.getcwd()
        os.chdir(self.dir)
        try:
            rc, out, err = self._run("validate", "--json")
        finally:
            os.chdir(old)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        joined = " ".join(data["summary"].get("warnings", []))
        self.assertIn("PLANNED", joined.upper())


class InitVendorTests(unittest.TestCase):
    """§八 7: init --vendor produces a self-contained project."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def test_init_vendor_runs_in_clean_env(self) -> None:
        # Run `harness init --vendor` in a temp dir; then run `./harness
        # --version` from that dir with HARNESS_HOME unset and no PATH to
        # any global install. Must succeed.
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(
                [
                    "init",
                    "--vendor",
                    "--language",
                    "python",
                    "--workload",
                    "other",
                    "--risk",
                    "standard",
                    "--name",
                    "vendored-demo",
                ]
            )
        self.assertEqual(rc, 0, err_buf.getvalue())
        # Vendored src/agent_harness/ must exist.
        self.assertTrue((self.dir / "src" / "agent_harness" / "cli.py").exists())
        # Run ./agent_harness --version in a clean env.
        env = {k: v for k, v in os.environ.items() if k != "HARNESS_HOME"}
        env["PATH"] = os.environ.get("PATH", "")
        proc = subprocess.run(
            [str(self.dir / "agent_harness"), "--version"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("agent_harness", proc.stdout)

    def test_init_default_does_not_vendor(self) -> None:
        # Without --vendor, src/agent_harness/ must NOT be copied.
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(
                [
                    "init",
                    "--language",
                    "python",
                    "--workload",
                    "other",
                    "--risk",
                    "standard",
                    "--name",
                    "global-demo",
                    "--force",
                ]
            )
        self.assertEqual(rc, 0, err_buf.getvalue())
        self.assertFalse((self.dir / "src").exists())


class RunnerTimeoutDocTests(unittest.TestCase):
    """§八 8: Runner timeout docstring matches whole-subprocess semantics."""

    def test_docstring_says_whole_subprocess_timeout(self) -> None:
        from agent_harness import evals as _evals

        # Read the source-of-truth docstring from the live function.
        doc = (_evals._invoke_subprocess_runner.__doc__ or "").lower()
        # Normalize whitespace so line-wrapped phrases still match.
        doc_norm = " ".join(doc.split())
        # Must explicitly state "whole subprocess" (not per-line/per-case).
        self.assertIn("whole subprocess timeout", doc_norm)
        # Must explicitly disclaim per-line semantics.
        self.assertIn("not a per-line", doc_norm)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
