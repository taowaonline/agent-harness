"""Built-in security check.

This stage audits the project's *security posture* — it does not run secret
scanning tools like `gitleaks` or `trufflehog` for the user (those are
external tools), but it:

  - Validates the configured `[security]` policy is sane.
  - Confirms redaction works on a synthetic secret sample.
  - Walks the repo looking for likely-committed secrets using a conservative
    regex set (defense in depth — never the only check).
  - Reports findings as a structured StageResult.

External secret/dependency scanners are integration points. `doctor` reports
their availability; this built-in does not depend on them.
"""

from __future__ import annotations

import time
from pathlib import Path

from .config import Config
from .redaction import redact
from .result import (
    STATUS_BLOCKED,
    STATUS_FAILED,
    STATUS_PASSED,
    RunResult,
    StageResult,
)

# Directories we never scan for secrets (build artifacts, vcs, etc.)
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    "target",
    ".next",
    "evals/reports",   # generated artifacts; redacted at write time
    "evals/baselines", # checked-in reports; redacted at write time
}

# File extensions we read for the secret scan.
# Markdown is intentionally excluded — documentation routinely mentions
# `api_key=`, `Bearer`, etc. as part of explaining the patterns. Real
# secrets in committed source files (.py, .ts, .go, etc.) are still
# caught.
_TEXT_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".kt",
    ".cs", ".rb", ".php", ".c", ".cc", ".cpp", ".h", ".hpp", ".swift",
    ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".conf",
    ".env", ".sh", ".bash", ".zsh",
    ".txt", ".sql",
}

# Synthetic secret sample used to verify redaction works at all.
# Constructed at module load so the literal never appears in source —
# keeps GitHub secret scanning happy while still exercising the regex.
_STRIPE_TEST_KEY = "sk_test_" + "a" * 28
_REDACTION_PROBE = (
    "Authorization: Bearer abcdef.GHIJKLM.nopqrst\n"
    f"api_key={_STRIPE_TEST_KEY}\n"
)


def run_security_check(cfg: Config, result: RunResult) -> StageResult:
    started = time.monotonic()
    stage = StageResult(name="security", kind="check")
    findings: list[str] = []
    # Advisory findings are surfaced in metrics but do not flip the stage
    # status to failed. Used for cases where the policy is intentionally
    # minimal (e.g. a non-AI project with no Agent tools to allowlist).
    advisory: list[str] = []

    # 1. Policy posture checks.
    # AI workloads (chat/rag/agent/extraction/code-agent) expose Agent
    # tools, so an empty allowlist is a real risk. Non-AI projects
    # (workload = "other") have nothing to allowlist — empty is correct.
    ai_workloads = {"chat", "rag", "agent", "extraction", "code-agent"}
    if not cfg.security.tool_allowlist:
        if cfg.project.workload in ai_workloads:
            findings.append(
                "[policy] tool_allowlist is empty for an AI workload — "
                "Agent tools default to deny-all, which may be tighter "
                "than intended"
            )
        else:
            advisory.append(
                "[policy] tool_allowlist is empty (acceptable for "
                "non-AI workload 'other')"
            )
    if "external_write" not in cfg.security.require_approval_for:
        findings.append(
            "[policy] 'external_write' is not in require_approval_for"
        )
    if "delete" not in cfg.security.require_approval_for:
        findings.append("[policy] 'delete' is not in require_approval_for")

    # 2. Redaction smoke test — confirm the patterns actually fire.
    redacted = redact(_REDACTION_PROBE)
    if "Bearer" in redacted or _STRIPE_TEST_KEY in redacted:
        findings.append(
            "[redaction] probe failed — redaction patterns let a secret through"
        )

    # 3. Repo secret scan (best-effort, walks the working tree).
    leaked = _scan_repo_for_secrets(scan_exclude=cfg.security.scan_exclude)
    if leaked:
        for hit in leaked[:10]:
            findings.append(f"[secret-scan] {hit}")
        if len(leaked) > 10:
            findings.append(
                f"[secret-scan] ...and {len(leaked) - 10} more"
            )

    stage.metrics = {
        "findings_count": len(findings),
        "advisory_count": len(advisory),
        "advisory": advisory,
        "policy_checks": {
            "tool_allowlist_size": len(cfg.security.tool_allowlist),
            "require_approval_for": list(cfg.security.require_approval_for),
            "redact_inputs": cfg.security.redact_inputs,
            "redact_outputs": cfg.security.redact_outputs,
            "scan_exclude": list(cfg.security.scan_exclude),
        },
    }
    if findings:
        stage.status = STATUS_FAILED
        stage.reason = f"{len(findings)} security finding(s)"
        for f in findings:
            result.add_error(f"security: {f}")
    else:
        stage.status = STATUS_PASSED
    stage.duration_ms = int((time.monotonic() - started) * 1000)
    return stage


