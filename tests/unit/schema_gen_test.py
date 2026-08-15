"""Tests for schema generation and the gen/verify pair.

The schema is generated from config.py's authoritative sets, so parser
and schema cannot drift silently (the class of bug SECOND_REVIEW P1.4
documented). verify-schema is the CI gate; gen-schema is the fix.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_harness import config as C  # noqa: E402
from agent_harness.schema_gen import build_schema, render_schema  # noqa: E402

REPO = HERE.parent.parent


class GeneratedSchemaContentTests(unittest.TestCase):
    """The generated schema reflects config.py's real allowed sets."""

    def test_top_level_keys_match_allowed(self) -> None:
        schema = build_schema()
        self.assertEqual(set(schema["properties"].keys()), set(C._ALLOWED_TOP))

    def test_project_fields_match_allowed(self) -> None:
        schema = build_schema()
        self.assertEqual(
            set(schema["properties"]["project"]["properties"].keys()),
            set(C._ALLOWED_PROJECT),
        )

    def test_security_fields_match_allowed(self) -> None:
        schema = build_schema()
        self.assertEqual(
            set(schema["properties"]["security"]["properties"].keys()),
            set(C._ALLOWED_SECURITY),
        )

    def test_eval_fields_match_allowed(self) -> None:
        schema = build_schema()
        eval_props = set(schema["$defs"]["evalConfig"]["properties"].keys())
        self.assertEqual(eval_props, set(C._ALLOWED_EVAL_KEYS))

    def test_language_enum_matches_parser(self) -> None:
        schema = build_schema()
        enum = schema["properties"]["project"]["properties"]["language"]["enum"]
        self.assertEqual(set(enum), set(C._ALLOWED_LANGUAGES))

    def test_workload_enum_matches_parser(self) -> None:
        schema = build_schema()
        enum = schema["properties"]["project"]["properties"]["workload"]["enum"]
        self.assertEqual(set(enum), set(C._ALLOWED_WORKLOADS))

    def test_risk_enum_matches_parser(self) -> None:
        schema = build_schema()
        enum = schema["properties"]["project"]["properties"]["risk"]["enum"]
        self.assertEqual(set(enum), set(C._ALLOWED_RISKS))

    def test_approval_enum_matches_parser(self) -> None:
        schema = build_schema()
        enum = schema["properties"]["security"]["properties"]["require_approval_for"]["items"][
            "enum"
        ]
        self.assertEqual(set(enum), set(C._ALLOWED_APPROVAL))

    def test_version_enum_matches_supported(self) -> None:
        schema = build_schema()
        enum = schema["properties"]["version"]["enum"]
        self.assertEqual(set(enum), set(C.SUPPORTED_CONFIG_VERSIONS))

    def test_commands_allows_empty_array(self) -> None:
        # The P1.4 regression: parser accepts typecheck = [], schema must too.
        schema = build_schema()
        cmds = schema["properties"]["commands"]["additionalProperties"]
        self.assertNotIn("minItems", cmds)

    def test_render_is_valid_json_and_stable(self) -> None:
        text = render_schema()
        parsed = json.loads(text)
        self.assertEqual(parsed, build_schema())
        self.assertEqual(render_schema(), text)  # deterministic


class CheckedInSchemaSyncTests(unittest.TestCase):
    """The committed harness.schema.json equals the generated one."""

    def test_checked_in_schema_is_in_sync(self) -> None:
        checked_in = (REPO / "harness.schema.json").read_text(encoding="utf-8")
        self.assertEqual(
            checked_in,
            render_schema(),
            "harness.schema.json drifted from config.py — "
            "run `agent_harness gen-schema` to regenerate",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
