# Security policy

## Reporting a vulnerability

Email the maintainers directly. Do **not** open a public issue for a
security vulnerability.

- Include a clear description of the issue and a minimal reproduction.
- Do not include real secrets, real user data, or production logs.
- Allow up to 72 hours for an initial response.

## Disclosure

We follow coordinated disclosure. Once a fix is available, we publish a
GitHub Security Advisory and credit the reporter (unless they prefer to
remain anonymous).

## Scope

Vulnerabilities in:

- The harness control plane (`src/agent_harness/`).
- The example configs and CI workflows shipped in this repo.
- The redaction patterns and security gate logic.

Out of scope:

- Vulnerabilities in third-party tools the harness integrates with
  (gitleaks, pip-audit, etc.) — report those upstream.
- Vulnerabilities in projects that *use* this harness — those are the
  project's responsibility.

## Hardening checklist for projects adopting this harness

- [ ] `[security].tool_allowlist` is explicit and minimal.
- [ ] `[security].require_approval_for` includes every privileged kind
      the workload can perform.
- [ ] `[security].redact_inputs` and `redact_outputs` are both `true`.
- [ ] `gitleaks` (or equivalent) runs in CI.
- [ ] Dependency scanning (`pip-audit` / `npm audit` / `cargo audit`)
      runs in CI.
- [ ] At least one adversarial sample per workload class.
- [ ] Production traces do not log raw inputs or outputs.
- [ ] Secret rotation procedure is documented for every secret the
      project uses.
