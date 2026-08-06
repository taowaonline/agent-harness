"""Structured result objects.

The result schema is part of the public CLI contract. Every execution
returns a record that matches this shape so external tools (CI, dashboards,
other Agents) can rely on it.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1

# Status values are part of the contract — do not rename.
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_BLOCKED = "blocked"
ALL_STATUSES = (STATUS_PASSED, STATUS_FAILED, STATUS_SKIPPED, STATUS_BLOCKED)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_run_id() -> str:
    return uuid.uuid4().hex


@dataclass
class StageResult:
    """One stage's result. A workflow result is a tree of StageResult."""

    name: str
    kind: str = "command"  # command | workflow | eval | check
    status: str = STATUS_PASSED
    started_at: str = field(default_factory=_utc_now_iso)
    duration_ms: int = 0
    argv: list[str] | None = None
    exit_code: int | None = None
    reason: str | None = None  # why skipped / blocked / failed
    children: list["StageResult"] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not self.children:
            data.pop("children", None)
        if self.argv is None:
            data.pop("argv", None)
        if self.exit_code is None:
            data.pop("exit_code", None)
        if self.reason is None:
            data.pop("reason", None)
        if not self.metrics:
            data.pop("metrics", None)
        return data


@dataclass
class RunResult:
    """Top-level result for one CLI invocation."""

    run_id: str = field(default_factory=_new_run_id)
    schema_version: int = SCHEMA_VERSION
    command: str = ""
    status: str = STATUS_PASSED
    started_at: str = field(default_factory=_utc_now_iso)
    duration_ms: int = 0
    stages: list[StageResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._start_monotonic = time.monotonic()

    def finish(self) -> None:
        self.duration_ms = int((time.monotonic() - self._start_monotonic) * 1000)

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def to_dict(self) -> dict[str, Any]:
        self.finish()
        data = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "command": self.command,
            "status": self.status,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "stages": [s.to_dict() for s in self.stages],
            "summary": self.summary,
            "errors": self.errors,
        }
        return data
