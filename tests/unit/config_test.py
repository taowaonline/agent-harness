"""Unit tests for ai_harness.config."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

# Make src/ importable when running tests directly.
HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_harness.config import (  # noqa: E402
    ConfigError,
    load_config,
)

VALID_TOML = """
version = 1

[project]
name = "demo"
language = "python"
workload = "rag"
risk = "standard"

[commands]
lint = [["python3", "-m", "py_compile", "src"]]
test-unit = [["python3", "-m", "unittest"]]

[workflows]
check = ["lint", "test-unit"]
nested = ["check"]

[evals.smoke]
dataset = "evals/datasets/smoke.jsonl"
min_pass_rate = 0.9

[evals.full]
dataset = "evals/datasets/full.jsonl"
repetitions = 3

[security]
redact_inputs = true
tool_allowlist = ["search", "retrieve"]
require_approval_for = ["external_write", "delete"]
"""


def _write(tmpdir: Path, content: str, name: str = "harness.toml") -> Path:
    p = tmpdir / name
    p.write_text(content, encoding="utf-8")
    return p


class ConfigLoadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_load_valid_config(self) -> None:
        p = _write(self.dir, VALID_TOML)
        cfg = load_config(p)
        self.assertEqual(cfg.version, 1)
        self.assertEqual(cfg.project.name, "demo")
        self.assertEqual(cfg.project.language, "python")
        self.assertEqual(cfg.project.workload, "rag")
        self.assertEqual(cfg.commands["lint"], [["python3", "-m", "py_compile", "src"]])
        self.assertEqual(cfg.workflows["check"], ["lint", "test-unit"])
        self.assertIn("smoke", cfg.evals)
        self.assertEqual(cfg.evals["smoke"].min_pass_rate, 0.9)
        self.assertEqual(cfg.evals["full"].repetitions, 3)
        self.assertEqual(cfg.security.tool_allowlist, ["search", "retrieve"])

    def test_missing_version_rejected(self) -> None:
        p = _write(self.dir, '[project]\nname = "x"\n')
        with self.assertRaises(ConfigError):
            load_config(p)

    def test_unknown_version_rejected(self) -> None:
        p = _write(
            self.dir,
            'version = 99\n[project]\nname = "x"\nlanguage = "python"\n',
        )
        with self.assertRaises(ConfigError) as cm:
            load_config(p)
        self.assertIn("Unsupported config version", str(cm.exception))

    def test_unknown_top_level_field_rejected(self) -> None:
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\n[mystery]\nfoo = "bar"\n',
        )
        with self.assertRaises(ConfigError) as cm:
            load_config(p)
        self.assertIn("Unknown top-level fields", str(cm.exception))

    def test_unknown_project_field_rejected(self) -> None:
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\nmystery = true\n',
        )
        with self.assertRaises(ConfigError) as cm:
            load_config(p)
        self.assertIn("Unknown [project] fields", str(cm.exception))

    def test_unknown_security_field_rejected(self) -> None:
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\n'
            "[security]\nbackdoor = true\n",
        )
        with self.assertRaises(ConfigError) as cm:
            load_config(p)
        self.assertIn("unknown fields", str(cm.exception))

    def test_unknown_approval_kind_rejected(self) -> None:
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\n'
            '[security]\nrequire_approval_for = ["nuke"]\n',
        )
        with self.assertRaises(ConfigError):
            load_config(p)

    def test_argv_must_be_strings(self) -> None:
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\n'
            '[commands]\nlint = [["echo", 42]]\n',
        )
        with self.assertRaises(ConfigError) as cm:
            load_config(p)
        self.assertIn("argv must contain only strings", str(cm.exception))

    def test_empty_argv_entry_rejected(self) -> None:
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\n[commands]\nlint = [[]]\n',
        )
        with self.assertRaises(ConfigError):
            load_config(p)

    def test_empty_argv_list_allowed_as_skipped(self) -> None:
        # typecheck = [] means "configured but no commands" — runner skips it.
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\n[commands]\ntypecheck = []\n',
        )
        cfg = load_config(p)
        self.assertEqual(cfg.commands["typecheck"], [])

    def test_cycle_direct_rejected(self) -> None:
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\n'
            '[workflows]\nloop = ["loop"]\n',
        )
        with self.assertRaises(ConfigError) as cm:
            load_config(p)
        self.assertIn("references itself", str(cm.exception))

    def test_cycle_transitive_rejected(self) -> None:
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\n'
            '[workflows]\na = ["b"]\nb = ["c"]\nc = ["a"]\n',
        )
        with self.assertRaises(ConfigError) as cm:
            load_config(p)
        self.assertIn("cycle detected", str(cm.exception))

    def test_invalid_toml_rejected(self) -> None:
        p = _write(self.dir, "this is = = not toml\n")
        with self.assertRaises(ConfigError) as cm:
            load_config(p)
        self.assertIn("TOML parse error", str(cm.exception))

    def test_missing_file(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(self.dir / "does-not-exist.toml")

    def test_unknown_eval_kind_rejected(self) -> None:
        p = _write(
            self.dir,
            'version = 1\n[project]\nname = "x"\nlanguage = "python"\n'
            '[evals.experimental]\ndataset = "x.jsonl"\n',
        )
        with self.assertRaises(ConfigError) as cm:
            load_config(p)
        self.assertIn("only 'smoke' and 'full'", str(cm.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