def _scan_repo_for_secrets(scan_exclude: list[str] | None = None) -> list[str]:
    """Walk the working tree, return human-readable hits for likely secrets.

    `scan_exclude` is a list of glob patterns matched against the path
    relative to project root (forward slashes). Matches skip the file
    entirely. Use this for vendored dictionaries, generated code, large
    text corpora that over-fire the secret patterns.
    """
    hits: list[str] = []
    root = Path.cwd()
    # Use the same secret patterns as redaction but report the file:line.
    from .redaction import _SECRET_PATTERNS

    excluded = _compile_exclude_patterns(scan_exclude or [])

    for path in _walk_text_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(root))
        # Honor user-supplied scan_exclude patterns first.
        if _matches_exclude(rel, excluded):
            continue
        # Skip fixture/test files: they legitimately contain secret-shaped
        # strings used to exercise the redactor and graders.
        if (
            "/tests/" in rel
            or "/testfiles/" in rel
            or "/evals/datasets/" in rel
            or rel.startswith("tests/")
            or rel.startswith("evals/datasets/")
            or rel.startswith("examples/")
        ):
            continue
        # Skip the harness's own redaction module — it literally contains
        # the patterns used to detect secrets. Same for the security
        # module, which contains a synthetic redaction probe.
        if rel in ("src/ai_harness/redaction.py", "src/ai_harness/security.py"):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat in _SECRET_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                hits.append(
                    f"{rel}:{lineno}: pattern "
                    f"'{pat.pattern[:40]}...' matched"
                )
                break
    return hits


def _walk_text_files(root: Path):
    for dirpath, dirnames, filenames in __import__("os").walk(root):
        # Prune skipped dirs in-place so os.walk doesn't descend.
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() in _TEXT_EXT:
                yield p


def _compile_exclude_patterns(patterns: list[str]) -> list[str]:
    """Return patterns as-is (already strings); helper exists for symmetry
    with future regex/anchor support. For now we use fnmatch per-pattern."""
    return list(patterns)


def _matches_exclude(rel_path: str, patterns: list[str]) -> bool:
    """Return True if rel_path matches any of the user's exclude patterns.

    Supports both glob semantics:
      - `tools/data-sources/**` matches everything under that dir
      - `*.min.js` matches anywhere
      - `tools/dict.txt` matches only that exact path
    """
    import fnmatch

    norm = rel_path.replace("\\", "/")
    for pat in patterns:
        p = pat.replace("\\", "/")
        # Directory-tree glob: `dir/**` matches `dir/anything/...`.
        # Keep the trailing slash so "tools/**" only matches paths under
        # tools/, not "tools_meta/x.py".
        if p.endswith("/**"):
            prefix = p[:-2]  # "tools/**" -> "tools/"
            if norm.startswith(prefix):
                return True
            # Also accept `dir` exactly (no slash).
            if norm == p[:-3]:
                return True
            continue
        # `dir/` (trailing slash without **) matches everything inside.
        if p.endswith("/"):
            if norm.startswith(p):
                return True
            continue
        # Plain fnmatch against the full path or any path segment.
        if fnmatch.fnmatch(norm, p):
            return True
        # Also match against just the basename, so `*.min.js` works on
        # nested paths like `vendor/lib/foo.min.js`.
        if "/" in norm and fnmatch.fnmatch(norm.rsplit("/", 1)[-1], p):
            return True
    return False
