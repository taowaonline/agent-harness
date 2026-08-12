# Graders

Project-specific graders live here. Each grader is a Python callable that
takes `(expected, output)` and returns `(bool, reason)`.

Register one with:

```python
from agent_harness.evals import register_grader


def my_grader(expected, output):
    ...
    return ok, reason


register_grader("my_kind", my_grader)
```

Reference a registered grader from a dataset record via:

```json
{"expected": {"graders": [{"kind": "my_kind", "...": "..."}]}}
```

See `src/agent_harness/evals.py` for the built-in graders (exact, contains,
regex, json_parse, json_field, tool_call, threshold).

## Guidelines for model-based graders

A model-judge grader is a powerful tool, but it brings its own risks:

- Pin the judge prompt and judge model.
- Sample at least 5% of judge decisions for human review.
- Do not let the same model judge its own outputs without calibration.
- Run with `repetitions >= 3` for non-deterministic judgments.

See `docs/evaluation-policy.md` for the full rules.
