# Review-driven iteration

**Decision:** Substantive changes to this repo land through numbered
review documents (`HARNESS_*_REVIEW.md`, later
`HARNESS_CURRENT_CHANGE_QUALITY_EVALUATION.md`): each round audits HEAD
with reproducible commands, classifies findings (P0/P1/P2, later R1–R5),
and the next implementation pass closes them with regression tests in
the same commit. Quick-win items (cheap, evidence-backed fixes) are
burned down before strategy items (Runner protocol, Profile loader).

**Why:** The alternative — one large implementation against a static
brief — produced exactly what the first review predicted: an
architecture-shaped repo where the sixth review found that a TOML field
was parsed and dropped (`runner`), malformed runner output could pass,
and `--strict` was dead code. Each review round caught the *previous*
round's regressions cheaply because every finding carried a one-line
reproduction; every fix carried its test. The rhythm (audit → classify →
fix-with-locked-regression → re-audit) is the actual product of the
review docs, more than any single finding.

**How to apply:** After a body of work, write the next numbered review
against HEAD with commands actually run — claims without command output
get discounted. When findings land, quick-wins first, one logical
commit per finding-class, and the regression test that proves the fix
belongs in the same commit. Post-mortem-worthy incidents get promoted
from review prose into `docs/postmortem/` so they stop being review-round
local knowledge.
