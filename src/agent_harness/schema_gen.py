"""Generate harness.schema.json from config.py's authoritative sets.

The schema and the parser previously drifted (SECOND_REVIEW P1.4: schema
demanded minItems on commands while the parser accepted empty arrays as
"explicitly not configured"). This module makes config.py the single
source of truth: `gen-schema` writes the JSON, `verify-schema --check`
diffs it in CI. The generator reads the same module-level constants the
parser validates against, so a new allowed key cannot exist in one and
not the other.

Regenerate rather than reject (dsh lefthook philosophy): if drift ever
appears, the fix is `agent-harness gen-schema`, not hand-editing JSON.
"""

from __future__ import annotations

import json
from typing import Any

from . import config as C


def build_schema() -> dict[str, Any]:
    """Build the schema dict deterministically from config.py constants."""
    langs = sorted(_strip_default_other(C._ALLOWED_LANGUAGES))
    workloads = sorted(_strip_default_other(C._ALLOWED_WORKLOADS))
    risks = sorted(C._ALLOWED_RISKS)
    approvals = sorted(C._ALLOWED_APPROVAL)
    eval_keys = sorted(C._ALLOWED_EVAL_KEYS)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://agent-harness.local/harness.schema.json",
        "title": "Harness configuration",
        "type": "object",
        "required": ["version", "project"],
        "additionalProperties": False,
        "properties": {
            "version": {
                "type": "integer",
                "description": "Major config version. Unknown majors are rejected.",
                "enum": list(C.SUPPORTED_CONFIG_VERSIONS),
            },
            "extends": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Profile refs to load and merge before this config. "
                    "Format: 'languages.python', 'workloads.rag', "
                    "'risk.standard'. Order = base-first; project fields "
                    "always win."
                ),
            },
            "project": {
                "type": "object",
                "required": ["name", "language"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "language": {"type": "string", "enum": langs},
                    "workload": {"type": "string", "enum": workloads},
                    "risk": {"type": "string", "enum": risks},
                },
            },
            "commands": {
                "type": "object",
                "description": (
                    "Map of stable stage name to one or more argv arrays. An "
                    "empty array means 'explicitly no command' (the runner "
                    "reports this stage as skipped with reason 'not "
                    "configured')."
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                },
            },
            "workflows": {
                "type": "object",
                "description": (
                    "Map of workflow name to an ordered list of stage or workflow names."
                ),
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "evals": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "smoke": {"$ref": "#/$defs/evalConfig"},
                    "full": {"$ref": "#/$defs/evalConfig"},
                },
            },
            "security": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "redact_inputs": {"type": "boolean"},
                    "redact_outputs": {"type": "boolean"},
                    "tool_allowlist": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "require_approval_for": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": approvals,
                        },
                    },
                    "scan_exclude": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Glob patterns (fnmatch) for files/dirs the "
                            "secret-scan should skip. Matched against path "
                            "relative to project root with forward slashes. "
                            "Use for vendored dictionaries, generated code, "
                            "etc."
                        ),
                    },
                },
            },
        },
        "$defs": {
            "evalConfig": {
                "type": "object",
                "required": ["dataset"],
                "additionalProperties": False,
                "properties": {
                    **{key: _eval_field_schema(key) for key in eval_keys if key != "runner"},
                    "runner": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": (
                            "Optional argv for a subprocess runner that "
                            "consumes Case JSON on stdin and produces "
                            "Result JSON on stdout."
                        ),
                    },
                },
            },
        },
    }


def _strip_default_other(values: set[str]) -> set[str]:
    """'other' is the explicit fallback enum member; keep it in the enum."""
    return set(values)


def _eval_field_schema(key: str) -> dict[str, Any]:
    integer_fields = {
        "sample_limit": ("minimum", 1),
        "timeout_seconds": ("minimum", 1),
        "repetitions": ("minimum", 1),
    }
    zero_one_fields = {"min_pass_rate", "max_regression"}
    if key in integer_fields:
        _, minimum = integer_fields[key]
        return {"type": "integer", "minimum": minimum}
    if key == "max_cost_usd":
        return {"type": "number", "minimum": 0}
    if key in zero_one_fields:
        return {"type": "number", "minimum": 0, "maximum": 1}
    if key == "enforce_max_cost":
        return {
            "type": "boolean",
            "default": False,
            "description": (
                "If true, treat max_cost_usd as a hard gate: the runner "
                "must emit cost_usd per case; over-budget → stage FAILED. "
                "Default false (advisory only — no provider price table "
                "is bundled)."
            ),
        }
    # dataset
    return {"type": "string"}


def render_schema() -> str:
    """Render the schema as canonical JSON text (stable key order)."""
    return json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"


__all__ = ["build_schema", "render_schema"]
