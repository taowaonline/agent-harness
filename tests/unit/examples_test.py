"""Tests that every shipped example and profile config is loadable."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_harness.config import ConfigError, load_config  # noqa: E402


REPO = HERE.parent.parent


class ExampleConfigTests(unittest.TestCase):
    def _check(self, rel_path: str) -> None:
        p = REPO / rel_path
        self.assertTrue(
            p.exists(),
            f"example config missing: {rel_path}",
        )
        # load_config resolves dataset paths relative to cwd, not the config
        # file. Run from the example's directory so relative dataset paths
        # resolve correctly.
        import os

        cwd = os.getcwd()
        try:
            os.chdir(p.parent)
            load_config(p.name)
        except ConfigError as e:
            self.fail(f"{rel_path} failed to load: {e}")
        finally:
            os.chdir(cwd)

    def test_python_rag(self) -> None:
        self._check("examples/python-rag/harness.toml")

    def test_typescript_agent(self) -> None:
        self._check("examples/typescript-agent/harness.toml")

    def test_go_ai_api(self) -> None:
        self._check("examples/go-ai-api/harness.toml")

    def test_rust_extraction(self) -> None:
        self._check("examples/rust-extraction/harness.toml")


class ProfileTests(unittest.TestCase):
    """Profiles are partial TOML snippets, not standalone configs — we
    just verify they parse without raising and contain expected sections."""

    def _parse_snippet(self, rel_path: str) -> dict:
        import tomllib

        p = REPO / rel_path
        self.assertTrue(p.exists(), f"profile missing: {rel_path}")
        with p.open("rb") as f:
            return tomllib.load(f)

    def test_language_profiles_exist(self) -> None:
        for lang in ("python", "typescript", "go", "rust", "jvm", "dotnet"):
            data = self._parse_snippet(f"profiles/languages/{lang}.toml")
            self.assertIn("commands", data, lang)

    def test_workload_profiles_exist(self) -> None:
        for wl in ("chat", "rag", "agent", "extraction"):
            data = self._parse_snippet(f"profiles/workloads/{wl}.toml")
            self.assertIn("evals", data, wl)

    def test_risk_profiles_exist(self) -> None:
        for risk in ("prototype", "standard", "high-risk"):
            data = self._parse_snippet(f"profiles/risk/{risk}.toml")
            self.assertIn("security", data, risk)


class RepoSelfConfigTest(unittest.TestCase):
    def test_repo_config_loads(self) -> None:
        import os

        cwd = os.getcwd()
        try:
            os.chdir(REPO)
            cfg = load_config("harness.toml")
        except ConfigError as e:
            self.fail(f"repo harness.toml failed: {e}")
        finally:
            os.chdir(cwd)
        self.assertEqual(cfg.project.language, "python")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
