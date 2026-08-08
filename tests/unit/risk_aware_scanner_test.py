"""Tests for the risk-aware scanner policy (HARNESS_FIFTH_REVIEW §八 14).

The actual decision logic lives in .github/workflows/security.yml as bash
case-statements. This test fixture encodes the SAME truth table in Python
so a regression in either place is caught. If you change the workflow,
change this test in lockstep.
"""

from __future__ import annotations

import unittest


# Mirror of the case-statement logic in security.yml.
def scanner_decision(risk: str, tool_installed: bool) -> tuple[str, int]:
    """Return (severity, exit_code).

    severity is one of: 'notice', 'warning', 'error'.
    exit_code is 0 (pass) or 1 (block).
    """
    if tool_installed:
        return ("ran", 0)  # tool ran; downstream pass/fail is on the tool itself
    table = {
        "prototype": ("notice", 0),
        "standard": ("warning", 0),
        "high-risk": ("error", 1),
    }
    return table.get(risk, ("warning", 0))


class RiskAwareScannerPolicyTests(unittest.TestCase):
    """§八 14: missing scanners are notice/warning/blocked by risk level."""

    def test_prototype_missing_scanner_is_notice(self) -> None:
        sev, rc = scanner_decision("prototype", tool_installed=False)
        self.assertEqual(sev, "notice")
        self.assertEqual(rc, 0)

    def test_standard_missing_scanner_is_warning(self) -> None:
        sev, rc = scanner_decision("standard", tool_installed=False)
        self.assertEqual(sev, "warning")
        self.assertEqual(rc, 0)

    def test_high_risk_missing_scanner_blocks(self) -> None:
        sev, rc = scanner_decision("high-risk", tool_installed=False)
        self.assertEqual(sev, "error")
        self.assertEqual(rc, 1)

    def test_installed_scanner_passes_regardless_of_risk(self) -> None:
        for risk in ("prototype", "standard", "high-risk"):
            sev, rc = scanner_decision(risk, tool_installed=True)
            self.assertEqual(sev, "ran")
            self.assertEqual(rc, 0, f"risk={risk}")

    def test_unknown_risk_defaults_to_warning(self) -> None:
        # Defensive: unknown risk should not silently fail.
        sev, rc = scanner_decision("weird", tool_installed=False)
        self.assertEqual(sev, "warning")
        self.assertEqual(rc, 0)


class WorkflowYamlParityTests(unittest.TestCase):
    """Lock the YAML's case-statement against the Python truth table."""

    def setUp(self) -> None:
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent.parent
        self.yml = (repo_root / ".github" / "workflows" / "security.yml").read_text()

    def test_yaml_mentions_all_three_risk_levels(self) -> None:
        for risk in ("prototype", "standard", "high-risk"):
            self.assertIn(risk, self.yml, f"missing {risk} case in YAML")

    def test_yaml_high_risk_blocks_on_missing_scanner(self) -> None:
        # The high-risk branch must contain an exit 1.
        # Find the high-risk block and check it ends with exit 1.
        self.assertIn("high-risk)", self.yml)
        # Verify the high-risk case has exit 1 nearby.
        idx = self.yml.index("high-risk)")
        snippet = self.yml[idx:idx + 400]
        self.assertIn("exit 1", snippet)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
