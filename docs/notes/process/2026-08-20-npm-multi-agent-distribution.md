# npm multi-agent distribution

**Decision:** The harness ships as one npm package
(`@taowaonline/agent-harness`) whose package root doubles as the skill
directory. A zero-dependency Node installer (`bin/setup.js`,
`npx @taowaonline/agent-harness setup`) wires the same SKILL.md into every
coding agent CLI, instead of maintaining per-CLI forks of the skill content:

- SKILL.md targets (symlink `skills/agent_harness` → package root):
  Claude Code `~/.claude/skills/`, Z.ai ZCode `~/.zcode/skills/`,
  Kimi Code `~/.kimi-code/skills/`, shared standard `~/.agents/skills/`,
  Deep Code `~/.deepcode/skills/` (best-effort path).
- Codex has no skill system → a managed, idempotent block in
  `~/.codex/AGENTS.md` (`adapters/agents-snippet.md`).
- Cursor → project-level rule copy `adapters/cursor-rule.mdc` →
  `.cursor/rules/agent-harness.mdc`.

**Why:** SKILL.md (name+description frontmatter) is the common format across
Claude Code, ZCode, Kimi, and Deep Code, so one skill body serves all of them
if the install target is a symlink to the package root — relative references
(docs/, profiles/, examples/) resolve exactly as they do for the source-repo
install. AGENTS.md is the only lever Codex offers, and Cursor rules are
per-project by design, so those two get adapters rather than symlinks.
Duplicating the skill per CLI would guarantee drift; a single body with
per-CLI *install* adapters keeps content authority in SKILL.md.

**How to apply:** Version bumps must move npm `version` and
`src/agent_harness/__init__.py` `__version__` together. New CLI support is a
row in setup.js's `SKILL_TARGETS` registry (or a new adapter file for
non-skill mechanisms), never a content fork. The npm `files` whitelist is the
publishing contract — anything new that the skill references at runtime
(datasets, profiles, docs) must be added there or the published package
breaks while the source repo passes its own gates.
