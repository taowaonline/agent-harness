"""Command runner — executes argv arrays via subprocess, never shell=True."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass

from .config import Config
from .redaction import redact_argv
from .result import (
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    RunResult,
    StageResult,
)

# Built-in stage names — the harness implements these directly. User
# config may still override by defining a [commands] entry with the same
# name; that entry takes precedence (it appears in cfg.commands).
BUILTIN_STAGES = {"eval-smoke", "eval-full", "security"}


@dataclass
class RunRequest:
    """What to run — either a stage name or a workflow name."""

    name: str
    dry_run: bool = False
    json_output: bool = False
    extra_args: list[str] | None = None


class RunnerError(Exception):
    pass


# Stages that are *expected* to be optional. They report `skipped` with a
# reason instead of failing the run when not configured.
_OPTIONAL_STAGES = {"typecheck", "eval-smoke", "eval-full", "security", "dev"}


def is_workflow(name: str, cfg: Config) -> bool:
    return name in cfg.workflows


def is_stage(name: str, cfg: Config) -> bool:
    return name in cfg.commands


def list_targets(cfg: Config) -> dict[str, list[str]]:
    """Return a structured listing of stages and workflows."""
    return {
        "stages": sorted(cfg.commands.keys()),
        "workflows": sorted(cfg.workflows.keys()),
        "evals": sorted(cfg.evals.keys()),
    }


def run_target(cfg: Config, request: RunRequest, result: RunResult) -> RunResult:
    """Run a stage or workflow, mutating `result` in place."""
    name = request.name
    if name in cfg.workflows:
        stage = _run_workflow(cfg, name, request, result, trail=[])
    elif name in cfg.commands:
        stage = _run_stage(cfg, name, request)
    elif name in BUILTIN_STAGES:
        stage = _run_builtin(cfg, name, request, result)
    else:
        result.add_error(f"Unknown target '{name}'. Use `./agent_harness list` to see options.")
        result.status = STATUS_FAILED
        return result
    result.stages.append(stage)
    # Propagate stage status to top-level result honestly.
    # PASSED is only kept if the stage actually passed. SKIPPED at the
    # top must not silently claim PASSED — the caller can opt into
    # exit-0 via --allow-skipped if it accepts the skip.
    if stage.status == STATUS_FAILED:
        result.status = STATUS_FAILED
    elif stage.status == STATUS_BLOCKED and result.status == STATUS_PASSED:
        result.status = STATUS_BLOCKED
    elif stage.status == STATUS_SKIPPED and result.status == STATUS_PASSED:
        result.status = STATUS_SKIPPED
    return result


def _run_workflow(
    cfg: Config,
    name: str,
    request: RunRequest,
    result: RunResult,
    trail: list[str],
) -> StageResult:
    if name in trail:
        # Cycles are also caught at config load; double-check at runtime.
        msg = f"workflow cycle: {' -> '.join(trail + [name])}"
        result.add_error(msg)
        return StageResult(name=name, kind="workflow", status=STATUS_BLOCKED, reason=msg)
    started = time.monotonic()
    started_at_iso = _now_iso()
    wf_result = StageResult(name=name, kind="workflow", started_at=started_at_iso)
    overall = STATUS_PASSED
    for child_name in cfg.workflows[name]:
        if child_name in cfg.workflows:
            child = _run_workflow(cfg, child_name, request, result, trail + [name])
        elif child_name in cfg.commands:
            child = _run_stage(cfg, child_name, request)
        elif child_name in BUILTIN_STAGES:
            child = _run_builtin(cfg, child_name, request, result)
        else:
            child = StageResult(
                name=child_name,
                kind="unknown",
                status=STATUS_BLOCKED,
                reason=(f"workflow '{name}' references unknown target '{child_name}'"),
            )
            result.add_error(child.reason or "")
        wf_result.children.append(child)
        if child.status == STATUS_FAILED:
            overall = STATUS_FAILED
            break  # fail fast — do not run remaining stages
        elif child.status == STATUS_BLOCKED and overall != STATUS_FAILED:
            overall = STATUS_BLOCKED
        elif child.status == STATUS_SKIPPED:
            # Any skip in the workflow means overall cannot remain PASSED.
            # If we haven't seen a failure/block, escalate to SKIPPED.
            if overall == STATUS_PASSED:
                overall = STATUS_SKIPPED
    # If dry-run, force SKIPPED at the workflow level (never PASSED).
    if request.dry_run and overall != STATUS_FAILED:
        overall = STATUS_SKIPPED
        wf_result.reason = "dry-run"
    elif overall == STATUS_SKIPPED and not wf_result.reason:
        skipped = [c.name for c in wf_result.children if c.status == STATUS_SKIPPED]
        passed = [c.name for c in wf_result.children if c.status == STATUS_PASSED]
        if skipped and passed:
            wf_result.reason = (
                f"partial: {len(passed)} passed, {len(skipped)} skipped "
                f"(skipped: {', '.join(skipped)})"
            )
        elif skipped:
            wf_result.reason = "all stages skipped"
    wf_result.status = overall
    wf_result.duration_ms = int((time.monotonic() - started) * 1000)
    return wf_result


def _run_builtin(cfg: Config, name: str, request: RunRequest, result: RunResult) -> StageResult:
    """Dispatch to a built-in stage. Eval defaults to offline in workflows."""
    if name in ("eval-smoke", "eval-full"):
        kind = "smoke" if name == "eval-smoke" else "full"
        if request.dry_run:
            return StageResult(
                name=name,
                kind="eval",
                status=STATUS_SKIPPED,
                reason="dry-run",
                argv=["<builtin:run_eval>", kind, "offline=True"],
            )
        # Local import to avoid a circular import at module load time.
        from .evals import run_eval

        return run_eval(cfg, kind, result, offline=True)
    if name == "security":
        if request.dry_run:
            return StageResult(
                name=name,
                kind="check",
                status=STATUS_SKIPPED,
                reason="dry-run",
                argv=["<builtin:security_check>"],
            )
        # Local import for the same reason.
        from .security import run_security_check

        return run_security_check(cfg, result)
    return StageResult(
        name=name,
        kind="unknown",
        status=STATUS_BLOCKED,
        reason=f"unknown builtin '{name}'",
    )


def _run_stage(cfg: Config, name: str, request: RunRequest) -> StageResult:
    argv_arrays = cfg.commands[name]
    stage = StageResult(
        name=name,
        kind="command",
        started_at=_now_iso(),
    )
    started = time.monotonic()
    # Explicitly empty argv list => configured but no commands; report skipped.
    if not argv_arrays:
        stage.status = STATUS_SKIPPED
        stage.reason = "not configured"
        stage.duration_ms = int((time.monotonic() - started) * 1000)
        return stage
    if request.dry_run:
        # Show the planned argv on the stage itself; no children, no exec.
        stage.status = STATUS_SKIPPED
        stage.reason = "dry-run"
        # If exactly one argv, attach it directly. Otherwise list under children.
        if len(argv_arrays) == 1:
            stage.argv = redact_argv(argv_arrays[0])
        else:
            for argv in argv_arrays:
                stage.children.append(
                    StageResult(
                        name=name,
                        kind="command",
                        status=STATUS_SKIPPED,
                        reason="dry-run",
                        argv=redact_argv(argv),
                    )
                )
        stage.duration_ms = int((time.monotonic() - started) * 1000)
        return stage
    overall = STATUS_PASSED
    saw_skipped_only = True
    # If there is exactly one argv, attach its result to the stage itself
    # instead of nesting under children — avoids confusing duplicate output.
    single = len(argv_arrays) == 1
    for argv in argv_arrays:
        if not argv:
            continue
        sub_status, exit_code = _exec_one(argv, name)
        if sub_status == STATUS_FAILED:
            reason = f"command exited {exit_code}: {' '.join(redact_argv(argv))}"
            if single:
                stage.argv = redact_argv(argv)
                stage.exit_code = exit_code
                stage.reason = reason
            else:
                stage.children.append(
                    StageResult(
                        name=name,
                        kind="command",
                        status=sub_status,
                        argv=redact_argv(argv),
                        exit_code=exit_code,
                        reason=reason,
                    )
                )
            overall = STATUS_FAILED
            break
        if sub_status != STATUS_SKIPPED:
            saw_skipped_only = False
        if single:
            stage.argv = redact_argv(argv)
            stage.exit_code = exit_code
            if sub_status == STATUS_SKIPPED:
                stage.reason = "executable unavailable for optional stage"
        else:
            stage.children.append(
                StageResult(
                    name=name,
                    kind="command",
                    status=sub_status,
                    argv=redact_argv(argv),
                    exit_code=exit_code,
                )
            )
    if overall == STATUS_PASSED and (single or stage.children) and saw_skipped_only:
        overall = STATUS_SKIPPED
        if not single:
            stage.reason = "executable unavailable for optional stage"
    stage.status = overall
    stage.duration_ms = int((time.monotonic() - started) * 1000)
    return stage


def _exec_one(
    argv: list[str], stage_name: str, *, timeout: float = 600.0
) -> tuple[str, int | None]:
    """Execute one argv array. Returns (status, exit_code).

    If the executable is missing and the stage is optional, returns SKIPPED
    with a meaningful reason rather than failing.
    """
    exe = argv[0]
    resolved = shutil.which(exe)
    if resolved is None:
        # Optional stages may skip when the binary is absent.
        if stage_name in _OPTIONAL_STAGES:
            return STATUS_SKIPPED, None
        # For required stages, surface as a failure with a clear cause.
        return STATUS_FAILED, 127
    try:
        proc = subprocess.run(
            list(argv),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return STATUS_FAILED, 124
    except FileNotFoundError:
        return STATUS_FAILED, 127
    if proc.returncode != 0:
        return STATUS_FAILED, proc.returncode
    return STATUS_PASSED, proc.returncode


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# `os` imported for type completeness in future hooks (env scrubbing etc).
__all__ = [
    "RunRequest",
    "RunnerError",
    "is_workflow",
    "is_stage",
    "list_targets",
    "run_target",
]
