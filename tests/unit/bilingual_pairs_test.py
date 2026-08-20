"""Bilingual doc pairing verification (dsh lefthook concept, as a test).

Every English doc that has a `.zh.md` counterpart must keep the pair in
sync structurally: both files exist, and section headings correspond.
Paragraph prose may differ (translation, not literal), but the section
skeleton must match so a reader of either language sees the same
structure. Command blocks and tables must exist in both.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

REPO = HERE.parent.parent

# Documents that are intentionally English-only (audit trail, generated
# schema, post-mortems and notes are historical records; i18n READMEs are
# index files, not content).
ENGLISH_ONLY = {
    "HARNESS_IMPLEMENTATION_BRIEF.md",
    "HARNESS_EVALUATION_AND_IMPROVEMENTS.md",
    "HARNESS_SECOND_REVIEW.md",
    "HARNESS_THIRD_REVIEW.md",
    "HARNESS_FOURTH_REVIEW.md",
    "HARNESS_FIFTH_REVIEW.md",
    "HARNESS_SIXTH_REVIEW.md",
    "HARNESS_CURRENT_CHANGE_QUALITY_EVALUATION.md",
    "THIRD_PARTY_NOTICES.md",
}

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def _headings(text: str) -> list[int]:
    """Heading levels in document order (structure fingerprint)."""
    return [len(m.group(1)) for m in HEADING_RE.finditer(text)]


def _has_commands(text: str) -> bool:
    return "```" in text or "`agent-harness" in text or "./agent-harness" in text


class BilingualPairTests(unittest.TestCase):
    def _pairs(self) -> list[tuple[Path, Path]]:
        pairs = []
        for en in sorted(REPO.glob("*.md")):
            if en.name in ENGLISH_ONLY:
                continue
            zh = en.with_name(en.stem + ".zh.md")
            if zh.exists():
                pairs.append((en, zh))
        return pairs

    def test_expected_pairs_exist(self) -> None:
        pairs = {en.name for en, _ in self._pairs()}
        self.assertIn("README.md", pairs)
        self.assertIn("CONTRIBUTING.md", pairs)

    def test_every_pair_has_matching_heading_structure(self) -> None:
        for en, zh in self._pairs():
            with self.subTest(pair=f"{en.name}/{zh.name}"):
                self.assertEqual(
                    _headings(en.read_text(encoding="utf-8")),
                    _headings(zh.read_text(encoding="utf-8")),
                    f"heading structure drifted between {en.name} and {zh.name}; "
                    f"update both in the same PR",
                )

    def test_command_presence_matches(self) -> None:
        for en, zh in self._pairs():
            with self.subTest(pair=f"{en.name}/{zh.name}"):
                self.assertEqual(
                    _has_commands(en.read_text(encoding="utf-8")),
                    _has_commands(zh.read_text(encoding="utf-8")),
                    f"one side of {en.name}/{zh.name} has command blocks the other lacks",
                )

    def test_english_only_docs_have_no_orphan_chinese_twin(self) -> None:
        for en in sorted(REPO.glob("*.zh.md")):
            base = en.with_name(en.name.replace(".zh.md", ".md"))
            self.assertTrue(
                base.exists(),
                f"{en.name} exists but its English base {base.name} does not",
            )

    def test_readme_links_to_chinese(self) -> None:
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        self.assertIn("README.zh.md", readme)
        readme_zh = (REPO / "README.zh.md").read_text(encoding="utf-8")
        self.assertIn("README.md", readme_zh)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
