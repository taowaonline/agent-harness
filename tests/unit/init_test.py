"""Unit tests for `harness init`."""

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

from agent_harness.cli import (  # noqa: E402
    _dataset_paths_in_toml,
    _localize_dataset_paths,
    _override_toml_field,
    _render_init_toml,
)
from agent_harness.config import load_config  # noqa: E402

REPO = HERE.parent.parent


class RenderTests(unittest.TestCase):
    def test_synthesize_minimal(self) -> None:
        text = _render_init_toml(
            name="demo",
            language="python",
            workload="rag",
            risk="standard",
            home=REPO,
        )
        # Should use the python-rag example (exact match).
        self.assertIn('name = "demo"', text)
        self.assertIn('language = "python"', text)
        self.assertIn('risk = "standard"', text)

    def test_synthesize_falls_back_to_table(self) -> None:
        # No exact example for jvm+chat; should synthesize from the table.
        text = _render_init_toml(
            name="jvmchat",
            language="jvm",
            workload="chat",
            risk="high-risk",
            home=REPO,
        )
        self.assertIn('name = "jvmchat"', text)
        self.assertIn('language = "jvm"', text)
        self.assertIn('risk = "high-risk"', text)
        # Spot-check a jvm-specific command.
        self.assertIn("gradlew", text)

    def test_multi_argv_stage(self) -> None:
        text = _render_init_toml(
            name="demo",
            language="go",
            workload="other",
            risk="standard",
            home=REPO,
        )
        # Go typecheck has two argv arrays.
        self.assertIn('typecheck = [["go", "vet"', text)


class PathRewriteTests(unittest.TestCase):
    def test_localize_dataset_paths(self) -> None:
        text = '[evals.smoke]\ndataset = "../../evals/datasets/smoke.example.jsonl"\n'
        out = _localize_dataset_paths(text)
        self.assertIn('dataset = "evals/datasets/smoke.example.jsonl"', out)

    def test_localize_idempotent(self) -> None:
        text = '[evals.smoke]\ndataset = "evals/datasets/x.jsonl"\n'
        self.assertEqual(_localize_dataset_paths(text), text)

    def test_extract_dataset_paths(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "harness.toml"
            p.write_text(
                '[evals.smoke]\ndataset = "a/b.jsonl"\n[evals.full]\ndataset = "c/d.jsonl"\n'
            )
            paths = _dataset_paths_in_toml(p)
            self.assertEqual(paths, ["a/b.jsonl", "c/d.jsonl"])


class OverrideFieldTests(unittest.TestCase):
    def test_override_name(self) -> None:
        text = '[project]\nname = "old"\nlanguage = "python"\n'
        out = _override_toml_field(text, "name", "new", section="project")
        self.assertIn('name = "new"', out)
        self.assertNotIn('name = "old"', out)
        # Other fields untouched.
        self.assertIn('language = "python"', out)

    def test_override_only_in_section(self) -> None:
        # A field with the same name outside the target section is left alone.
        text = '[project]\nname = "old"\n\n[other]\nname = "keepme"\n'
        out = _override_toml_field(text, "name", "new", section="project")
        self.assertIn('name = "new"', out)
        self.assertIn('name = "keepme"', out)


class EndToEndInitTests(unittest.TestCase):
    """Run `harness init` end-to-end in a tempdir, then validate."""

    def _run_init(self, cwd: Path, *args: str) -> int:
        from agent_harness.cli import main

        old = os.getcwd()
        os.chdir(cwd)
        try:
            return main(["init", *args])
        finally:
            os.chdir(old)

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_init_python_rag_then_validate(self) -> None:
        rc = self._run_init(
            self.dir,
            "--language",
            "python",
            "--workload",
            "rag",
            "--risk",
            "standard",
            "--name",
            "demo",
        )
        self.assertEqual(rc, 0)
        # Generated layout.
        self.assertTrue((self.dir / "agent-harness").exists())
        self.assertTrue((self.dir / "harness.toml").exists())
        self.assertTrue((self.dir / "harness.schema.json").exists())
        self.assertTrue((self.dir / "evals/datasets/smoke.example.jsonl").exists())
        # Generated config is loadable from the project dir.
        old = os.getcwd()
        os.chdir(self.dir)
        try:
            cfg = load_config("harness.toml")
        finally:
            os.chdir(old)
        self.assertEqual(cfg.project.name, "demo")
        self.assertEqual(cfg.project.risk, "standard")

    def test_init_refuses_overwrite_without_force(self) -> None:
        # First init succeeds.
        self._run_init(self.dir, "--language", "python")
        # Second init without --force fails.
        rc = self._run_init(self.dir, "--language", "python")
        self.assertNotEqual(rc, 0)
        # Third with --force succeeds.
        rc = self._run_init(self.dir, "--language", "python", "--force")
        self.assertEqual(rc, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
