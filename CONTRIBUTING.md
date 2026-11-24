# Contributing to Storybook Factory

## Develop from a checkout

Install [uv](https://docs.astral.sh/uv/) and use Python 3.11 or newer. From the repository root:

```sh
uv sync --locked
uv run --locked storybook --help
uv run --locked pytest
```

The tests use temporary projects and simulated provider responses. You can run them after dependency setup with provider keys unset. To verify a workflow change, run the affected test module and build the [offline example](examples/pip-and-the-kite/README.md). CI tests Python 3.11 and 3.14 and scans dependencies. When changing dependencies, update `uv.lock` and verify the locked sync in the same PR.

Keep agent reports, work notes and review drafts in ignored `reports/`. Keep story inputs, edition state and renders in ignored `projects/`.

## Find the right code

| Location | Responsibility |
| --- | --- |
| `src/storybook_toolkit/cli.py` | Wire CLI subcommands to their command modules |
| `src/storybook_toolkit/sources.py`, `catalog.py`, `world.py` | Reviewed source, adaptation, shared reference catalogs and continuity |
| `src/storybook_toolkit/edition/`, `legacy/` | Versioned editions and older scene-plan projects |
| `src/storybook_toolkit/generation.py`, `journal.py`, `providers/` | Provider policy, attempt records and network adapters |
| `src/storybook_toolkit/store.py`, `render.py` | Storage, shared typesetting and PDF output |
| `tests/`, `examples/`, `docs/` | Regression tests, the runnable sample, and reference material |

Use the shared fixtures in `tests/conftest.py`. Exercise CLI behavior through `tests/support.py` and keep real subprocess tests for entry-point contracts. Use neutral fixtures and inspect observable outputs such as exit codes, manifests and PDFs. When a bug needs a test, first reproduce it at the closest public boundary and verify that the test fails for the expected reason.

## Use skills during development

Read [AGENTS.md](AGENTS.md) at the start. Open the applicable skill before starting that kind of work.

| When | Skill and expected output |
| --- | --- |
| Change behavior or review a test | [OpenClaw test-audit](.agents/skills/test-audit/SKILL.md). Identify the independent contract and a regression the test catches. Use the pytest commands above for proof. |
| Diagnose a hard bug or flaky test | [Matt Pocock's diagnosing-bugs](https://github.com/mattpocock/skills/tree/main/skills/engineering/diagnosing-bugs). Use its reproduce-and-minimize steps to build a repeatable local check, then review new test coverage with test-audit. |
| Review the module structure | [Improve codebase architecture](.agents/skills/improve-codebase-architecture/SKILL.md). Identify where a simpler interface would help callers or tests before changing a boundary. |
| Change untrusted file handling, provider I/O or credentials | [Cloudflare security-audit](.agents/skills/security-audit/SKILL.md). Use the relevant review guidance and save audit reports under ignored `reports/`. |
| Work on a book or illustration round | [Storybook](.agents/skills/storybook/SKILL.md) for source through proof and [storybook-image](.agents/skills/storybook-image/SKILL.md) for provider calls and review. |
| Audit artwork or promote repeated lessons | [Consistency auditor](.agents/skills/consistency-auditor/SKILL.md) to log observed defects and [self-improve](.agents/skills/self-improve/SKILL.md) to turn recurring findings into guidance or tests. |

The vendored skills record their upstream sources in `SOURCE.md`. OpenClaw's broader testing workflows target its own stack. Use test-audit together with this repository's pytest workflow. The diagnosing-bugs guide is an upstream reference.

## Open a pull request

1. Update the example or reference docs if a command, file format or output layout changes.
2. Run `uv run --locked pytest` and inspect the staged files for private material. See the [public repository boundary](docs/OPEN-SOURCE-PREP.md).
3. Describe the behavior change and verification in the PR. Use `gh pr checks --watch` to follow CI and `gh run view RUN_ID --log-failed` for failure details.
