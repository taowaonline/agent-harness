"""Configuration loading and validation.

`harness.toml` is the source of truth. We validate against the schema
contract documented in `harness.schema.json` and reject unknown major
versions.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .result import STATUS_SKIPPED

SUPPORTED_CONFIG_VERSIONS = (1,)
DEFAULT_CONFIG_PATH = "harness.toml"


class ConfigError(Exception):
    """Raised when the harness configuration is invalid."""


@dataclass
class ProjectInfo:
    name: str
    language: str = "other"
    workload: str = "other"
    risk: str = "standard"


@dataclass
class EvalConfig:
    dataset: str
    sample_limit: int | None = None
    timeout_seconds: int | None = None
    max_cost_usd: float | None = None
    min_pass_rate: float | None = None
    repetitions: int = 1
    max_regression: float | None = None


@dataclass
class SecurityConfig:
    redact_inputs: bool = True
    redact_outputs: bool = True
    tool_allowlist: list[str] = field(default_factory=list)
    require_approval_for: list[str] = field(default_factory=list)


@dataclass
class Config:
    version: int
    project: ProjectInfo
    commands: dict[str, list[list[str]]] = field(default_factory=dict)
    workflows: dict[str, list[str]] = field(default_factory=dict)
    evals: dict[str, EvalConfig] = field(default_factory=dict)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    source_path: str | None = None
    unknown_fields: list[str] = field(default_factory=list)


# Top-level keys allowed in harness.toml. Unknown keys => validation error.
_ALLOWED_TOP = {"version", "project", "commands", "workflows", "evals", "security"}
_ALLOWED_PROJECT = {"name", "language", "workload", "risk"}
_ALLOWED_SECURITY = {
    "redact_inputs",
    "redact_outputs",
    "tool_allowlist",
    "require_approval_for",
}
_ALLOWED_EVAL_KEYS = {
    "dataset",
    "sample_limit",
    "timeout_seconds",
    "max_cost_usd",
    "min_pass_rate",
    "repetitions",
    "max_regression",
}
_ALLOWED_LANGUAGES = {"python", "typescript", "go", "rust", "jvm", "dotnet", "other"}
_ALLOWED_WORKLOADS = {
    "chat",
    "rag",
    "agent",
    "extraction",
    "code-agent",
    "other",
}
_ALLOWED_RISKS = {"prototype", "standard", "high-risk"}
_ALLOWED_APPROVAL = {
    "external_write",
    "delete",
    "payment",
    "deploy",
    "network_egress",
    "privileged",
}


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    """Load and validate harness.toml. Raises ConfigError on any issue."""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with p.open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"TOML parse error in {path}: {e}") from e
    return _build_config(raw, source_path=str(path))


def _build_config(raw: dict[str, Any], source_path: str | None = None) -> Config:
    unknown = [k for k in raw if k not in _ALLOWED_TOP]
    if unknown:
        raise ConfigError(
            f"Unknown top-level fields: {sorted(unknown)}. "
            f"Allowed: {sorted(_ALLOWED_TOP)}."
        )

    if "version" not in raw:
        raise ConfigError("Missing required field: version")
    version = raw["version"]
    if not isinstance(version, int):
        raise ConfigError(f"version must be an integer, got {type(version).__name__}")
    if version not in SUPPORTED_CONFIG_VERSIONS:
        raise ConfigError(
            f"Unsupported config version {version}. "
            f"Supported major versions: {SUPPORTED_CONFIG_VERSIONS}."
        )

    if "project" not in raw:
        raise ConfigError("Missing required section: [project]")
    project = _build_project(raw["project"])

    commands = _build_commands(raw.get("commands", {}))
    workflows = raw.get("workflows", {})
    if not isinstance(workflows, dict):
        raise ConfigError("[workflows] must be a table")
    for name, seq in workflows.items():
        if not isinstance(seq, list) or not all(isinstance(x, str) for x in seq):
            raise ConfigError(
                f"workflow '{name}' must be a list of stage/workflow names"
            )
    _detect_cycles(workflows)

    evals = _build_evals(raw.get("evals", {}))
    security = _build_security(raw.get("security", {}))

    cfg = Config(
        version=version,
        project=project,
        commands=commands,
        workflows=workflows,
        evals=evals,
        security=security,
        source_path=source_path,
    )
    return cfg


def _build_project(raw: Any) -> ProjectInfo:
    if not isinstance(raw, dict):
        raise ConfigError("[project] must be a table")
    unknown = [k for k in raw if k not in _ALLOWED_PROJECT]
    if unknown:
        raise ConfigError(f"Unknown [project] fields: {sorted(unknown)}")
    if "name" not in raw:
        raise ConfigError("[project].name is required")
    name = raw["name"]
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("[project].name must be a non-empty string")
    language = raw.get("language", "other")
    if language not in _ALLOWED_LANGUAGES:
        raise ConfigError(
            f"[project].language '{language}' not in {sorted(_ALLOWED_LANGUAGES)}"
        )
    workload = raw.get("workload", "other")
    if workload not in _ALLOWED_WORKLOADS:
        raise ConfigError(
            f"[project].workload '{workload}' not in {sorted(_ALLOWED_WORKLOADS)}"
        )
    risk = raw.get("risk", "standard")
    if risk not in _ALLOWED_RISKS:
        raise ConfigError(f"[project].risk '{risk}' not in {sorted(_ALLOWED_RISKS)}")
    return ProjectInfo(name=name, language=language, workload=workload, risk=risk)


def _build_commands(raw: Any) -> dict[str, list[list[str]]]:
    if not isinstance(raw, dict):
        raise ConfigError("[commands] must be a table")
    out: dict[str, list[list[str]]] = {}
    for stage, val in raw.items():
        # An empty list means "explicitly no commands for this stage" — the
        # runner reports it as `skipped` with reason "not configured".
        if not isinstance(val, list):
            raise ConfigError(
                f"[commands].{stage} must be a list of argv arrays"
            )
        compiled: list[list[str]] = []
        for entry in val:
            if not isinstance(entry, list) or not entry:
                raise ConfigError(
                    f"[commands].{stage} entry must be a non-empty argv array"
                )
            if not all(isinstance(x, str) for x in entry):
                raise ConfigError(
                    f"[commands].{stage} argv must contain only strings"
                )
            compiled.append(list(entry))
        out[stage] = compiled
    return out


def _build_evals(raw: Any) -> dict[str, EvalConfig]:
    if not isinstance(raw, dict):
        raise ConfigError("[evals] must be a table")
    out: dict[str, EvalConfig] = {}
    for name, body in raw.items():
        if name not in {"smoke", "full"}:
            raise ConfigError(
                f"[evals.{name}] not supported; only 'smoke' and 'full' are recognized"
            )
        if not isinstance(body, dict):
            raise ConfigError(f"[evals.{name}] must be a table")
        unknown = [k for k in body if k not in _ALLOWED_EVAL_KEYS]
        if unknown:
            raise ConfigError(f"[evals.{name}] unknown fields: {sorted(unknown)}")
        if "dataset" not in body:
            raise ConfigError(f"[evals.{name}].dataset is required")
        dataset = body["dataset"]
        if not isinstance(dataset, str):
            raise ConfigError(f"[evals.{name}].dataset must be a string path")
        out[name] = EvalConfig(
            dataset=dataset,
            sample_limit=body.get("sample_limit"),
            timeout_seconds=body.get("timeout_seconds"),
            max_cost_usd=body.get("max_cost_usd"),
            min_pass_rate=body.get("min_pass_rate"),
            repetitions=int(body.get("repetitions", 1)),
            max_regression=body.get("max_regression"),
        )
    return out


def _build_security(raw: Any) -> SecurityConfig:
    if not isinstance(raw, dict):
        raise ConfigError("[security] must be a table")
    unknown = [k for k in raw if k not in _ALLOWED_SECURITY]
    if unknown:
        raise ConfigError(f"[security] unknown fields: {sorted(unknown)}")
    tool_allowlist = raw.get("tool_allowlist", [])
    if not isinstance(tool_allowlist, list) or not all(
        isinstance(t, str) for t in tool_allowlist
    ):
        raise ConfigError("[security].tool_allowlist must be a list of strings")
    approval = raw.get("require_approval_for", [])
    if not isinstance(approval, list) or not all(isinstance(a, str) for a in approval):
        raise ConfigError(
            "[security].require_approval_for must be a list of strings"
        )
    for a in approval:
        if a not in _ALLOWED_APPROVAL:
            raise ConfigError(
                f"[security].require_approval_for entry '{a}' not in "
                f"{sorted(_ALLOWED_APPROVAL)}"
            )
    return SecurityConfig(
        redact_inputs=bool(raw.get("redact_inputs", True)),
        redact_outputs=bool(raw.get("redact_outputs", True)),
        tool_allowlist=list(tool_allowlist),
        require_approval_for=list(approval),
    )


def _detect_cycles(workflows: dict[str, list[str]]) -> None:
    """Reject workflows that directly or transitively reference themselves."""
    WHITE, GREY, BLACK = 0, 1, 2
    color: dict[str, int] = {name: WHITE for name in workflows}

    def visit(name: str, stack: list[str]) -> None:
        if name not in workflows:
            return  # references a stage, not a workflow — fine
        color[name] = GREY
        for nxt in workflows[name]:
            if nxt == name:
                raise ConfigError(
                    f"workflow '{name}' references itself directly"
                )
            if color.get(nxt) == GREY:
                raise ConfigError(
                    f"cycle detected in workflows: {' -> '.join(stack + [nxt])}"
                )
            if color.get(nxt, BLACK) == WHITE:
                visit(nxt, stack + [nxt])
        color[name] = BLACK

    for name in workflows:
        if color[name] == WHITE:
            visit(name, [name])


def stage_status_reason_skip(reason: str) -> dict[str, str]:
    """Helper to build a skipped stage dict."""
    return {"status": STATUS_SKIPPED, "reason": reason}
