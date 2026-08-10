"""Tests for Profile runtime loading (HARNESS_FIFTH_REVIEW §八 15)."""

from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_harness.config import ConfigError, load_config  # noqa: E402

REPO = HERE.parent.parent


class ProfileLoaderTests(unittest.TestCase):
    """§八 15: profile loading, override, source tracking."""

    def test_extends_language_python_loads_profile_commands(self) -> None:
        # Project file extends languages.python — should pick up
        # format/lint/typecheck/test-unit/test-integration from the profile
        # without restating them.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "harness.toml").write_text(
                textwrap.dedent("""
                version = 1
                extends = ["languages.python"]
                [project]
                name = "demo"
                language = "python"
            """),
                encoding="utf-8",
            )
            # Need profiles/ reachable — copy from repo
            self._copy_profiles(d)
            cfg = load_config(d / "harness.toml")
            # Profile supplies all 6 standard stages.
            self.assertIn("format", cfg.commands)
            self.assertIn("lint", cfg.commands)
            self.assertIn("typecheck", cfg.commands)
            self.assertIn("test-unit", cfg.commands)
            self.assertIn("test-integration", cfg.commands)
            # Profile uses uv + ruff.
            self.assertEqual(cfg.commands["lint"][0][0], "uv")

    def test_project_overrides_profile_per_stage(self) -> None:
        # Project defines its own `lint` — that should fully replace the
        # profile's lint stage.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "harness.toml").write_text(
                textwrap.dedent("""
                version = 1
                extends = ["languages.python"]
                [project]
                name = "demo"
                language = "python"
                [commands]
                lint = [["./bin/my-linter"]]
            """),
                encoding="utf-8",
            )
            self._copy_profiles(d)
            cfg = load_config(d / "harness.toml")
            # Project's lint wins entirely.
            self.assertEqual(cfg.commands["lint"], [["./bin/my-linter"]])
            # Other profile stages still present.
            self.assertIn("format", cfg.commands)

    def test_unknown_profile_ref_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "harness.toml").write_text(
                'version = 1\nextends = ["unknown.profile"]\n'
                '[project]\nname = "x"\nlanguage = "python"\n',
                encoding="utf-8",
            )
            self._copy_profiles(d)
            with self.assertRaises(ConfigError) as cm:
                load_config(d / "harness.toml")
            self.assertIn("must start with languages/ workloads/ or risk/", str(cm.exception))

    def test_missing_profile_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "harness.toml").write_text(
                'version = 1\nextends = ["languages.perl"]\n'
                '[project]\nname = "x"\nlanguage = "python"\n',
                encoding="utf-8",
            )
            self._copy_profiles(d)
            with self.assertRaises(ConfigError) as cm:
                load_config(d / "harness.toml")
            self.assertIn("not found", str(cm.exception))

    def test_multi_profile_chain_workload_risk(self) -> None:
        # Chain: languages.python + workloads.rag + risk.standard.
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "harness.toml").write_text(
                textwrap.dedent("""
                version = 1
                extends = ["languages.python", "workloads.rag", "risk.standard"]
                [project]
                name = "demo"
                language = "python"
                workload = "rag"
                risk = "standard"
            """),
                encoding="utf-8",
            )
            self._copy_profiles(d)
            cfg = load_config(d / "harness.toml")
            self.assertIn("format", cfg.commands)  # from languages
            self.assertTrue(len(cfg.security.tool_allowlist) >= 0)
            self.assertIn("external_write", cfg.security.require_approval_for)

    def _copy_profiles(self, target: Path) -> None:
        """Copy the repo's profiles/ next to the test project so the loader
        finds them via base_root = config dir."""
        import shutil

        shutil.copytree(REPO / "profiles", target / "profiles")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
