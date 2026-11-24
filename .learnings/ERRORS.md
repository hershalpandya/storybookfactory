# Toolkit errors

Record reusable problems in the toolkit. Keep story-specific incidents, prompts and observed images in ignored `reports/` or alongside the associated attempt in `projects/`.

```text
## YYYY-MM-DD — short title
- Where: affected command, test or workflow
- Observed: reproducible behavior
- Cause and correction: evidence and result
- Status: open, fixed or promoted to RULES_LOG.md
```

## Reordered pytest runs silently used default order

- Observed: `pytest --collect-only -q -q` returned file counts, leaving the list of test IDs empty.
- Correction: use one `-q`, keep IDs one per line and use pytest's `@argfile` to preserve parametrized IDs. Check the order with `-v`.
- Status: promoted to RULES_LOG.md.

## Recurring-set layouts were rendered after the image calls

- Observed: the provider journal had style comparisons but no local layout attachment. A retrospective render exposed differences in landmark order and did not guide the original calls.
- Cause and correction: the instruction was advisory. Require staged layout evidence and the actual attachment for fresh recurring-setting scenes.
- Status: promoted to RULES_LOG.md.
