"""Policy: exit codes, security enforcement, tool allowlist."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import SecurityConfig


# Coarse exit codes are part of the contract — do not renumber.
EXIT_SUCCESS = 0
EXIT_VALIDATION = 1
EXIT_STAGE_FAILED = 2
EXIT_POLICY_BLOCKED = 3
EXIT_INTERNAL = 4
EXIT_SKIPPED = 10  # all-or-partial skipped without --allow-skipped
EXIT_USAGE = 64    # arg parsing / usage error


class PolicyError(Exception):
    """Raised when a security policy blocks an action."""


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = ""


def check_tool_allowed(tool: str, security: SecurityConfig) -> PolicyDecision:
    """Enforce the tool allowlist. Empty allowlist => nothing allowed."""
    if tool not in security.tool_allowlist:
        return PolicyDecision(
            allowed=False,
            reason=(
                f"tool '{tool}' is not in tool_allowlist "
                f"({sorted(security.tool_allowlist) or 'empty'})"
            ),
        )
    return PolicyDecision(allowed=True)


def check_write_requires_approval(
    action_kind: str, security: SecurityConfig
) -> PolicyDecision:
    """Return whether the given high-risk write kind needs human approval."""
    if action_kind in security.require_approval_for:
        return PolicyDecision(
            allowed=False,
            reason=(
                f"action kind '{action_kind}' requires explicit human approval "
                f"(in require_approval_for)"
            ),
        )
    return PolicyDecision(allowed=True)


def summarize_unmatched(
    declared: Iterable[str], observed: Iterable[str]
) -> tuple[list[str], list[str]]:
    """Return (declared-but-not-observed, observed-but-not-declared)."""
    decl = set(declared)
    obs = set(observed)
    return sorted(decl - obs), sorted(obs - decl)
