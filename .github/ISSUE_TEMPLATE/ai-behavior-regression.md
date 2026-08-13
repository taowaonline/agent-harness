---
name: AI behavior regression
about: Report an AI quality, safety, or tool-behavior regression
labels: ["ai-quality", "needs-triage"]
---

## Affected behavior

<!-- Which prompt id/version, model, tool, or workload? -->

## Symptom

<!-- What did the model/agent do wrong? Include the input class and the
failing output class. -->

## Evidence

- Eval report: `evals/reports/<name>.json`
- Trace_id (if production): ...
- Reproduction case (must be redacted before pasting):

```json
{"id":"...","input":{"query":"..."},"expected":{"...":"..."}}
```

## Baseline comparison

```bash
./agent_harness baseline compare evals/baselines/<prev>.json evals/reports/<new>.json
```

## Proposed remediation

<!-- Fix forward, add a regression sample, or roll back the model/prompt?
Add the proposed regression case id below. -->
