"""Unit tests for ai_harness.evals — datasets, graders, gates."""

from __future__ import annotations

import json
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
    EvalConfig,
    ProjectInfo,
    SecurityConfig,
)
from ai_harness.evals import (  # noqa: E402
    GRADER_REGISTRY,
    DatasetError,
    compare_reports,
    grader_contains,
    grader_exact,
    grader_json_field,
    grader_json_parse,
    grader_not_contains,
    grader_regex,
    grader_threshold,
    grader_tool_call,
    load_dataset,
    run_eval,
)
from ai_harness.result import (  # noqa: E402
    STATUS_FAILED,
    STATUS_PASSED,
    RunResult,
)


def _write_dataset(tmpdir: Path, lines: list[str], name: str = "x.jsonl") -> Path:
    p = tmpdir / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class DatasetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_load_valid_dataset(self) -> None:
        p = _write_dataset(
            self.dir,
            [
                json.dumps(
                    {
                        "id": "a",
                        "input": {"query": "q"},
                        "expected": {"contains": ["q"]},
                        "tags": ["smoke"],
                        "metadata": {"source": "synthetic"},
                    }
                ),
                json.dumps(
                    {
                        "id": "b",
                        "input": {"query": "r"},
                        "expected": {"contains": ["r"]},
                    }
                ),
            ],
        )
        cases = load_dataset(p)
        self.assertEqual(len(cases), 2)
        self.assertEqual(cases[0].id, "a")
        self.assertEqual(cases[0].tags, ["smoke"])
        self.assertEqual(cases[1].metadata, {})

    def test_load_skips_blank_and_comment_lines(self) -> None:
        p = _write_dataset(
            self.dir,
            [
                "",
                "# this is a comment",
                json.dumps({"id": "a", "input": {}, "expected": {}}),
            ],
        )
        cases = load_dataset(p)
        self.assertEqual(len(cases), 1)

    def test_duplicate_id_rejected(self) -> None:
        p = _write_dataset(
            self.dir,
            [
                json.dumps({"id": "x", "input": {}, "expected": {}}),
                json.dumps({"id": "x", "input": {}, "expected": {}}),
            ],
        )
        with self.assertRaises(DatasetError) as cm:
            load_dataset(p)
        self.assertIn("duplicate case id", str(cm.exception))

    def test_missing_required_field_rejected(self) -> None:
        p = _write_dataset(
            self.dir,
            [
                json.dumps({"id": "x", "input": {}}),  # no 'expected'
            ],
        )
        with self.assertRaises(DatasetError):
            load_dataset(p)

    def test_invalid_json_line_reports_lineno(self) -> None:
        p = _write_dataset(
            self.dir,
            [
                json.dumps({"id": "x", "input": {}, "expected": {}}),
                "{not json",
            ],
        )
        with self.assertRaises(DatasetError) as cm:
            load_dataset(p)
        # Line 2 should be named in the error.
        self.assertIn(":2:", str(cm.exception))

    def test_empty_dataset_rejected(self) -> None:
        p = _write_dataset(self.dir, ["", "# comment"])
        with self.assertRaises(DatasetError):
            load_dataset(p)

    def test_missing_file(self) -> None:
        with self.assertRaises(DatasetError):
            load_dataset(self.dir / "nope.jsonl")


class GraderTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        ok, _ = grader_exact({"exact": "yes"}, {"answer": "yes"})
        self.assertTrue(ok)
        ok, _ = grader_exact({"exact": "yes"}, {"answer": "no"})
        self.assertFalse(ok)

    def test_contains(self) -> None:
        ok, _ = grader_contains({"needle": "hello"}, {"answer": "hello world"})
        self.assertTrue(ok)
        ok, _ = grader_contains({"needle": "missing"}, {"answer": "hello world"})
        self.assertFalse(ok)

    def test_not_contains(self) -> None:
        ok, _ = grader_not_contains({"needle": "secret"}, {"answer": "hello world"})
        self.assertTrue(ok)
        ok, _ = grader_not_contains({"needle": "secret"}, {"answer": "top secret data"})
        self.assertFalse(ok)

    def test_regex(self) -> None:
        ok, _ = grader_regex({"pattern": r"\bAPI\b"}, {"answer": "use the API now"})
        self.assertTrue(ok)
        ok, _ = grader_regex({"pattern": r"\bZZZ\b"}, {"answer": "nothing"})
        self.assertFalse(ok)

    def test_json_parse(self) -> None:
        ok, _ = grader_json_parse({}, {"answer": '{"a": 1}'})
        self.assertTrue(ok)
        ok, _ = grader_json_parse({}, {"answer": "not json"})
        self.assertFalse(ok)

    def test_json_field(self) -> None:
        ok, _ = grader_json_field(
            {"field": "name", "equals": "Ada"},
            {"answer": '{"name": "Ada", "age": 30}'},
        )
        self.assertTrue(ok)
        ok, _ = grader_json_field(
            {"field": "name", "equals": "Ada"},
            {"answer": '{"name": "Grace"}'},
        )
        self.assertFalse(ok)
        ok, _ = grader_json_field(
            {"field": "missing", "equals": "x"},
            {"answer": '{"name": "Ada"}'},
        )
        self.assertFalse(ok)

    def test_tool_call_match_name_only(self) -> None:
        ok, _ = grader_tool_call(
            {"tool": "cancel_order"},
            {"tool_calls": [{"name": "cancel_order", "args": {}}]},
        )
        self.assertTrue(ok)

    def test_tool_call_match_with_args(self) -> None:
        ok, _ = grader_tool_call(
            {"tool": "cancel_order", "args": {"order_id": "1234"}},
            {"tool_calls": [{"name": "cancel_order", "args": {"order_id": "1234"}}]},
        )
        self.assertTrue(ok)
        ok, _ = grader_tool_call(
            {"tool": "cancel_order", "args": {"order_id": "1234"}},
            {"tool_calls": [{"name": "cancel_order", "args": {"order_id": "9999"}}]},
        )
        self.assertFalse(ok)

    def test_tool_call_missing(self) -> None:
        ok, _ = grader_tool_call(
            {"tool": "cancel_order"},
            {"tool_calls": [{"name": "refund", "args": {}}]},
        )
        self.assertFalse(ok)

    def test_threshold_pass(self) -> None:
        ok, _ = grader_threshold(
            {"metric": "latency_ms", "max": 500},
            {"metrics": {"latency_ms": 120}},
        )
        self.assertTrue(ok)

    def test_threshold_breach(self) -> None:
        ok, _ = grader_threshold(
            {"metric": "latency_ms", "max": 500},
            {"metrics": {"latency_ms": 800}},
        )
        self.assertFalse(ok)

    def test_all_graders_registered(self) -> None:
        for name in [
            "exact",
            "contains",
            "not_contains",
            "regex",
            "json_parse",
            "json_field",
            "tool_call",
            "threshold",
        ]:
            self.assertIn(name, GRADER_REGISTRY)


class RunEvalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        import os

        self._cwd = os.getcwd()
        os.chdir(self.dir)

    def tearDown(self) -> None:
        import os

        os.chdir(self._cwd)

    def _cfg_with_dataset(
        self,
        dataset_text: str,
        *,
        min_pass_rate: float = 0.9,
        name: str = "smoke",
    ) -> Config:
        p = self.dir / "ds.jsonl"
        p.write_text(dataset_text, encoding="utf-8")
        return Config(
            version=1,
            project=ProjectInfo(name="t", language="python"),
            commands={},
            workflows={},
            evals={name: EvalConfig(dataset=str(p), min_pass_rate=min_pass_rate)},
            security=SecurityConfig(),
        )

    def test_offline_eval_passes_when_fixtures_present(self) -> None:
        cfg = self._cfg_with_dataset(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "a",
                            "input": {"output": {"answer": "hello"}},
                            "expected": {"contains": ["hello"]},
                        }
                    ),
                    json.dumps(
                        {
                            "id": "b",
                            "input": {"output": {"answer": "world"}},
                            "expected": {"contains": ["world"]},
                        }
                    ),
                ]
            )
        )
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_PASSED)
        self.assertEqual(stage.metrics["summary"]["passed"], 2)
        self.assertEqual(stage.metrics["summary"]["failed"], 0)

    def test_offline_eval_fails_threshold(self) -> None:
        cfg = self._cfg_with_dataset(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "a",
                            "input": {"output": {"answer": "right"}},
                            "expected": {"contains": ["right"]},
                        }
                    ),
                    json.dumps(
                        {
                            "id": "b",
                            "input": {"output": {"answer": "wrong"}},
                            "expected": {"contains": ["right"]},
                        }
                    ),
                ]
            ),
            min_pass_rate=0.99,
        )
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        self.assertEqual(stage.status, STATUS_FAILED)

    def test_offline_eval_skips_case_without_fixture(self) -> None:
        cfg = self._cfg_with_dataset(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "a",
                            "input": {},  # no fixture output
                            "expected": {"contains": ["anything"]},
                        }
                    ),
                ]
            ),
            min_pass_rate=0.0,
        )
        result = RunResult(command="eval")
        stage = run_eval(cfg, "smoke", result, offline=True)
        # No fixture => case skipped, no graded cases => pass_rate 0 but
        # zero graded means status stays passed (no failures).
        self.assertEqual(stage.metrics["summary"]["skipped"], 1)

    def test_persist_report_does_not_leak_secrets(self) -> None:
        # A fixture that *contains* a fake secret must not appear verbatim
        # in the persisted report — outputs are never written to disk by
        # the offline runner.
        cfg = self._cfg_with_dataset(
            "\n".join(
                [
                    json.dumps(
                        {
                            "id": "a",
                            "input": {"output": {"answer": "Bearer eyJhbc.def.ghijklmno.secret"}},
                            "expected": {"contains": ["Bearer"]},
                        }
                    ),
                ]
            ),
            min_pass_rate=0.0,
        )
        result = RunResult(command="eval")
        run_eval(cfg, "smoke", result, offline=True)
        reports = list((self.dir / "evals" / "reports").glob("*.json"))
        self.assertEqual(len(reports), 1)
        text = reports[0].read_text()
        # The raw output is never included in case rows.
        self.assertNotIn("Bearer eyJhbc", text)
        self.assertNotIn("ghijklmno.secret", text)


class CompareReportsTests(unittest.TestCase):
    def test_compare_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a = d / "a.json"
            b = d / "b.json"
            payload = {"summary": {"pass_rate": 0.9}}
            a.write_text(json.dumps(payload))
            b.write_text(json.dumps(payload))
            delta = compare_reports(str(a), str(b))
            self.assertEqual(delta["verdict"], "unchanged")
            self.assertEqual(delta["pass_rate_delta"], 0.0)

    def test_compare_regression(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            a = d / "a.json"
            b = d / "b.json"
            a.write_text(json.dumps({"summary": {"pass_rate": 0.95}}))
            b.write_text(json.dumps({"summary": {"pass_rate": 0.85}}))
            delta = compare_reports(str(a), str(b))
            self.assertEqual(delta["verdict"], "regressed")
            self.assertAlmostEqual(delta["regression"], 0.10, places=2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
