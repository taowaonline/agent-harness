# Entry distribution model

**Decision:** The `agent_harness` entry script resolves the package in a
fixed order — `<script dir>/src`, then `$HARNESS_HOME/src`, then bare
`import agent_harness` — with no hardcoded canonical path anywhere. The
default install model is *global CLI*: target projects commit only
`harness.toml` + `harness.schema.json`, and contributors install the CLI
globally. `init --vendor` is the opt-in that additionally copies
`src/agent_harness/` alongside the entry for self-contained installs.

**Why:** The original entry embedded
`_CANONICAL_HOME = "/Users/tommacmini4/..."`. That made every
`harness init` product machine-bound: a clone on any other machine (or
CI) failed with `cannot find ai_harness package`, while the origin
machine stayed green — so local success proved nothing about
distributability (SECOND_REVIEW P0.1, FIFTH_REVIEW P0.2). Deleting the
fallback forced the failure mode to be honest; the isolated-copy test
(`skipped_semantics_test.py::test_entry_runs_in_isolated_copy`, which
copies script+src to a tempdir and unsets `HARNESS_HOME`) now locks the
guarantee. Global-CLI default was chosen over always-vendoring after the
Local_CICD integration: committing a wrapper that hardcodes one machine's
path helps nobody, while `harness.toml`-only keeps the project contract
clean and the install story one line.

**How to apply:** Never reintroduce a canonical path or any
machine-specific default. New resolution steps must fail with actionable
instructions, not guess. If a project needs to be clone-and-run, that is
`--vendor` territory — keep the two models distinct and document which
one a project chose in its README.
