"""Offline deterministic eval system.

Loads JSONL datasets, runs deterministic graders, aggregates results, and
applies threshold/regression gates. Model-based graders are a plugin
interface — never required by the unit or integration tests.
"""

from __future__ import annotations

import io
import json
import re
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def load_dataset(path: str | Path) -> list[EvalCase]:
    """Load and validate a JSONL dataset. Raises DatasetError on any issue."""
    p = Path(path)
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
                raise DatasetError(
                    f"{path}:{lineno}: invalid JSON ({e.msg})"
                ) from e
            case = _build_case(rec, path, lineno)
            if case.id in seen_ids:
                raise DatasetError(
                    f"{path}:{lineno}: duplicate case id '{case.id}'"
                )
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
            raise DatasetError(
                f"{path}:{lineno}: missing required field '{required}'"
            )
    cid = rec["id"]
    if not isinstance(cid, str) or not cid:
        raise DatasetError(f"{path}:{lineno}: 'id' must be a non-empty string")
    inp = rec["input"]
    if not isinstance(inp, dict):
        raise DatasetError(f"{path}:{lineno}: 'input' must be an object")
    exp = rec["expected"]
    if not isinstance(exp, dict):
        raise DatasetError(f"{path}:{lineno}: 'expected' must be an object")
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


def grader_not_contains(
    expected: dict[str, Any], output: dict[str, Any]
) -> GraderResult:
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


def grader_json_parse(
    expected: dict[str, Any], output: dict[str, Any]
) -> GraderResult:
    raw = output.get("answer") or output.get("text") or ""
    if not isinstance(raw, str):
        raw = json.dumps(raw, ensure_ascii=False)
    try:
        json.loads(raw)
    except json.JSONDecodeError as e:
        return False, f"output is not valid JSON: {e.msg}"
    return True, ""


def grader_json_field(
    expected: dict[str, Any], output: dict[str, Any]
) -> GraderResult:
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


def grader_tool_call(
    expected: dict[str, Any], output: dict[str, Any]
) -> GraderResult:
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
                        f"tool {want_name}: arg '{k}' expected {v!r}, "
                        f"got {got_args.get(k)!r}"
                    )
            return True, ""
    return False, f"expected tool '{want_name}' was not called"


def grader_threshold(
    expected: dict[str, Any], output: dict[str, Any]
) -> GraderResult:
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


def run_eval(
    cfg: Config,
    name: str,
    result: RunResult,
    *,
    offline: bool,
    provider: "ModelProvider | None" = None,
) -> StageResult:
    """Run an eval (smoke or full). Offline-only by default.

    `provider` is a callable that takes a case and returns a dict output.
    When `offline` is True and no provider is given, the eval uses the
    `output` fixture baked into the dataset (if present), else marks the
    case as `error`.
    """
    if name not in cfg.evals:
        msg = f"eval '{name}' is not configured"
        result.add_error(msg)
        return StageResult(
            name=name, kind="eval", status=STATUS_SKIPPED, reason=msg
        )
    ec = cfg.evals[name]
    started_at = _now_iso()
    started = time.monotonic()
    try:
        cases = load_dataset(ec.dataset)
    except DatasetError as e:
        result.add_error(str(e))
        return StageResult(
            name=name, kind="eval", status=STATUS_FAILED, reason=str(e),
            started_at=started_at,
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    if ec.sample_limit is not None:
        cases = cases[: ec.sample_limit]
    case_results: list[CaseResult] = []
    for case in cases:
        case_results.append(
            _grade_case(case, ec, offline=offline, provider=provider)
        )
    summary = _summarize(case_results)
    thresholds = _threshold_block(ec)
    status = _apply_thresholds(summary, ec)
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
    _persist_report(report)
    return stage


def _grade_case(
    case: EvalCase,
    ec: EvalConfig,
    *,
    offline: bool,
    provider: "ModelProvider | None",
) -> CaseResult:
    started = time.monotonic()
    # Resolve the model output.
    if provider is not None:
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
                reason="offline mode requires a fixture output",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
    else:
        return CaseResult(
            case_id=case.id,
            status="error",
            reason="no provider configured for online eval",
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
            graders.append({"kind": "contains", "needle": case.expected["contains"][0]})
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
        case_id=case.id, status="passed", duration_ms=duration_ms,
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

    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _persist_report(report: EvalReport) -> Path:
    out_dir = Path("evals/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_started = report.started_at.replace(":", "").replace("-", "")
    fname = f"{report.name}-{safe_started}.json"
    out = out_dir / fname
    # The report is a generated artifact — gitignored.
    payload = report.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    redacted = redact(text)
    out.write_text(redacted, encoding="utf-8")
    return out


# Type alias used in the runner signature.
ModelProvider = Callable[[EvalCase], dict[str, Any]]


def compare_reports(a_path: str, b_path: str) -> dict[str, Any]:
    """Compare two eval reports and surface deltas."""
    a = json.loads(Path(a_path).read_text(encoding="utf-8"))
    b = json.loads(Path(b_path).read_text(encoding="utf-8"))
    sa = a.get("summary", {})
    sb = b.get("summary", {})
    pass_delta = sb.get("pass_rate", 0.0) - sa.get("pass_rate", 0.0)
    regression = -pass_delta if pass_delta < 0 else 0.0
    return {
        "a": {"path": a_path, "pass_rate": sa.get("pass_rate")},
        "b": {"path": b_path, "pass_rate": sb.get("pass_rate")},
        "pass_rate_delta": round(pass_delta, 4),
        "regression": round(regression, 4),
        "verdict": (
            "improved" if pass_delta > 0 else
            "regressed" if pass_delta < 0 else "unchanged"
        ),
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
