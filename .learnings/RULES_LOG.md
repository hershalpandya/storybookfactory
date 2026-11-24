# Toolkit rules

Record the rule, generic evidence, the test or reproduction, and where the rule was implemented. Keep story evidence with local project records.

- Verify reordered pytest runs with a nonempty list of node IDs and verbose output. Pass the IDs in a pytest argument file to preserve spaces and brackets.
- Use in-process CLI tests for command behavior and subprocess smoke tests for the entry points. See `tests/support.py` and `tests/test_cli.py`.
- Render recurring set layouts from one set plan for each camera. Check art against the declared objects and positions using `edition set-score`.
- Inspect reference crops and use an approved neighbour from a different set or camera when one is available. Use localized edits for small surface changes and check drift outside the edit region.

## Recurring settings need a staged layout before generation

- Rule: declare the setting on each recurring story illustration, then render and stage the local perspective view before the dry run. Use the layout for composition and comparison artwork for identity and style.
- Enforcement: edition preflight, Gemini dispatch and manual art reservation verify the staged page, plan and attachment.
- Verification: the recurring-set CLI regression exercises missing, stale and correctly attached layouts without a paid call.
