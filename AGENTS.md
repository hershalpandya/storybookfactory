# Storybook Factory agent instructions

This Python toolkit turns reviewed English transcripts into illustrated French CE1 storybooks. Start with [README.md](README.md) for story setup and [CONTRIBUTING.md](CONTRIBUTING.md) for code, testing, and when to use each skill.

## Working rules

- Keep real transcripts, references, journals, reviews, and outputs under ignored `projects/` or outside Git. Put agent reports, working documents and handoffs in ignored `reports/`. Keep story details and credentials out of public fixtures, docs, skills and logs. Use synthetic examples such as Pip and the Kite.
- Obtain the owner's authorization before sending story material to an external provider. A back-cover image marked private stays local.
- Use fresh output directories. Keep failed image attempts and their reviews. Record each provider call and capture before reviewing. Report only reviews, image calls, audio checks and physical proofs that occurred.
- Validate current evidence before reusing approval records. Use `check-adaptation`, `check-assets` and the applicable edition or layout preflight.
- Run `uv run --locked pytest` before committing. Update docs for behavior changes and run the offline example when the story workflow changes. Follow the [public repository boundary](docs/OPEN-SOURCE-PREP.md) before pushing.

## Code boundaries

- `store.py` owns storage, hashing, errors and write locking. Import their helpers from there. `sources.py` owns transcript, story and adaptation reviews.
- `cli.py` wires command modules through `register(subparsers)` and exposes `main(argv=None)`. Use `tests/support.py` for in-process CLI tests and `tests/conftest.py` for shared fixtures. Test modules do not import each other.
- `journal.py` owns attempts and pauses. `generation.py` owns dispatch gates and budget policy. `providers/gemini_http.py` implements the Gemini adapter behind the provider protocol. Avoid automatic provider fallback.
- `edition/` owns versioned editions. Add revision operations to `OPERATIONS` in `edition/revise.py` and document them in [docs/EDITIONS.md](docs/EDITIONS.md). Access older scene-plan projects from edition code through `legacy.export_for_edition`.
- `render.typeset` is the shared typesetting entry point for all workflows. Keep the version in `pyproject.toml`.

## Skills

Edit first-party skills under `.agents/skills/`. The Claude entry point uses the same directory. `storybook export-workflow` copies the two product skills, guides and agent entry notes into a new directory.

- For story work, read [storybook](.agents/skills/storybook/SKILL.md) first and [storybook-image](.agents/skills/storybook-image/SKILL.md) before image calls. Use [consistency-auditor](.agents/skills/consistency-auditor/SKILL.md) for artwork review and [self-improve](.agents/skills/self-improve/SKILL.md) for recurrent issues.
- For tests, use [test-audit](.agents/skills/test-audit/SKILL.md). For module boundaries, use [improve-codebase-architecture](.agents/skills/improve-codebase-architecture/SKILL.md). For focused security review, use relevant [security-audit](.agents/skills/security-audit/SKILL.md) guidance. Keep third-party skills pinned with their licenses and source references.
- Record story-specific lessons privately in `reports/learnings/`. Share reusable toolkit lessons in `.learnings/` with the verification and the resulting rule or check.
