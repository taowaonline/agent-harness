"""Tests for eval snapshot tri-mode (replay / record / diff).

Adapted from dsh's DSH_SNAPSHOT record/replay/refresh state machine.
replay = keyless CI gate on recorded fixtures; record = run the runner
and write fixtures back (human reviews the diff); diff = run the runner
and compare without writing (behavior-change gate).
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

from agent_harness.cli import main  # noqa: E402
from agent_harness.config import (  # noqa: E402
    Config,
    EvalConfig,
    ProjectInfo,
    SecurityConfig,
)
from agent_harness.evals import run_eval  # noqa: E402
from agent_harness.result import STATUS_FAILED, STATUS_PASSED, RunResult  # noqa: E402

REPO = HERE.parent.parent


def _stable_runner_script(answer: str) -> str:
    """A runner that echoes the query as the answer (deterministic)."""
    return textwrap.dedent(f"""
        import sys, json
        for line in sys.stdin:
            case = json.loads(line)
            q = (case.get("input") or {{}}).get("query", "")
            sys.stdout.write(json.dumps({{
                "case_id": case["id"],
                "output": {{"answer": {answer!r}}},
            }}) + "\\n")
    """)


class SnapshotModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def _write_runner(self, answer: str) -> str:
        p = self.dir / "runner.py"
        p.write_text(_stable_runner_script(answer), encoding="utf-8")
        p.chmod(0o755)
        return str(p)

    def _write_dataset(self, fixture_answer: str | None) -> Path:
        p = self.dir / "ds.jsonl"
        rec: dict = {
            "id": "c1",
            "input": {"query": "hello"},
            "expected": {"contains": ["hello"]},
        }
        if fixture_answer is not None:
            rec["input"]["output"] = {"answer": fixture_answer}
        p.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
        return p

    def _cfg(self, runner: str | None) -> Config:
        ds = str(self.dir / "ds.jsonl")
        return Config(
            version=1,
            project=ProjectInfo(name="t", language="python"),
            commands={},
            workflows={},
            evals={
                "smoke": EvalConfig(
                    dataset=ds,
                    runner=["python3", runner] if runner else None,
                    min_pass_rate=0.5,
                    timeout_seconds=10,
                )
            },
            security=SecurityConfig(),
        )

    # ── replay (existing behavior, unchanged) ─────────────────────

    def test_replay_grades_recorded_fixture(self) -> None:
        self._write_dataset(fixture_answer="hello world")
        cfg = self._cfg(runner=None)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True, snapshot_mode="replay")
        self.assertEqual(stage.status, STATUS_PASSED)
        self.assertEqual(stage.metrics["summary"]["passed"], 1)

    # ── record ────────────────────────────────────────────────────

    def test_record_writes_runner_output_back_as_fixture(self) -> None:
        # Dataset has NO fixture; record must produce one from the runner.
        self._write_dataset(fixture_answer=None)
        runner = self._write_runner("hello world")
        cfg = self._cfg(runner=runner)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True, snapshot_mode="record")
        # After recording, the dataset grades green in replay mode.
        self.assertEqual(stage.status, STATUS_PASSED)
        self.assertEqual(result.summary.get("recorded_fixtures"), 1)
        # The dataset file on disk now carries the fixture.
        line = json.loads((self.dir / "ds.jsonl").read_text().strip())
        self.assertEqual(line["input"]["output"], {"answer": "hello world"})

    def test_record_overwrites_stale_fixture(self) -> None:
        self._write_dataset(fixture_answer="stale answer")
        runner = self._write_runner("hello world")
        cfg = self._cfg(runner=runner)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True, snapshot_mode="record")
        self.assertEqual(stage.status, STATUS_PASSED)
        line = json.loads((self.dir / "ds.jsonl").read_text().strip())
        self.assertEqual(line["input"]["output"], {"answer": "hello world"})

    def test_record_requires_runner(self) -> None:
        self._write_dataset(fixture_answer=None)
        cfg = self._cfg(runner=None)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True, snapshot_mode="record")
        self.assertEqual(stage.status, STATUS_FAILED)
        self.assertIn("requires", " ".join(result.errors))

    # ── diff ──────────────────────────────────────────────────────

    def test_diff_passes_when_behavior_matches_fixture(self) -> None:
        self._write_dataset(fixture_answer="hello world")
        runner = self._write_runner("hello world")
        cfg = self._cfg(runner=runner)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True, snapshot_mode="diff")
        self.assertEqual(stage.status, STATUS_PASSED)
        self.assertEqual(stage.metrics["summary"]["matched"], 1)
        self.assertEqual(stage.metrics["summary"]["mismatched"], 0)

    def test_diff_fails_on_behavior_change_without_writing(self) -> None:
        self._write_dataset(fixture_answer="hello world")
        runner = self._write_runner("changed answer")
        cfg = self._cfg(runner=runner)
        before = (self.dir / "ds.jsonl").read_text()
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True, snapshot_mode="diff")
        self.assertEqual(stage.status, STATUS_FAILED)
        self.assertEqual(stage.metrics["summary"]["mismatched"], 1)
        joined = " ".join(result.errors)
        self.assertIn("snapshot diff", joined)
        self.assertIn("c1", joined)
        # Crucially: the dataset was NOT modified.
        self.assertEqual(before, (self.dir / "ds.jsonl").read_text())

    def test_diff_reports_missing_fixture_as_mismatch(self) -> None:
        self._write_dataset(fixture_answer=None)
        runner = self._write_runner("hello world")
        cfg = self._cfg(runner=runner)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True, snapshot_mode="diff")
        self.assertEqual(stage.status, STATUS_FAILED)
        self.assertEqual(stage.metrics["summary"]["mismatched"], 1)

    def test_diff_requires_runner(self) -> None:
        self._write_dataset(fixture_answer=None)
        cfg = self._cfg(runner=None)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True, snapshot_mode="diff")
        self.assertEqual(stage.status, STATUS_FAILED)

    # ── CLI surface ───────────────────────────────────────────────

    def test_cli_snapshot_mode_diff_end_to_end(self) -> None:
        self._write_dataset(fixture_answer="hello world")
        runner = self._write_runner("hello world")
        (self.dir / "harness.toml").write_text(
            textwrap.dedent(f"""
                version = 1
                [project]
                name = "t"
                language = "python"
                [evals.smoke]
                dataset = "ds.jsonl"
                runner = ["python3", "{runner}"]
                min_pass_rate = 0.5
                timeout_seconds = 10
            """),
            encoding="utf-8",
        )
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(["eval", "smoke", "--snapshot-mode", "diff", "--json"])
        self.assertEqual(rc, 0, err_buf.getvalue())
        data = json.loads(out_buf.getvalue())
        self.assertEqual(data["status"], "passed")
        self.assertEqual(data["summary"]["snapshot_mode"], "diff")

    def test_cli_offline_alias_still_replay(self) -> None:
        self._write_dataset(fixture_answer="hello world")
        (self.dir / "harness.toml").write_text(
            textwrap.dedent("""
                version = 1
                [project]
                name = "t"
                language = "python"
                [evals.smoke]
                dataset = "ds.jsonl"
                min_pass_rate = 0.5
            """),
            encoding="utf-8",
        )
        out_buf, err_buf = io.StringIO(), io.StringIO()
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            rc = main(["eval", "smoke", "--offline", "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(out_buf.getvalue())
        self.assertEqual(data["summary"]["snapshot_mode"], "replay")

    def test_unknown_mode_rejected(self) -> None:
        self._write_dataset(fixture_answer=None)
        cfg = self._cfg(runner=None)
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True, snapshot_mode="bogus")
        self.assertEqual(stage.status, STATUS_FAILED)
        self.assertIn("unknown snapshot_mode", " ".join(result.errors))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
