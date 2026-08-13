## Summary

<!-- What does this change do, and why? One or two sentences. -->

## Acceptance criteria

<!-- Bullet list of verifiable criteria. Each item should be checkable by
a test, eval case, or manual step. Link the issue if applicable. -->

- [ ] ...
- [ ] ...

## Test evidence

<!-- Commands you ran and their results. Attach eval report paths if this
change affects AI behavior. Do not paste secrets. -->

```bash
./agent_harness validate
./agent_harness run check
./agent_harness eval smoke --offline
```

## AI behavior change

<!-- Check all that apply. If any box is checked, an eval sample must
accompany the change. -->

- [ ] Prompt changed (version bumped in `prompts/`)
- [ ] Model or model parameters changed (provider, snapshot, temperature, etc.)
- [ ] Tool definition changed (input schema, allowlist, or permissions)
- [ ] Retrieval configuration changed
- [ ] No AI behavior change

## Eval baseline delta

<!-- If you ran `eval full` before and after, paste the comparison. -->

```bash
./agent_harness baseline compare evals/baselines/<prev>.json evals/reports/<new>.json
```

## Safety / privacy / cost / latency impact

<!-- One line each. "No change" is an acceptable answer. -->

- Safety:
- Privacy:
- Cost:
- Latency:

## Rollout & rollback

<!-- How is this shipped and how is it rolled back if it breaches a gate? -->
