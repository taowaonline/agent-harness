"""Tests for HARNESS_FIFTH_REVIEW §八 items 12, 13.

12: Schema for empty commands matches parser.
13: Two reports persisted in the same second don't overwrite.
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

from ai_harness.config import load_config  # noqa: E402
from ai_harness.evals import (  # noqa: E402
    EvalReport,
    _persist_report,
)


REPO = HERE.parent.parent


class SchemaParserParityTests(unittest.TestCase):
    """§八 12: Schema and parser agree on `typecheck = []`."""

    def test_schema_allows_empty_argv_list(self) -> None:
        # The schema's outer commands array no longer requires minItems=1.
        s = json.loads((REPO / "harness.schema.json").read_text())
        commands_schema = s["properties"]["commands"]
        self.assertNotIn("minItems", commands_schema["additionalProperties"])

    def test_parser_accepts_empty_list_as_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "harness.toml").write_text(
                'version = 1\n[project]\nname = "x"\nlanguage = "python"\n'
                '[commands]\ntypecheck = []\n',
                encoding="utf-8",
            )
            cfg = load_config(d / "harness.toml")
            self.assertEqual(cfg.commands["typecheck"], [])


class ReportAtomicityTests(unittest.TestCase):
    """§八 13: Same-second reports don't overwrite."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def _make_report(self, started_at: str = "2026-08-08T10:00:00Z") -> EvalReport:
        return EvalReport(
            name="smoke",
            dataset="ds.jsonl",
            started_at=started_at,
            duration_ms=10,
            harness_version="test",
            git_sha="unknown",
            summary={"pass_rate": 1.0, "passed": 1, "failed": 0,
                     "errors": 0, "skipped": 0, "total": 1,
                     "p50_latency_ms": 0, "p95_latency_ms": 0},
            cases=[],
            thresholds={"min_pass_rate": 0.9},
            status="passed",
        )

    def test_two_reports_same_timestamp_dont_overwrite(self) -> None:
        rep1 = self._make_report()
        rep2 = self._make_report()
        # Both have identical timestamps; without run_id in filename they
        # would collide.
        out1 = _persist_report(rep1, project_root=self.dir)
        out2 = _persist_report(rep2, project_root=self.dir)
        self.assertNotEqual(out1, out2)
        self.assertTrue(out1.exists())
        self.assertTrue(out2.exists())
        # Each has the run_id short hash suffix.
        self.assertRegex(out1.name, r"smoke-\d{8}T\d{6}Z-[0-9a-f]{8}\.json")
        self.assertRegex(out2.name, r"smoke-\d{8}T\d{6}Z-[0-9a-f]{8}\.json")

    def test_atomic_write_no_tmp_file_left(self) -> None:
        rep = self._make_report()
        _persist_report(rep, project_root=self.dir)
        # No leftover .tmp files in the reports dir.
        tmp_files = list((self.dir / "evals" / "reports").glob("*.tmp"))
        self.assertEqual(tmp_files, [])

    def test_report_includes_run_id_field(self) -> None:
        rep = self._make_report()
        out = _persist_report(rep, project_root=self.dir)
        data = json.loads(out.read_text())
        self.assertIn("run_id", data)
        self.assertEqual(len(data["run_id"]), 32)  # uuid hex


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
