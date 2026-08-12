"""Tests for [security].scan_exclude (false-positive mitigation)."""

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

from agent_harness.config import (  # noqa: E402
    Config,
    ProjectInfo,
    SecurityConfig,
)
from agent_harness.result import STATUS_FAILED, STATUS_PASSED, RunResult  # noqa: E402
from agent_harness.security import _matches_exclude, run_security_check  # noqa: E402


def _cfg(security: SecurityConfig) -> Config:
    return Config(
        version=1,
        project=ProjectInfo(name="t", language="other", workload="other"),
        commands={},
        workflows={},
        evals={},
        security=security,
    )


class ExcludePatternMatchingTests(unittest.TestCase):
    """Direct tests of the pattern matcher."""

    def test_double_star_matches_directory_tree(self) -> None:
        self.assertTrue(_matches_exclude("tools/dict.txt", ["tools/**"]))
        self.assertTrue(_matches_exclude("tools/sub/a.txt", ["tools/**"]))
        self.assertTrue(_matches_exclude("tools/sub/deep/b.json", ["tools/**"]))

    def test_double_star_does_not_match_unrelated(self) -> None:
        self.assertFalse(_matches_exclude("src/app.py", ["tools/**"]))
        self.assertFalse(_matches_exclude("tools_meta/x.py", ["tools/**"]))

    def test_trailing_slash_matches_inside(self) -> None:
        self.assertTrue(_matches_exclude("vendor/lib.js", ["vendor/"]))
        self.assertFalse(_matches_exclude("vendor", ["vendor/"]))

    def test_basename_glob_matches_nested(self) -> None:
        self.assertTrue(_matches_exclude("a/b/c/file.min.js", ["*.min.js"]))
        self.assertTrue(_matches_exclude("file.min.js", ["*.min.js"]))
        self.assertFalse(_matches_exclude("file.js", ["*.min.js"]))

    def test_exact_path_match(self) -> None:
        self.assertTrue(_matches_exclude("tools/dict.txt", ["tools/dict.txt"]))
        self.assertFalse(_matches_exclude("tools/other.txt", ["tools/dict.txt"]))

    def test_no_patterns_matches_nothing(self) -> None:
        self.assertFalse(_matches_exclude("anything", []))


class ScanExcludeIntegrationTests(unittest.TestCase):
    """End-to-end: a fake 'secret' in scan_exclude paths is ignored."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def _write_dict_file(self) -> None:
        # Write a file with content that would over-fire the AWS secret
        # regex ([A-Za-z0-9/+]{40}).
        d = Path(self.tmp.name) / "tools" / "data-sources"
        d.mkdir(parents=True)
        (d / "dict.txt").write_text(
            "key AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA value\n" * 5,
            encoding="utf-8",
        )

    def test_scan_exclude_skips_dict_files(self) -> None:
        self._write_dict_file()
        sec = SecurityConfig(
            tool_allowlist=["retrieve"],
            require_approval_for=["external_write", "delete"],
            scan_exclude=["tools/**"],
        )
        cfg = _cfg(sec)
        result = RunResult(command="security")
        stage = run_security_check(cfg, result)
        self.assertEqual(stage.status, STATUS_PASSED, result.errors)
        self.assertEqual(stage.metrics["findings_count"], 0)

    def test_without_scan_exclude_the_dict_triggers_findings(self) -> None:
        # Sanity: same setup but without exclude → must FAIL.
        self._write_dict_file()
        sec = SecurityConfig(
            tool_allowlist=["retrieve"],
            require_approval_for=["external_write", "delete"],
        )
        cfg = _cfg(sec)
        result = RunResult(command="security")
        stage = run_security_check(cfg, result)
        self.assertEqual(stage.status, STATUS_FAILED)
        self.assertGreater(stage.metrics["findings_count"], 0)
        # The findings mention the dict file.
        joined = " ".join(result.errors)
        self.assertIn("dict.txt", joined)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
