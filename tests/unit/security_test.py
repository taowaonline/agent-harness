"""Unit tests for ai_harness.security and ai_harness.policy."""

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
from ai_harness.policy import (  # noqa: E402
    PolicyDecision,
    check_tool_allowed,
    check_write_requires_approval,
)
from ai_harness.result import STATUS_FAILED, STATUS_PASSED, RunResult  # noqa: E402
from ai_harness.security import run_security_check  # noqa: E402


def _cfg(security: SecurityConfig | None = None) -> Config:
    return Config(
        version=1,
        project=ProjectInfo(name="t", language="python"),
        commands={},
        workflows={},
        evals={},
        security=security or SecurityConfig(),
    )


class PolicyTests(unittest.TestCase):
    def test_tool_allowed_when_in_allowlist(self) -> None:
        sec = SecurityConfig(tool_allowlist=["search"])
        d = check_tool_allowed("search", sec)
        self.assertTrue(d.allowed)

    def test_tool_blocked_when_not_in_allowlist(self) -> None:
        sec = SecurityConfig(tool_allowlist=["search"])
        d = check_tool_allowed("delete_user", sec)
        self.assertFalse(d.allowed)
        self.assertIn("not in tool_allowlist", d.reason)

    def test_empty_allowlist_blocks_all(self) -> None:
        sec = SecurityConfig(tool_allowlist=[])
        d = check_tool_allowed("anything", sec)
        self.assertFalse(d.allowed)

    def test_write_requires_approval(self) -> None:
        sec = SecurityConfig(require_approval_for=["delete"])
        d = check_write_requires_approval("delete", sec)
        self.assertFalse(d.allowed)
        d = check_write_requires_approval("external_write", sec)
        self.assertTrue(d.allowed)


class SecurityCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self._cwd)

    def test_flags_weak_policy(self) -> None:
        # Empty allowlist and no required approvals should produce findings.
        sec = SecurityConfig(
            tool_allowlist=[],
            require_approval_for=[],
        )
        cfg = _cfg(security=sec)
        result = RunResult(command="security")
        stage = run_security_check(cfg, result)
        self.assertEqual(stage.status, STATUS_FAILED)
        self.assertGreaterEqual(stage.metrics["findings_count"], 3)
        # Findings should mention each missing approval kind.
        joined = " ".join(result.errors)
        self.assertIn("external_write", joined)
        self.assertIn("delete", joined)

    def test_passes_with_strong_policy(self) -> None:
        sec = SecurityConfig(
            tool_allowlist=["retrieve"],
            require_approval_for=["external_write", "delete", "deploy", "payment"],
        )
        cfg = _cfg(security=sec)
        result = RunResult(command="security")
        stage = run_security_check(cfg, result)
        # An empty tmpdir should not produce findings beyond policy.
        self.assertEqual(stage.status, STATUS_PASSED, result.errors)

    def test_detects_committed_secret(self) -> None:
        sec = SecurityConfig(
            tool_allowlist=["retrieve"],
            require_approval_for=["external_write", "delete", "deploy", "payment"],
        )
        cfg = _cfg(security=sec)
        # Write a file with a real-shaped secret in a non-test source path.
        # Build the secret at runtime so the literal never lands in source
        # (GitHub secret scanning would flag a static Stripe key).
        fake_stripe = "sk_test_" + "a" * 28
        (Path(self.tmp.name) / "app.py").write_text(
            f'API_KEY = "{fake_stripe}"\n',
            encoding="utf-8",
        )
        result = RunResult(command="security")
        stage = run_security_check(cfg, result)
        self.assertEqual(stage.status, STATUS_FAILED)
        joined = " ".join(result.errors)
        self.assertIn("app.py", joined)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
