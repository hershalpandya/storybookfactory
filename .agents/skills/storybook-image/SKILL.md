---
name: storybook-image
description: Use before and during any image provider call for a storybook — root character/prop profiles, scene illustrations, colouring graphics or targeted edits. Covers set preflight, attempt journaling, frozen checklists, pixel review and the retry limit that keeps image rounds cheap.
---
# Storybook image workflow

Use the provider named in the owner's plan. For editions, use `storybook edition gemini` for Gemini or the `edition art-*` journal commands for an externally operated provider. Start with a dry run and follow `docs/EDITIONS.md`. Keep the private story, references, prompts and results in the owner's chosen local project; send images to a provider only under the owner's existing authorization.

For a fresh edition scene, follow this order.

1. Declare every story illustration's setting in the import index or a stage revision. Use the same setting ID across a recurring setting and give a reason for a standalone scene.
2. Render and stage each recurring shot with `edition set-layout EDITION set-plans/SETTING.json PAGE NEW_OUTPUT --stage`. Inspect the camera, fixture count and order, and the intended visible actors. Write separate checks for exact actions and partial occlusion.
3. Read `edition next` and inspect the dry-run attachments. The staged layout controls composition. Comparison images guide identity and style. Record the director review after staging, then dispatch under the approved budget.
4. Review the capture with `storybook image-checklist`, using a crop where a detail is unclear. Assign a current passing attempt and record the separate visual review.

Build profiles and scenes using `docs/SCENE-ASSETS.md`. Create distinct root PNGs after describing each character and prop and declaring their conditions and views. Look at the profiles side by side. Check identity, state, anatomy, construction and stable set details before storing any approved reference.

Before a scene call, review the approved passage, set layout, camera, staging, cast and props against local profiles and adjacent scenes. Inspect each subject's planned part counts and visibility. Count two legs for a hen, four for a sheep, and the declared parts for insects, machines and props. Side views may overlap paired parts, and props or framing may hide them. Verify how each part lines up and attaches from the planned viewpoint. Review the colouring pose and use a separate placement when it needs a different profile or visibility. Check that the right character performs the action and that objects connect and move as planned. For a rope mechanism, follow one continuous path from attachment through pulley to free end. In a legacy scene project, use `set-preflight` and record the evidence with `review-set`. In an edition, inspect `scene-handoff` and the compiled slot checks.

For legacy scene projects, freeze cases with `benchmark-start`. Open each provider call with `attempt-start`, use the prompt and ordered input files in its `provider_payload`, and save the returned bytes with `attempt-finish` before review. When passing binary data by pipe, use `--stdin`. Use `--resume` when intake finished and the process stopped during screening. Use `image-checklist` and inspect it at usable size in a fresh review pass. Look for duplicate or detached limbs, profile drift, changes in relative size, missing doors or interior fixtures and unplanned characters. Record the facts actually seen with `review-image`. Check uncertain features at full size and record remaining uncertainty. Register the PNG only after its review passes.

In a legacy scene project, record transfer failures in the run with `attempt-finish --error`. Track root profile calls in a separate profile run. Record the actual time spent reviewing when available. For a localized defect, open a new journal entry with `--parent` and `--edit-prompt`. Specify the single change and preserve successful features. If the overall action or staging fails, revisit the set review. After two failures on the same issue, reassess the composition or record the blocker. Respect the user's credit budget. Keep the run manifest, prompts, references, unsuccessful candidates and reviews for comparison with the next book.

For an edition manifest, use `scene-handoff` and `image-checklist` on the
edition directory. See `docs/EDITIONS.md` for Gemini dry runs, review
dependencies, budget, pause and reconciliation. Match the provider named in the
current owner's plan. A failed or paused provider call requires an explicit
owner decision before dispatching with a different provider.

When text names a physical contact, add a separate `visual_checks` entry and choose a camera that shows both sides of the contact. For a group, list the members in order with individual identity marks. Check the count separately from identity and shape.

Inspect every attachment before a fresh call. Use clean references that show the intended subject, style and condition. If an approved neighbour page is available, prefer one from a different set or camera angle. For a fresh cast, make a cast sheet and a clean set reference, then compose the exact roster needed for each page. Use `edition set-score` when measuring agreement with the planned view.

Use a targeted edit for a local surface change. Describe the intended change and name adjacent identity marks or connected parts that must remain visible. Restage when the camera, action or connections need to change. Use the region drift check when editing an assigned page. Review line weight on colouring pages alongside their neighbours.

After an HTTP failure, read the recorded provider error and determine whether the request was accepted before resuming. For Gemini, use the journal's pause and reconciliation workflow in `docs/EDITIONS.md`.

For manually operated providers, freeze the recurring identity, anatomy and
construction checks in the edition brief. Review the dry-run packet before
dispatch. Use `edition art-status` to resume interrupted work. Carry all
frozen checks into a targeted edit and verify the result against the original
and relevant neighboring pages. Record the visible cause and next tactic
before opening the next small round.
