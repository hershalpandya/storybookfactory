---
name: self-improve
description: Use at the end of an image round or session, or when the same defect shows up again, to turn entries in .learnings/ERRORS.md into tested rules and promote them into skills, docs or CLI checks. Repo-maintenance skill, not exported.
---
# Self-improve

Goal: fewer image calls per accepted page. For scene runs the scorecard is `storybook benchmark-report` (first-pass acceptance and retries). Use `edition gemini-report` for Gemini rounds and `edition art-status` and the round journal for externally operated providers. A rule that does not improve these numbers is not worth keeping.

## Promotion ladder

Move each lesson up only as far as its evidence supports. Higher rungs are cheaper per session and work the same in Claude, Codex and Copilot.

1. **Log** — a single occurrence goes in the private `reports/learnings/ERRORS.md` (page, run id, what was seen, prompt pattern). The public `.learnings/` logs take only the generic lesson, with no story names, page text or family details.
2. **Rule** — when the same cause appears twice, or across two pages/books, write one concrete line in the relevant `.agents/skills/*/SKILL.md` or `docs/` file.
3. **Check** — when a rule can be verified mechanically (a count, a field, a hash, a required catalog view, a checklist item), implement it in the `storybook` CLI with a test, and shorten the prose rule to a pointer. Prefer this rung: code costs no tokens to obey.
4. **Always-on** — only rules every session needs go in `AGENTS.md`. Keep it short.

## Steps

1. Read `reports/learnings/ERRORS.md` (if present) and `.learnings/ERRORS.md`; group open entries by cause.
2. For each group, pick the rung its evidence supports and draft one rule.
3. Test it on the next real round or with a unit test. Compare `benchmark-report` before and after when an image round was involved. Record the actual result, including failure.
4. Promote it: edit the skill, doc or code. Never edit `.claude/skills` separately; it is a symlink.
5. Append to `.learnings/RULES_LOG.md` (rule, generic evidence, rung, test, promoted-to) and to `reports/learnings/RULES_LOG.md` (story evidence), and mark the source errors `promoted`. Rules written into skills, docs and code stay free of story material.
6. Demote or delete rules that turned out wrong or never fired; log that too.
