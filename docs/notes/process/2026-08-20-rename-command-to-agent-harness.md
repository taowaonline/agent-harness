# Rename command and skill to agent-harness

**Decision:** The user-facing command is `agent-harness` everywhere: the
repo entry script, pip console script, argparse prog / `--version` string,
all docs, CI workflows, eval prompts, and installer output. The skill name
(SKILL.md frontmatter + install directory under each CLI's `skills/`)
renames in lockstep, so the Claude Code slash command becomes
`/agent-harness` and setup.js links `skills/agent-harness`. The Python
package/import name `src/agent_harness/` and the dist name `agent-harness`
are unchanged.

**Why:** One spelling for everything users type — repo directory, command,
skill, slash command, npm package — instead of a hyphen/underscore split
across surfaces. The underscore form existed only as a Python-identifier
habit; no tool requires it at the CLI boundary. Renaming the import name
too would churn every `from agent_harness...` for zero user-visible gain,
so the boundary is drawn at the command surface.

**How to apply:** Breaking rename → version bumped 0.1.0 → 0.2.0 in both
`package.json` and `src/agent_harness/__init__.py` (version-sync contract
from the npm distribution note). Consumers must re-run setup (old
`skills/agent_harness` links are not migrated automatically — uninstall
with 0.1.x first, then install 0.2.0). New user-facing strings must use
`agent-harness`; new Python modules stay under the `agent_harness` package.
Historical archives (`HARNESS_*_REVIEW.md`, dated post-mortems) keep the
old spelling on purpose.
