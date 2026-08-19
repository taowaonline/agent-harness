"""Offline deterministic eval system.

Loads JSONL datasets, runs deterministic graders, aggregates results, and
applies threshold/regression gates. Model-based graders are a plugin
interface — never required by the unit or integration tests.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import statistics
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import Config, EvalConfig
from .redaction import redact
from .result import (
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_PASSED,
    STATUS_SKIPPED,
    RunResult,
    StageResult,
)

# ---------------------------------------------------------------------------
# Dataset model
# ---------------------------------------------------------------------------


class DatasetError(Exception):
    pass


@dataclass
class EvalCase:
    id: str
    input: dict[str, Any]
    expected: dict[str, Any]
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_line: int = 0


@dataclass
class CaseResult:
    case_id: str
    status: str  # passed | failed | error | skipped
    grader: str = ""
    reason: str = ""
    duration_ms: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    # The actual model output is *not* stored by default — redaction policy.
    output_redacted: bool = True


@dataclass
class EvalReport:
    name: str
    dataset: str
    started_at: str
    duration_ms: int
    harness_version: str
    git_sha: str
    summary: dict[str, Any]
    cases: list[dict[str, Any]]
    thresholds: dict[str, Any]
    status: str
    # Unique per-run id; included in the persisted filename so that two
    # evals started in the same second never overwrite each other.
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def load_dataset(path: str | Path, *, project_root: Path | None = None) -> list[EvalCase]:
    """Load and validate a JSONL dataset. Raises DatasetError on any issue.

    If `path` is relative and `project_root` is given, resolves against
    `project_root` rather than the process cwd.
    """
    p = Path(path)
    if not p.is_absolute() and project_root is not None:
        p = project_root / p
    if not p.exists():
        raise DatasetError(f"Dataset not found: {path}")
    seen_ids: set[str] = set()
    cases: list[EvalCase] = []
    with p.open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                raise DatasetError(f"{path}:{lineno}: invalid JSON ({e.msg})") from e
            case = _build_case(rec, path, lineno)
            if case.id in seen_ids:
                raise DatasetError(f"{path}:{lineno}: duplicate case id '{case.id}'")
            seen_ids.add(case.id)
            cases.append(case)
    if not cases:
        raise DatasetError(f"{path}: dataset is empty")
    return cases


def _build_case(rec: Any, path: str | Path, lineno: int) -> EvalCase:
    if not isinstance(rec, dict):
        raise DatasetError(f"{path}:{lineno}: each record must be a JSON object")
    for required in ("id", "input", "expected"):
        if required not in rec:
            raise DatasetError(f"{path}:{lineno}: missing required field '{required}'")
    cid = rec["id"]
    if not isinstance(cid, str) or not cid:
        raise DatasetError(f"{path}:{lineno}: 'id' must be a non-empty string")
    inp = rec["input"]
    if not isinstance(inp, dict):
        raise DatasetError(f"{path}:{lineno}: 'input' must be an object")
    exp = rec["expected"]
    if not isinstance(exp, dict):
        raise DatasetError(f"{path}:{lineno}: 'expected' must be an object")
    _validate_expected_shape(exp, path, lineno)
    tags = rec.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise DatasetError(f"{path}:{lineno}: 'tags' must be a list of strings")
    meta = rec.get("metadata", {})
    if not isinstance(meta, dict):
        raise DatasetError(f"{path}:{lineno}: 'metadata' must be an object")
    return EvalCase(
        id=cid,
        input=inp,
        expected=exp,
        tags=list(tags),
        metadata=dict(meta),
        source_line=lineno,
    )


def _validate_expected_shape(exp: dict[str, Any], path: str | Path, lineno: int) -> None:
    """Reject expected-field shapes that would crash or silently misgrade.

    Caught here (at dataset load, with file:line context) rather than deep
    inside a grader as an IndexError/AttributeError internal error:
      - `contains` must be a non-empty list of strings — an empty list would
        IndexError on `[0]`, and a bare string would silently grade on its
        first character.
      - `not_contains` must be a list of strings.
      - `regex` must be a string and must compile.
      - `graders` must be a list of objects.
    """
    if "contains" in exp:
        v = exp["contains"]
        if not isinstance(v, list) or not v or not all(isinstance(x, str) for x in v):
            raise DatasetError(
                f"{path}:{lineno}: 'expected.contains' must be a non-empty list of strings"
            )
    if "not_contains" in exp:
        v = exp["not_contains"]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise DatasetError(
                f"{path}:{lineno}: 'expected.not_contains' must be a list of strings"
            )
    if "regex" in exp:
        v = exp["regex"]
        if not isinstance(v, str):
            raise DatasetError(f"{path}:{lineno}: 'expected.regex' must be a string")
        try:
            re.compile(v)
        except re.error as e:
            raise DatasetError(f"{path}:{lineno}: 'expected.regex' does not compile: {e}") from e
    if "graders" in exp:
        v = exp["graders"]
        if not isinstance(v, list) or not all(isinstance(g, dict) for g in v):
            raise DatasetError(
                f"{path}:{lineno}: 'expected.graders' must be a list of grader objects"
            )


# ---------------------------------------------------------------------------
# Graders (deterministic)
# ---------------------------------------------------------------------------


GraderResult = tuple[bool, str]
Grader = Callable[[dict[str, Any], dict[str, Any]], GraderResult]


def grader_exact(expected: dict[str, Any], output: dict[str, Any]) -> GraderResult:
    want = expected.get("exact")
    got = output.get("answer")
    if want is None:
        return False, "no 'exact' expected value defined"
    ok = want == got
    return ok, "" if ok else f"expected exact={want!r}, got {got!r}"


def grader_contains(expected: dict[str, Any], output: dict[str, Any]) -> GraderResult:
    needle = expected.get("needle") or expected.get("value")
    if not isinstance(needle, str):
        return False, "contains grader requires 'needle'"
    hay = output.get("answer") or output.get("text") or ""
    if not isinstance(hay, str):
        hay = json.dumps(hay, ensure_ascii=False)
    ok = needle in hay
    return ok, "" if ok else f"missing required substring {needle!r}"


def grader_not_contains(expected: dict[str, Any], output: dict[str, Any]) -> GraderResult:
    forbidden = expected.get("needle") or expected.get("value")
    if not isinstance(forbidden, str):
        return False, "not_contains grader requires 'needle'"
    hay = output.get("answer") or output.get("text") or ""
    if not isinstance(hay, str):
        hay = json.dumps(hay, ensure_ascii=False)
    ok = forbidden not in hay
    return ok, "" if ok else f"forbidden substring present: {forbidden!r}"


def grader_regex(expected: dict[str, Any], output: dict[str, Any]) -> GraderResult:
    pattern = expected.get("pattern")
    if not isinstance(pattern, str):
        return False, "regex grader requires 'pattern'"
    hay = output.get("answer") or output.get("text") or ""
    if not isinstance(hay, str):
        hay = json.dumps(hay, ensure_ascii=False)
    try:
        pat = re.compile(pattern)
    except re.error as e:
        return False, f"invalid regex: {e}"
    ok = pat.search(hay) is not None
    return ok, "" if ok else f"pattern {pattern!r} did not match"


def grader_json_parse(expected: dict[str, Any], output: dict[str, Any]) -> GraderResult:
    raw = output.get("answer") or output.get("text") or ""
    if not isinstance(raw, str):
        raw = json.dumps(raw, ensure_ascii=False)
    try:
        json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"output is not valid JSON: {e.msg}"
    return True, ""


def grader_json_field(expected: dict[str, Any], output: dict[str, Any]) -> GraderResult:
    field = expected.get("field")
    want = expected.get("equals")
    if not isinstance(field, str):
        return False, "json_field grader requires 'field'"
    raw = output.get("answer") or output.get("text") or output
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            return False, f"output is not valid JSON: {e.msg}"
    elif isinstance(raw, dict):
        parsed = raw
    else:
        return False, "json_field grader needs an object or JSON string"
    if not isinstance(parsed, dict):
        return False, "JSON output is not an object"
    if field not in parsed:
        return False, f"field '{field}' missing from output"
    ok = parsed[field] == want
    return ok, "" if ok else f"field '{field}': expected {want!r}, got {parsed[field]!r}"


def grader_tool_call(expected: dict[str, Any], output: dict[str, Any]) -> GraderResult:
    want_name = expected.get("tool")
    calls = output.get("tool_calls") or []
    if not isinstance(calls, list):
        return False, "tool_calls must be a list"
    for call in calls:
        if not isinstance(call, dict):
            continue
        if call.get("name") == want_name:
            want_args = expected.get("args") or {}
            if not isinstance(want_args, dict):
                return True, ""
            got_args = call.get("args") or {}
            if not isinstance(got_args, dict):
                return False, "tool call args must be a dict"
            for k, v in want_args.items():
                if got_args.get(k) != v:
                    return False, (
                        f"tool {want_name}: arg '{k}' expected {v!r}, got {got_args.get(k)!r}"
                    )
            return True, ""
    return False, f"expected tool '{want_name}' was not called"


def grader_threshold(expected: dict[str, Any], output: dict[str, Any]) -> GraderResult:
    metric = expected.get("metric")
    limit = expected.get("max")
    if metric is None or limit is None:
        return False, "threshold grader requires 'metric' and 'max'"
    value = output.get("metrics", {}).get(metric)
    if value is None:
        return False, f"metric '{metric}' not provided in output"
    try:
        ok = float(value) <= float(limit)
    except (TypeError, ValueError):
        return False, f"metric '{metric}' is not numeric"
    return ok, "" if ok else f"{metric}={value} exceeds limit {limit}"


GRADER_REGISTRY: dict[str, Grader] = {
    "exact": grader_exact,
    "contains": grader_contains,
    "not_contains": grader_not_contains,
    "regex": grader_regex,
    "json_parse": grader_json_parse,
    "json_field": grader_json_field,
    "tool_call": grader_tool_call,
    "threshold": grader_threshold,
}


def register_grader(name: str, fn: Grader) -> None:
    """Register a custom grader. Used for semantic/model-based graders."""
    GRADER_REGISTRY[name] = fn


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


class _RunnerError(Exception):
    """Raised when a subprocess runner fails terminally."""


def _invoke_subprocess_runner(
    ec: EvalConfig, cases: list[EvalCase], result: RunResult
) -> dict[str, dict[str, Any]]:
    """Spawn `ec.runner` argv, feed cases on stdin, read results from stdout.

    Protocol:
      - stdin: one Case JSON per line. Each line is the full record from the
        dataset (id/input/expected/tags/metadata).
      - stdout: one Result JSON per line, in the same order as input.
        Each result must contain at least `case_id` and `output`.
      - stderr: diagnostic logs (will be redacted on capture).
      - exit code: 0 = success, non-zero = runner failure (all cases error).

    Timeout semantics: `ec.timeout_seconds` (default 600s) is the **whole
    subprocess timeout** passed to `subprocess.run`. It is NOT a per-line
    or per-case budget. If you need per-case timeouts, the runner itself
    must enforce them internally.

    Errors and protocol violations raise `_RunnerError`, which the caller
    turns into a stage failure. Specifically:
      - non-zero runner exit
      - subprocess timeout
      - line count mismatch (stdout has fewer/more lines than stdin)
      - malformed JSON on a stdout line
      - missing or non-string `case_id` field
      - `case_id` does not match the corresponding input case id

    Any of these is considered a runner-contract violation; the eval stage
    fails rather than silently degrading. Positional validation makes the
    duplicate/unknown case_id scenario impossible — any reordering surfaces
    as a mismatch on the first affected line.
    """
    import subprocess

    if not ec.runner:
        return {}
    argv = list(ec.runner)
    exe = argv[0]
    resolved = shutil.which(exe)
    if resolved is None and not os.path.isabs(exe):
        raise _RunnerError(f"runner executable '{exe}' not found on PATH")
    # Build stdin payload.
    stdin_lines: list[str] = []
    expected_ids: list[str] = []
    for case in cases:
        line = json.dumps(
            {
                "id": case.id,
                "input": case.input,
                "expected": case.expected,
                "tags": case.tags,
                "metadata": case.metadata,
            },
            ensure_ascii=False,
        )
        stdin_lines.append(line)
        expected_ids.append(case.id)
    stdin_payload = "\n".join(stdin_lines) + "\n"
    timeout = ec.timeout_seconds if ec.timeout_seconds else 600
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise _RunnerError(f"runner timed out after {timeout}s ({len(cases)} cases)") from e
    except FileNotFoundError as e:
        raise _RunnerError(f"runner executable vanished at exec time: {e}") from e
    # Redact stderr before storing it anywhere.
    stderr_redacted = redact(proc.stderr or "")
    if proc.returncode != 0:
        raise _RunnerError(f"runner exited {proc.returncode}; stderr: {stderr_redacted[:500]}")
    # Parse stdout. The runner must emit one JSON object per line, in the
    # same order as the cases were sent, with `case_id` matching the input.
    stdout_lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
    if len(stdout_lines) != len(cases):
        raise _RunnerError(
            f"runner returned {len(stdout_lines)} result lines for "
            f"{len(cases)} input cases (line-count mismatch)"
        )
    outputs: dict[str, dict[str, Any]] = {}
    for expected_id, line in zip(expected_ids, stdout_lines, strict=False):
        # Per-line malformed JSON is a contract violation, not a soft skip.
        # `strict=False` because we already check len() equality above.
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise _RunnerError(
                f"runner emitted malformed JSON for case '{expected_id}': "
                f"{e.msg}; line: {line[:200]}"
            ) from e
        if not isinstance(rec, dict):
            raise _RunnerError(f"runner result for case '{expected_id}' is not a JSON object")
        got_id = rec.get("case_id")
        if not isinstance(got_id, str) or not got_id:
            raise _RunnerError(
                f"runner result for case '{expected_id}' missing string 'case_id' field"
            )
        # Positional + value check: the runner must emit results in the
        # same order as the cases were sent, and case_id must match the
        # input. This implicitly catches duplicate / unknown / missing
        # case_ids because any reordering surfaces as a mismatch on the
        # first affected line.
        if got_id != expected_id:
            raise _RunnerError(
                f"runner case_id mismatch: expected '{expected_id}', "
                f"got '{got_id}' (results must be in input order)"
            )
        out = rec.get("output")
        if not isinstance(out, dict):
            out = {"answer": out} if out is not None else {}
        # Carry cost_usd into the output dict so the eval loop can sum it.
        # The grader ignores unknown keys, so this is non-invasive.
        cost = rec.get("cost_usd")
        if isinstance(cost, int | float):
            out["_cost_usd"] = float(cost)
        outputs[got_id] = out
    return outputs


def _resolve_dataset_path(dataset: str, project_root: Path | None) -> Path:
    p = Path(dataset)
    if not p.is_absolute() and project_root is not None:
        p = project_root / p
    return p


def _run_snapshot_record(
    cfg: Config,
    ec: EvalConfig,
    name: str,
    cases: list[EvalCase],
    dataset_path: Path,
    result: RunResult,
    started_at: str,
    started: float,
) -> StageResult | None:
    """Record mode: run the runner, write outputs back as fixtures.

    Returns None on success (caller falls through to replay grading
    against the fresh fixtures); returns a StageResult on failure.
    """
    assert ec.runner is not None
    try:
        runner_outputs = _invoke_subprocess_runner(ec, cases, result)
    except _RunnerError as e:
        result.add_error(f"runner: {e}")
        return StageResult(
            name=name,
            kind="eval",
            status=STATUS_FAILED,
            reason=f"runner failed: {e}",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    # Rewrite the dataset with fresh fixtures, preserving field order and
    # any non-fixture fields exactly as loaded. Atomic: temp + replace.
    lines: list[str] = []
    updated = 0
    for case in cases:
        rec: dict[str, Any] = {
            "id": case.id,
            "input": dict(case.input),
            "expected": case.expected,
        }
        if case.tags:
            rec["tags"] = case.tags
        if case.metadata:
            rec["metadata"] = case.metadata
        out = runner_outputs.get(case.id)
        if out is not None:
            clean = {k: v for k, v in out.items() if not k.startswith("_")}
            rec["input"]["output"] = clean
            updated += 1
        lines.append(json.dumps(rec, ensure_ascii=False))
    tmp = dataset_path.with_name(f".{os.getpid()}-record.tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, dataset_path)
    result.summary["recorded_fixtures"] = updated
    result.summary["dataset"] = str(dataset_path)
    return None


def _run_snapshot_diff(
    cfg: Config,
    ec: EvalConfig,
    name: str,
    cases: list[EvalCase],
    result: RunResult,
    started_at: str,
    started: float,
) -> StageResult:
    """Diff mode: run the runner, compare against recorded fixtures.

    Fails the stage on any mismatch; never writes the dataset. Missing
    fixtures count as mismatches (nothing recorded to compare against).
    """
    assert ec.runner is not None
    duration = int((time.monotonic() - started) * 1000)
    try:
        runner_outputs = _invoke_subprocess_runner(ec, cases, result)
    except _RunnerError as e:
        result.add_error(f"runner: {e}")
        return StageResult(
            name=name,
            kind="eval",
            status=STATUS_FAILED,
            reason=f"runner failed: {e}",
            started_at=started_at,
            duration_ms=duration,
        )
    mismatches: list[str] = []
    matched = 0
    for case in cases:
        fixture = case.input.get("output") or case.metadata.get("output")
        actual_raw = runner_outputs.get(case.id)
        if actual_raw is None:
            mismatches.append(f"{case.id}: runner produced no output")
            continue
        actual = {k: v for k, v in actual_raw.items() if not k.startswith("_")}
        if fixture == actual:
            matched += 1
        else:
            mismatches.append(
                f"{case.id}: fixture != runner output "
                f"(fixture={json.dumps(fixture, ensure_ascii=False, sort_keys=True)[:200]} "
                f"actual={json.dumps(actual, ensure_ascii=False, sort_keys=True)[:200]})"
            )
    summary = {
        "mode": "diff",
        "total": len(cases),
        "matched": matched,
        "mismatched": len(mismatches),
    }
    thresholds = _threshold_block(ec)
    if mismatches:
        for m in mismatches[:10]:
            result.add_error(f"snapshot diff: {m}")
        if len(mismatches) > 10:
            result.add_error(f"snapshot diff: ...and {len(mismatches) - 10} more")
        return StageResult(
            name=name,
            kind="eval",
            status=STATUS_FAILED,
            reason=f"{len(mismatches)} snapshot mismatch(es); run "
            f"`--snapshot-mode=record` after reviewing, never auto-promote",
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
            metrics={"summary": summary, "thresholds": thresholds},
        )
    return StageResult(
        name=name,
        kind="eval",
        status=STATUS_PASSED,
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        metrics={"summary": summary, "thresholds": thresholds},
    )


def run_eval(
    cfg: Config,
    name: str,
    result: RunResult,
    *,
    offline: bool,
    provider: ModelProvider | None = None,
    snapshot_mode: str = "replay",
) -> StageResult:
    """Run an eval (smoke or full) in one of three snapshot modes.

    Modes (adapted from dsh's DSH_SNAPSHOT record/replay/refresh):
      - replay (default): grade against the fixture `output` baked into
        the dataset. Keyless; this is the CI protocol gate.
      - record: invoke the configured runner and write its outputs back
        into the dataset as new fixtures, then grade. The dataset file
        is rewritten atomically; every diff is reviewed by the human
        who runs record.
      - diff: invoke the runner and compare its outputs against the
        recorded fixtures without writing. Any mismatch fails the stage
        with a per-case report. This is the "behavior changed?" gate.

    `provider` is a callable that takes a case and returns a dict output.
    When `offline` is True (replay) and no provider is given, the eval
    uses the `output` fixture baked into the dataset (if present), else
    marks the case as `error`.
    """
    if snapshot_mode not in ("replay", "record", "diff"):
        msg = f"unknown snapshot_mode '{snapshot_mode}' (replay|record|diff)"
        result.add_error(msg)
        return StageResult(name=name, kind="eval", status=STATUS_FAILED, reason=msg)
    if snapshot_mode in ("record", "diff"):
        if name not in cfg.evals or not cfg.evals[name].runner:
            msg = f"snapshot-mode={snapshot_mode} requires [evals.{name}].runner"
            result.add_error(msg)
            return StageResult(name=name, kind="eval", status=STATUS_FAILED, reason=msg)
    if name not in cfg.evals:
        msg = f"eval '{name}' is not configured"
        result.add_error(msg)
        return StageResult(name=name, kind="eval", status=STATUS_SKIPPED, reason=msg)
    ec = cfg.evals[name]
    started_at = _now_iso()
    started = time.monotonic()
    dataset_path = _resolve_dataset_path(ec.dataset, cfg.project_root)
    try:
        cases = load_dataset(ec.dataset, project_root=cfg.project_root)
    except DatasetError as e:
        result.add_error(str(e))
        return StageResult(
            name=name,
            kind="eval",
            status=STATUS_FAILED,
            reason=str(e),
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    if ec.sample_limit is not None:
        cases = cases[: ec.sample_limit]

    # ── diff mode: compare runner behavior against recorded fixtures ──
    if snapshot_mode == "diff":
        return _run_snapshot_diff(cfg, ec, name, cases, result, started_at, started)

    # ── record mode: run the runner, write outputs back as fixtures ──
    if snapshot_mode == "record":
        record_stage = _run_snapshot_record(
            cfg, ec, name, cases, dataset_path, result, started_at, started
        )
        if record_stage is not None:
            return record_stage
        # Fall through: dataset now carries fresh fixtures; replay-grade.

    # Honor `repetitions` (default 1). For non-deterministic workloads
    # (chat/agent traces) the user sets this >1 and we report the worst
    # pass_rate observed across reps. Each rep re-grades; fixture mode
    # returns identical results so reps have no effect there.
    reps = max(1, int(ec.repetitions or 1))
    worst_summary: dict[str, Any] | None = None
    final_case_results: list[CaseResult] = []
    worst_cost_usd: float | None = None  # max cost seen across reps
    for _rep in range(reps):
        # If a subprocess runner is configured, invoke it ONCE per rep.
        runner_outputs: dict[str, dict[str, Any]] = {}
        if ec.runner:
            try:
                runner_outputs = _invoke_subprocess_runner(ec, cases, result)
            except _RunnerError as e:
                result.add_error(f"runner: {e}")
                return StageResult(
                    name=name,
                    kind="eval",
                    status=STATUS_FAILED,
                    reason=f"runner failed: {e}",
                    started_at=started_at,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
        case_results: list[CaseResult] = []
        for case in cases:
            case_results.append(
                _grade_case(
                    case,
                    ec,
                    offline=offline,
                    provider=provider,
                    runner_output=runner_outputs.get(case.id),
                )
            )
        summary = _summarize(case_results)
        # Sum cost if runner reported it. _invoke_subprocess_runner
        # carries cost_usd into each output dict as _cost_usd.
        rep_cost: float | None = None
        if runner_outputs:
            rep_cost = 0.0
            for out in runner_outputs.values():
                c = out.get("_cost_usd")
                if isinstance(c, int | float):
                    rep_cost += float(c)
                else:
                    rep_cost = None  # any missing cost → can't aggregate
                    break
        if rep_cost is not None:
            summary["cost_usd"] = round(rep_cost, 6)
            if worst_cost_usd is None or rep_cost > worst_cost_usd:
                worst_cost_usd = rep_cost
        # Track worst-case across repetitions.
        if worst_summary is None or summary.get("pass_rate", 0.0) < worst_summary.get(
            "pass_rate", 1.0
        ):
            worst_summary = summary
            final_case_results = case_results
    assert worst_summary is not None  # reps >= 1
    summary = worst_summary
    case_results = final_case_results
    if reps > 1:
        summary["repetitions"] = reps
        summary["aggregation"] = "worst_pass_rate"
    if worst_cost_usd is not None:
        summary["worst_cost_usd"] = round(worst_cost_usd, 6)
    thresholds = _threshold_block(ec)
    status = _apply_thresholds(summary, ec)
    # Cost enforcement gate. Only fires when enforce_max_cost=true AND the
    # runner actually reported cost_usd. Default (advisory) doesn't block.
    if (
        ec.enforce_max_cost
        and ec.max_cost_usd is not None
        and worst_cost_usd is not None
        and worst_cost_usd > ec.max_cost_usd
    ):
        status = STATUS_FAILED
        result.add_error(
            f"cost gate: ${worst_cost_usd:.4f} exceeds budget "
            f"${ec.max_cost_usd:.4f} (enforce_max_cost=true)"
        )
    report = EvalReport(
        name=name,
        dataset=ec.dataset,
        started_at=started_at,
        duration_ms=int((time.monotonic() - started) * 1000),
        harness_version=_harness_version(),
        git_sha=_git_sha(),
        summary=summary,
        cases=[_redact_case_dict(c) for c in case_results],
        thresholds=thresholds,
        status=status,
    )
    stage = StageResult(
        name=name,
        kind="eval",
        status=status,
        started_at=started_at,
        duration_ms=report.duration_ms,
        metrics={"summary": summary, "thresholds": thresholds},
    )
    if status != STATUS_PASSED:
        stage.reason = (
            f"eval '{name}' {status}: "
            f"pass_rate={summary['pass_rate']:.3f}, "
            f"min_pass_rate={ec.min_pass_rate}"
        )
        result.add_error(stage.reason)
    # Persist the report under evals/reports/ for downstream comparison.
    _persist_report(report, project_root=cfg.project_root)
    return stage


def _grade_case(
    case: EvalCase,
    ec: EvalConfig,
    *,
    offline: bool,
    provider: ModelProvider | None,
    runner_output: dict[str, Any] | None = None,
) -> CaseResult:
    started = time.monotonic()
    # Resolve the model output. Priority: runner_output (subprocess) >
    # provider (Python callable) > fixture (offline dataset).
    if runner_output is not None:
        output = runner_output
    elif provider is not None:
        try:
            output = provider(case)
        except Exception as e:  # noqa: BLE001
            return CaseResult(
                case_id=case.id,
                status="error",
                reason=redact(str(e)),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
    elif offline:
        output = case.input.get("output") or case.metadata.get("output")
        if output is None:
            return CaseResult(
                case_id=case.id,
                status="skipped",
                reason="offline mode requires a fixture output or runner",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
    else:
        return CaseResult(
            case_id=case.id,
            status="error",
            reason="no provider or runner configured for online eval",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    if not isinstance(output, dict):
        output = {"answer": output}
    # Apply the grader(s) named in expected.graders, defaulting to a
    # plain exact-match check.
    graders = case.expected.get("graders")
    if graders is None:
        # If only `contains` / `exact` is set directly, run the matching one.
        graders = []
        if "exact" in case.expected:
            graders.append({"kind": "exact"})
        if "contains" in case.expected:
            # All needles must be present, mirroring not_contains — the
            # dataset lists every required substring, not just the first.
            for needle in case.expected["contains"]:
                graders.append({"kind": "contains", "needle": needle})
        if "not_contains" in case.expected:
            for needle in case.expected["not_contains"]:
                graders.append({"kind": "not_contains", "needle": needle})
        if "regex" in case.expected:
            graders.append({"kind": "regex", "pattern": case.expected["regex"]})
        if not graders:
            return CaseResult(
                case_id=case.id,
                status="error",
                reason="no grader configured",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
    fails: list[str] = []
    for spec in graders:
        kind = spec.get("kind")
        fn = GRADER_REGISTRY.get(kind) if kind else None
        if fn is None:
            fails.append(f"unknown grader '{kind}'")
            continue
        ok, reason = fn(spec, output)
        if not ok:
            fails.append(f"[{kind}] {reason}")
    duration_ms = int((time.monotonic() - started) * 1000)
    if fails:
        return CaseResult(
            case_id=case.id,
            status="failed",
            reason="; ".join(fails),
            duration_ms=duration_ms,
        )
    return CaseResult(
        case_id=case.id,
        status="passed",
        duration_ms=duration_ms,
    )


def _summarize(case_results: list[CaseResult]) -> dict[str, Any]:
    total = len(case_results)
    if total == 0:
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "pass_rate": 0.0,
        }
    by_status = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    durations: list[float] = []
    for c in case_results:
        by_status[c.status] = by_status.get(c.status, 0) + 1
        durations.append(c.duration_ms)
    graded = by_status["passed"] + by_status["failed"]
    pass_rate = (by_status["passed"] / graded) if graded else 0.0
    p50 = statistics.median(durations) if durations else 0.0
    p95 = _percentile(durations, 95) if durations else 0.0
    return {
        "total": total,
        "passed": by_status["passed"],
        "failed": by_status["failed"],
        "errors": by_status["error"],
        "skipped": by_status["skipped"],
        "pass_rate": round(pass_rate, 4),
        "p50_latency_ms": int(p50),
        "p95_latency_ms": int(p95),
    }


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((pct / 100.0) * (len(s) - 1)))
    return float(s[k])


def _threshold_block(ec: EvalConfig) -> dict[str, Any]:
    return {
        "min_pass_rate": ec.min_pass_rate,
        "max_regression": ec.max_regression,
        "sample_limit": ec.sample_limit,
        "timeout_seconds": ec.timeout_seconds,
        "max_cost_usd": ec.max_cost_usd,
    }


def _apply_thresholds(summary: dict[str, Any], ec: EvalConfig) -> str:
    if ec.min_pass_rate is not None:
        if summary["pass_rate"] < ec.min_pass_rate:
            return STATUS_FAILED
    if summary.get("errors", 0) > 0 and summary.get("passed", 0) == 0:
        return STATUS_BLOCKED
    return STATUS_PASSED


def _redact_case_dict(c: CaseResult) -> dict[str, Any]:
    d = asdict(c)
    # Never include the raw output text in the persisted report.
    return d


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _harness_version() -> str:
    try:
        from . import __version__

        return __version__
    except Exception:  # noqa: BLE001
        return "unknown"


def _git_sha() -> str:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def _persist_report(report: EvalReport, *, project_root: Path | None = None) -> Path:
    base = project_root if project_root is not None else Path.cwd()
    out_dir = base / "evals" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_started = report.started_at.replace(":", "").replace("-", "")
    # Include the run_id short hash so two evals started in the same second
    # never overwrite each other.
    fname = f"{report.name}-{safe_started}-{report.run_id[:8]}.json"
    out = out_dir / fname
    payload = report.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    redacted = redact(text)
    # Atomic write: PID-scoped temp file + os.replace. The PID suffix
    # ensures two concurrent processes can never collide on the .tmp
    # file even if they share the same report directory (which happens
    # when running `harness run check` and `harness run release-check`
    # in parallel).
    tmp = out_dir / f".{os.getpid()}-{report.run_id[:8]}.tmp"
    tmp.write_text(redacted, encoding="utf-8")
    os.replace(tmp, out)
    return out


# Type alias used in the runner signature.
ModelProvider = Callable[[EvalCase], dict[str, Any]]


def compare_reports(
    a_path: str,
    b_path: str,
    *,
    max_regression: float | None = None,
) -> dict[str, Any]:
    """Compare two eval reports and surface deltas.

    `max_regression` (0.0–1.0): if set and the regression is at or below
    the threshold, the verdict is `within_threshold` rather than `regressed`.
    When called via `harness baseline compare --max-regression N` or via
    `--config <eval>`, the configured threshold gates the verdict.
    """
    a = json.loads(Path(a_path).read_text(encoding="utf-8"))
    b = json.loads(Path(b_path).read_text(encoding="utf-8"))
    sa = a.get("summary", {})
    sb = b.get("summary", {})
    pass_delta = sb.get("pass_rate", 0.0) - sa.get("pass_rate", 0.0)
    regression = -pass_delta if pass_delta < 0 else 0.0
    # Decide verdict honoring max_regression if provided.
    if regression > 0 and max_regression is not None and regression <= max_regression:
        verdict = "within_threshold"
    elif pass_delta > 0:
        verdict = "improved"
    elif pass_delta < 0:
        verdict = "regressed"
    else:
        verdict = "unchanged"
    return {
        "a": {"path": a_path, "pass_rate": sa.get("pass_rate")},
        "b": {"path": b_path, "pass_rate": sb.get("pass_rate")},
        "pass_rate_delta": round(pass_delta, 4),
        "regression": round(regression, 4),
        "allowed_regression": max_regression,
        "verdict": verdict,
    }


__all__ = [
    "CaseResult",
    "DatasetError",
    "EvalCase",
    "EvalReport",
    "GRADER_REGISTRY",
    "ModelProvider",
    "compare_reports",
    "load_dataset",
    "register_grader",
    "run_eval",
]
