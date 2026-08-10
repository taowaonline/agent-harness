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

    severity is one of: 'notice', 'error'.
    exit_code is 0 (pass) or 1 (block).

    Truth table (updated R3 from HARNESS_CURRENT_CHANGE_QUALITY_EVALUATION):
      prototype  → notice,  exit 0  (accept missing scanner)
      standard   → error,   exit 1  (scanner MUST be installed)
      high-risk  → error,   exit 1  (scanner MUST be installed)
    """
    if tool_installed:
        return ("ran", 0)  # tool ran; downstream pass/fail is on the tool itself
    table = {
        "prototype": ("notice", 0),
        "standard": ("error", 1),
        "high-risk": ("error", 1),
    }
    return table.get(risk, ("error", 1))


class RiskAwareScannerPolicyTests(unittest.TestCase):
    """§八 14: missing scanners are notice/blocked by risk level.

    R3 update: standard risk now blocks (was warning). Only prototype
    accepts missing scanners.
    """

    def test_prototype_missing_scanner_is_notice(self) -> None:
        sev, rc = scanner_decision("prototype", tool_installed=False)
        self.assertEqual(sev, "notice")
        self.assertEqual(rc, 0)

    def test_standard_missing_scanner_blocks(self) -> None:
        sev, rc = scanner_decision("standard", tool_installed=False)
        self.assertEqual(sev, "error")
        self.assertEqual(rc, 1)

    def test_high_risk_missing_scanner_blocks(self) -> None:
        sev, rc = scanner_decision("high-risk", tool_installed=False)
        self.assertEqual(sev, "error")
        self.assertEqual(rc, 1)

    def test_installed_scanner_passes_regardless_of_risk(self) -> None:
        for risk in ("prototype", "standard", "high-risk"):
            sev, rc = scanner_decision(risk, tool_installed=True)
            self.assertEqual(sev, "ran")
            self.assertEqual(rc, 0, f"risk={risk}")

    def test_unknown_risk_defaults_to_block(self) -> None:
        # Defensive: unknown risk should not silently pass.
        sev, rc = scanner_decision("weird", tool_installed=False)
        self.assertEqual(sev, "error")
        self.assertEqual(rc, 1)


class WorkflowYamlParityTests(unittest.TestCase):
    """Lock the YAML's case-statement against the Python truth table."""

    def setUp(self) -> None:
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent.parent
        self.yml = (repo_root / ".github" / "workflows" / "security.yml").read_text()

    def test_yaml_mentions_all_three_risk_levels(self) -> None:
        for risk in ("prototype", "standard", "high-risk"):
            self.assertIn(risk, self.yml, f"missing {risk} case in YAML")

    def test_yaml_standard_and_high_risk_block_on_missing_scanner(self) -> None:
        # R3: both standard and high-risk must exit 1 on missing scanner.
        # The case blocks are indented 14 spaces ("              standard)").
        for risk_block in ("              standard)", "              high-risk)"):
            with self.subTest(risk_block=risk_block.strip()):
                self.assertIn(risk_block, self.yml)
                # Each occurrence should have exit 1 within the same block.
                # Find all occurrences and verify each has exit 1 nearby.
                start = 0
                while True:
                    idx = self.yml.find(risk_block, start)
                    if idx == -1:
                        break
                    snippet = self.yml[idx : idx + 200]
                    self.assertIn(
                        "exit 1",
                        snippet,
                        f"{risk_block.strip()} block missing exit 1",
                    )
                    start = idx + 1

    def test_yaml_prototype_does_not_block(self) -> None:
        # Prototype should have notice, not exit 1, nearby.
        self.assertIn("prototype)", self.yml)
        idx = self.yml.index("prototype)")
        snippet = self.yml[idx : idx + 200]
        self.assertIn("::notice", snippet)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
