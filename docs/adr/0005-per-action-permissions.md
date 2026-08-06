# ADR 0005 — Per-action-kind permissions, not an admin flag

Status: Accepted
Date: 2026-08-02

## Context

A single `admin=true` permission is convenient but dangerous — once
granted, it covers reads, writes, deletes, deploys, and payments. There
is no way to scope or audit it.

## Decision

Model permissions per action kind: `read-only`, `external_write`,
`delete`, `payment`, `deploy`, `network_egress`, `privileged`. Tools
declare their kind; the runtime consults
`[security].require_approval_for` to decide whether to block.

## Consequences

- **Pro:** Privilege is auditable per tool.
- **Pro:** A breach in one tool does not implicitly grant others.
- **Con:** More configuration surface. The profiles under
  `profiles/risk/` give sensible defaults.
