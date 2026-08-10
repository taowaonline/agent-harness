"""Tests for config-relative path resolution (HARNESS_FIFTH_REVIEW §八 11)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_harness.config import load_config  # noqa: E402
from ai_harness.evals import load_dataset  # noqa: E402


class ProjectRootResolutionTests(unittest.TestCase):
    """Relative dataset paths resolve against config dir, not process cwd."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        # Build a project layout:
        #   <dir>/proj/harness.toml
        #   <dir>/proj/evals/datasets/smoke.jsonl
        self.proj = self.dir / "proj"
        (self.proj / "evals" / "datasets").mkdir(parents=True)
        toml = """
version = 1
[project]
name = "p"
language = "python"
[evals.smoke]
dataset = "evals/datasets/smoke.jsonl"
"""
        (self.proj / "harness.toml").write_text(toml, encoding="utf-8")
        ds = '{"id":"a","input":{"query":"x"},"expected":{"contains":["x"]}}\n'
        (self.proj / "evals" / "datasets" / "smoke.jsonl").write_text(ds, encoding="utf-8")

    def test_load_config_sets_project_root(self) -> None:
        cfg = load_config(self.proj / "harness.toml")
        self.assertEqual(cfg.project_root, self.proj)

    def test_dataset_resolves_via_project_root_from_any_cwd(self) -> None:
        cwd = os.getcwd()
        try:
            # cd to /tmp — totally unrelated to the project
            os.chdir("/tmp")
            cfg = load_config(self.proj / "harness.toml")
            # Must NOT raise "Dataset not found"
            cases = load_dataset(
                cfg.evals["smoke"].dataset,
                project_root=cfg.project_root,
            )
            self.assertEqual(len(cases), 1)
        finally:
            os.chdir(cwd)

    def test_validate_via_cli_from_foreign_cwd(self) -> None:
        """Black-box: `harness validate --config <abs>` from /tmp must pass."""
        repo_root = HERE.parent.parent
        env = dict(os.environ)
        # Ensure the harness script can find ai_harness (adjacent src/)
        proc = subprocess.run(
            [
                "python3",
                str(repo_root / "harness"),
                "validate",
                "--config",
                str(self.proj / "harness.toml"),
                "--json",
            ],
            capture_output=True,
            text=True,
            cwd="/tmp",
            env=env,
            timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual(data["status"], "passed")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
