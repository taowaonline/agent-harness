"""Secret and sensitive-value redaction.

Used for: log lines, dry-run argv previews, eval reports, error messages.
The goal is *defense in depth* — never the only line of defense. We never
log raw model output, raw user input, or known-sensitive env vars.
"""

from __future__ import annotations

import os
import re
from typing import Iterable

# Patterns that detect common secret formats. Conservative: redact on match
# even if the surrounding text is benign — false positives in logs are cheap,
# secret leaks are not.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Bearer tokens — checked before the generic auth= pattern so the
    # `Authorization: Bearer <token>` form is fully redacted.
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-/+=]+"),
    # Generic key=value style: api_key=..., token=..., secret=...
    re.compile(
        r"(?i)\b(api[_-]?key|secret|token|password|passwd|authorization|"
        r"auth[_-]?token|access[_-]?key|private[_-]?key|client[_-]?secret|"
        r"refresh[_-]?token)\b\s*[:=]\s*[^\s,;'\"]+"
    ),
    # AWS access key id
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    # AWS secret access key (40-char base64-ish)
    re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+]{40}(?![A-Za-z0-9/+=])"),
    # GitLab/GitHub PATs
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"),
    # Slack tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]+\b"),
    # JWT (header.payload.signature, each segment >=4 base64 chars)
    re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b"),
    # Google API key
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    # Stripe
    re.compile(r"\b(sk|pk|rk)_(live|test)_[0-9a-zA-Z]{24,}\b"),
)

# Env var names whose values must never be logged.
_SENSITIVE_ENV_SUBSTRINGS = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
)

_REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    """Replace secret-like substrings with ***REDACTED***."""
    if not text:
        return text
    redacted = text
    for pat in _SECRET_PATTERNS:
        redacted = pat.sub(_REDACTED, redacted)
    return redacted


def redact_argv(argv: Iterable[str]) -> list[str]:
    """Redact secret-like argv elements. Whole elements only — never partial."""
    return [redact(arg) for arg in argv]


def is_sensitive_env_var(name: str) -> bool:
    upper = name.upper()
    return any(sub in upper for sub in _SENSITIVE_ENV_SUBSTRINGS)


def safe_env_for_logging(env: dict[str, str]) -> dict[str, str]:
    """Return env suitable for inclusion in a log/eval record."""
    return {k: (_REDACTED if is_sensitive_env_var(k) else v) for k, v in env.items()}


def redact_env_for_subprocess(env: dict[str, str] | None) -> dict[str, str]:
    """Build the env passed to subprocess.run.

    Inherits the parent env so commands work; never strips secrets from
    the actual subprocess env (the subprocess may need them) — this is only
    used to construct a clean inherited env when explicitly overriding.
    """
    base = dict(os.environ)
    if env:
        base.update(env)
    return base
