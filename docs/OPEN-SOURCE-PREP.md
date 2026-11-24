# Public repository boundary

The shared repository contains toolkit source, tests, documentation, agent skills and neutral examples. Keep real transcripts, adaptations, art, prompts, reviews and output proofs under the ignored `projects/` directory or outside the checkout. Save agent reports, working documents and handoffs under ignored `reports/`. Use ignored `local-references/` for local reference material. Back up private work separately.

Keep credentials in the environment or a supported credential store. Keep project names, story details and local paths out of issues, pull requests and CI artifacts. Reduce reports to a synthetic example when possible. See the [security policy](../SECURITY.md) for private reporting.

Before pushing, inspect the staged diff and run:

```sh
uv run --locked pytest tests/test_public_tree.py
```

This check rejects tracked files in the private directories and checks toolkit text for common personal paths and email addresses. Maintainers can add project-specific terms as regular expressions in a local `reports/private-terms.txt` to check an export against their own private material. Keep that file in the ignored directory. Review staged images, binary assets, filenames and history separately; the text scan cannot establish what those contain.

If migrating from a private Git repository, copy a reviewed tree into a separate public checkout. Private Git history can retain deleted material and must stay in the private repository.
