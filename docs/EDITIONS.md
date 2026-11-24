# Transcript-to-book editions

The toolkit starts from UTF-8 transcripts. The editor reconciles their wording and authors the event and visual briefs. The software preserves evidence, checks continuity and dependencies, assembles proofs, and gates production export.

## Start a book

```sh
storybook init projects/source
storybook register projects/source transcript-a.txt
storybook register projects/source transcript-b.txt
storybook compare projects/source
storybook review projects/source reconciled.json
storybook approve-adaptation projects/source french.json
storybook init-catalogs projects/source
storybook import-catalog-entry projects/source projects/previous characters lead
storybook edition import projects/edition projects/source edition-index.json metadata.json
storybook edition check projects/edition
storybook edition build projects/edition projects/edition/preview
```

All example project paths contain private material. The final two commands use the same frozen edition and typography as release. You can use the existing projects, source review, adaptation, root reference, catalog transfer, and asset commands without migrating them. Keep the old project available if it is the source of an import. Repeat the identical import to verify that the original revision is still present. Reimports preserve any newer active revision.

The private JSON import index contains ordered `events`, `pages` and `covers`, and optionally a `world` and a Gemini `generation` policy. The layout uses the packaged shaped Marelle 2 font, or a font from `--font`. Metadata follows [book rendering](BOOK-RENDERING.md). The edition copies source, transcript, adaptation, font and image bytes into content-addressed project-local files. `edition.json` identifies the active revision and `revisions/` holds historical manifests.

- Define each event with an `id`, `actor`, `action`, `speaker` and zero-based `source_passages`. Preserve disputed transcript readings and the editor's decision in the matching reviewed source passage. The reviewed-text export includes this evidence for each event.
- Define each story page with a stable `id`, ordered `events`, `text`, `annotations` and `art`. Annotation offsets are zero-based Unicode character offsets on the page text. Include the linked character as `target` in a sounded liaison. Every event must appear exactly once in story order.
- Supply `art.illustration` and `art.colouring` as separate objects with a `disposition` (`reuse`, `edit`, `new` or `unresolved`), `reason` and `brief`. Each brief needs an English `description`, an optional ordered `references` array of keys such as `characters/lead/summer/front`, and optional camera, movement, prop and blocking details. Give the colouring artwork its own pose and roster. Use `file` relative to the source project, `registered_page` to copy the corresponding asset from its registry, or leave it unassigned. Covers are keyed by `front` and `back`. Each has an `id`, the matching `role` and one illustration slot.
- Import qualifying series references with `import-catalog-entry` before building the index. Use the top-level `roots` map to add descriptive metadata keyed by catalog/subject/state/view, for example location, pose and crop. Use `permitted_uses` to restrict references. Include optional `comparison_references` on a brief to bind ordered existing art across pages. Each item specifies `page`, optional `kind` and a description of its `role`.
- Use [world declarations](WORLD-TIMELINE.md) for positions and continuity. A scene can track `transfers` with `item`, `from`, `to` and `reason` for an item declared in `initial_custody`. Transfers occur after the scene's movements and require a shared zone. Add a `required_custody` assertion when a scene depends on a delivery. Use named events and private data for locations, mechanisms and all story-specific facts.
- To import an independently reviewed adaptation for an owner proof, provide its project-relative `adaptation` path, `adaptation_sha256` and `language_reviewer_role`. Record the source approval separately. Carry the language artifact's real `human_approved` value and review identity.

The [offline example](../examples/pip-and-the-kite/README.md) shows how the source, edition and output directories fit together.

## Revise and review

```sh
storybook edition revise projects/edition operations.json
storybook scene-handoff projects/edition --page first --kind illustration
storybook image-checklist projects/edition first illustration candidate.png
storybook edition review projects/edition first/illustration --revision REVISION \
  --role visual --reviewer 'Review name' --decision approved --evidence 'Observed features'
storybook edition review projects/edition text --revision REVISION \
  --role independent-ai --reviewer 'Review name' --decision approved --evidence 'Checked wording, marks and shaped layout'
storybook edition build projects/edition projects/edition/release --final
```

A revision file contains the current `revision` digest, an `editor`, a `reason`, and ordered `operations`. Use `text` with `page`, `text` and `annotations`. Wording changes either supply new `briefs` or explain the unchanged visual meaning with `editorial_reason`. Use `root` with a root key, replacement `file` relative to the operation file, and review `evidence`. Every `file` an operation names must be a relative path that stays inside the edition directory or the operation file's own folder; absolute paths and `../` escapes are refused, so a revision file received from someone else cannot pull other files into the edition or into a provider request. Use `stage` to replace one slot brief, and `assign` with `page`, `kind`, `file`, `disposition` and `reason` after resolving an image.

Use `split` with the original `page` and two `parts`, each with `id`, `events`, `offset` and distinct `briefs` for both slot kinds. The first offset marks the end of the first part, and the second offset marks the start of the second part after any separating whitespace. Retain the original first-page ID. `carry` can list a still-relevant artwork kind in one split part. Use `merge` with `page`, the next page ID in `with`, the combined `text`, `annotations` and slot `briefs`. Use `reorder` with `pages` and, when the editor has deliberately changed event order, `event_order`. Use `unassign` with `page`, `kind` and a `reason` to start one slot again from its brief; the old image stays in `content/`. `layout` sets `keep_french_punctuation`; `generation` sets the Gemini policy; `missing_root` defines a reference sheet from source crops. Each operation is one function in the `OPERATIONS` table of `storybook_toolkit/edition/revise.py`. Include a corrected top-level `world` when operation changes affect transitions, visibility or page IDs.

An annotation update reopens text layout and owner proof review. For edits to art inputs the change report identifies the affected slots, comparison references and previous decisions. You can use role `director` to sign off the scene packet before any provider call. Use a named visual reviewer to observe actual pixels at use size. Record the owner's PDF decision separately with `edition review ... owner-proof --role owner` and the edition revision.

Run `storybook edition build EDITION --mode reading` to use the default output
location. A workspace writes each build to a dated folder in `outputs/previews/`
or, with `--final`, `outputs/final/`. A standalone edition has its own
`outputs/` directory. The build prints the folder path and includes a short
revision ID in its name. Pass a new output path as the second argument to
choose a different location. Keep cast sheets and rendered layout references
under `book-edition/artwork-preparation/` when they are part of a workspace.

The release gate requires every art slot to have a resolved, verified, uniquely assigned image and a current visual approval. It also requires a current text layout approval. The build writes reading and five print variants (`--mode` selects some), reviewed text and a proof report. An odd duplex edition adds an explicit reverse side before the back cover. Owner proof and actual physical print and sewing status are separately verifiable.

## Gemini dispatch

To choose the provider and store an API key, or to use a subscription tool such as Codex instead, see [Providers](PROVIDERS.md) and run `storybook provider status PROJECT`.

Google Gemini is the image provider for editions. The only implemented API model is `gemini-nano-banana-2.1`, chosen for cost: it has the lowest standard per-image price at both 1K and 2K. Nano Banana 2 Lite matches it at 1K but has no 2K output, and Nano Banana Pro costs several times more. Using one model for every slot also keeps the style consistent. The edition's `generation` object supplies this `model`, the allowed `slots` and a lifetime `max_submissions` ceiling. Set it at import, or later with a revision operation such as `{"op": "generation", "model": "gemini-nano-banana-2.1", "slots": ["p18/illustration", "p20/colouring"], "max_submissions": 8}`. Slots are story pages and the front cover (`cover/illustration`); the private back cover is refused. The ceiling counts every submission in the edition's Gemini journal, so it must exceed the number already made. `storybook edition gemini PROJECT PAGE/illustration --dry-run` lists the ordered inputs, roles, output dimensions and budget. Use `gemini-probe` to check local environment or Keychain credential presence. An authenticated request is a separate step. Use `GEMINI_API_KEY` or the macOS login Keychain service `Storybook Toolkit Gemini API` (override the name with `STORYBOOK_KEYCHAIN_SERVICE`), account `storybook`; see [providers](PROVIDERS.md). Store the key privately.

The paid call requires current director approval. Results are recorded under `generation-runs/edition-gemini/`. Check a captured attempt's actual art, then record `gemini-quality PROJECT ATTEMPT pass|localized|unusable --reviewer NAME --seconds SECONDS --evidence OBSERVATIONS`. Use `assign` with `attempt` to promote a current passing capture and record its edition visual review. A localized defect permits one edit with `--parent ATTEMPT --edit 'targeted change'`. Stop and record the owner's decision after provider or quality failures. Use `gemini-resume` with owner and reconciliation evidence for a paused journal only after the condition has been resolved. Ambiguous submissions require billing/provider reconciliation before further dispatch. The adapter has one provider and performs no automatic retry. Rerunning an identical packet after a failed attempt makes no call until the owner releases it: `gemini-resume PROJECT --owner NAME --evidence TEXT --resubmit ATTEMPT` works whether or not the journal is paused, and each release allows one resend.

Wire format: Google accepts only `image/jpeg` output, so the adapter requests JPEG and converts the decoded pixels to PNG for intake; the attempt's `provider_output` records the JPEG digest. PNG inputs travel as JPEG quality 92 (`wire_encoding` in the packet) to stay under the 20 MB inline limit; the journal still hashes the stored PNG. If a response breaks mid-stream, the adapter reads the interaction id from the partial body and fetches the stored interaction by id, which makes no new generation; otherwise the attempt stays ambiguous with that id recorded.

Current reference and price basis as checked 22 November 2026. A maximum of 14 inputs, with up to four character and ten object references, includes the edit parent in the total. Standard image output for the selected model is approximately $0.0336 at 1K and $0.0504 at 2K; the adapter requests 2K for illustrations and 1K for colouring and profiles. Inputs and thinking tokens are separate, so attach only the references a slot needs. Google's Batch API costs about half but returns results asynchronously and is not implemented. Retries cost far more than resolution, so the frozen checks and one-edit limit are the main cost controls. The private back-cover image is excluded from requests. [Google image generation](https://ai.google.dev/gemini-api/docs/image-generation) · [Google pricing](https://ai.google.dev/gemini-api/docs/pricing).

Use a `layout` revision operation with `keep_french_punctuation: true` to
keep French punctuation and guillemets with the adjoining words. Imported proofs
retain their original wrapping until that option is selected.

Use `storybook edition gemini-report PROJECT` to inspect submissions,
first-submission and first-delivered-image passes, timed reviews, and pause
status. Use provider usage and billing to reconcile actual monetary cost.

## Run a small, reviewed image round

For an explicitly authorized tool that an agent operates outside the CLI,
freeze a small round with `edition art-round PROJECT RUN ROUND.json`. The
round defines `provider`, `objective`, `slots` and a submission `limit`.
Use `edition art-start PROJECT RUN PAGE/KIND SHOT.json` immediately before a
call. The shot records the exact `prompt`, ordered local `inputs` with
`file`, `sha256` and `role`, and a `checks` map with specific visible
criteria. Include the edited parent as the first attachment when applicable.

Use `art-capture PROJECT RUN ATTEMPT --file OUTPUT.png` for the returned file.
Then give `art-review PROJECT RUN ATTEMPT OBSERVATIONS.json` the reviewer
name and `criteria` with one `decision` and observed `evidence` per frozen
check. Close with `art-close PROJECT RUN --lessons TEXT` before planning the
next round. For passing attempts, an edition `assign` operation can use the
`round` and `attempt` fields together. Check the artwork again in context
and record its edition visual approval.

### Preserve recurring visual checks

Put required visible expectations in the slot brief under
`visual_checks`, keyed by stable criterion IDs. A round shot can add checks
without replacing existing ones. Use `art-start --dry-run` to inspect the
merged rubric, provider input order, local comparison art and print slot
before reserving an attempt. The dry run uses no submission.

Reviewers can log `uncertain` when pixels do not establish a feature. A
`repair` with `region`, `instruction` and the exact blocking `criteria`
records several observations that one local edit can address. For a targeted
shot, use `edit_parent` with its previous `round` and `attempt`. The parent
must be first in `inputs`. Its complete rubric survives the edit, including
checks that already passed. An unsuccessful targeted edit requires new
staging before trying a fresh composition.

Use `edition art-status PROJECT RUN` to recover after an interruption. It
shows the frozen and current revisions, remaining reservations, candidate
digests, comparison references, review observations and the next action for
each attempt. Add `--attempt ID` to retrieve one record. Resolve a pending
transfer or review before scheduling another image. This command is read-only.

Rebuild a prior proof without changing the active edition with
`storybook edition build PROJECT NEW_OUTPUT --revision REVISION`. Add
`--reading-only` when you need only the reading PDF. The proof report in
each output directory records the revision used for that build.

## Plan v2 consistency tools

These guarantees run locally and make no provider call.

- **Policy switches.** The `generation` revision operation accepts `max_inputs` (input budget per call; 5 recommended), `strict_references` (refuse a dispatch whose reference is a scene shared by three or more subjects), `drift_max` (largest share of pixels an edit may change outside its target, e.g. `0.01`), `checks` (`text`, `colouring`: add these findings to `edition check` and the release gate) and `max_failures_per_slot` (pause only when one slot keeps failing, instead of on every unusable image).
- **Checks from the text.** `storybook edition textspec PROJECT [--page ID]` lists checks for characters and elements declared in the edition's `textspec.json`. A brief satisfies a requirement with a `visual_checks` entry of the same ID or waives it in `text_exemptions` with a reason. See [project vocabulary](#project-vocabulary-and-relationships).
- **Cast sheets.** `storybook edition cast-sheet PROJECT OUT.png --root KEY=HEIGHT ...` places clean single-subject references left to right on white. Attach it to a brief as `layout_reference` (`file`, `role`); it tells the model exactly who is on the page, in order and at relative scale.
- **Reference sheets.** A `missing_root` revision operation defines a `KEY/profile` call with `sources` (crops), `prompt`, `aspect_ratio` and `image_size`: for example four characters isolated on white in one 2K call, or five colouring outlines in a grid. `storybook edition split-sheet PROJECT ATTEMPT OUTDIR --rows p01,p02,p03 --rows p04,p05` cuts a passed outline sheet into one page image per subject and reports each page's colouring metrics.
- **Drift gate.** An edit (`--parent ATTEMPT` or `--parent assigned`) sends only the image being edited and must declare its target with `--region x0,y0,x1,y1` (fractions, repeatable). When the policy sets `drift_max`, `gemini-quality ... pass` measures the parent against the result and refuses the pass if more than `drift_max` of the pixels outside the targets changed, or if any small cell outside them changed a lot (a hotspot around a small element). `storybook edition ab PROJECT BEFORE AFTER --region ...` runs the same measurement on any two files.
- **Colouring checks.** Flat grey or shaded areas (more than 2% of the page) and stroke widths outside 4-8 px at 1000 px wide are reported for colouring slots.
- **Recovery without the owner.** If a response breaks and the journal pauses with an interaction id, `storybook edition gemini-readback PROJECT` reads the stored result back by id (no new generation), and `gemini-resume PROJECT --agent --owner NAME --evidence TEXT` records it as an agent recovery under the owner's standing authorization.
- **Following the book.** `storybook edition next PROJECT` prints the single next action (review a capture, edit, assign, generate, book sweep). `storybook edition sheets PROJECT OUT.jpg [--kind colouring]` makes a contact sheet of every page. `storybook edition scorecard PROJECT [--issues LEDGER.json]` reports calls, passes, edits, drift rejects, estimated cost per assigned slot, model versions, owner resumptions and agent recoveries.

## Project vocabulary and relationships

Put `textspec.json` beside `edition.json` to specify what the text checks should
recognize. Vocabulary comes from this file. Counts use French numbers and
determiners.

```json
{
  "words": {"salle": ["room", ["room"]], "rideaux": ["curtain", ["curtain-a", "curtain-b"]]},
  "plural_forms": ["rideaux"],
  "named": [["camille", "character-a"]],
  "contacts": [["touch(e|ent) le mur", "the character touches the wall"]],
  "occupied_zones": {"room": "interior"}
}
```

- Each word maps to a check group and corresponding catalog IDs. Add the forms
  that occur in the edition. Declare irregular plurals in `plural_forms`.
- `named` and `contacts` use regular expressions on lowercase, accent-folded text.
  Names produce `text-named-ID` checks. Contacts produce `text-contact-N` checks
  in declaration order.
- `occupied_zones` maps an element ID to a zone in `world.initial_occupancy`.
  A check is generated when text mentions that element or the brief references it.
- For an older edition, bring its vocabulary, contacts and occupied zones into
  `textspec.json`, then compare `edition textspec` with its saved visual checks.

## Set plans and rendered layouts

Keep one set plan per setting, for example `book-edition/set-plans/setting.json`.
Coordinates are in metres with x east, z north and y up.

- `objects`: a map from story element IDs to geometry. Use `ground` with x and z
  ranges, `box` with x, z, width, depth and height, `sphere` with x, y, z and radius,
  or `polygon` with three or more `[x, y, z]` vertices. A `group` combines solid
  shapes in a `parts` list. Older plans with specialized shape names can model
  the same elements using groups.
- Give each element a `label`, `facts` and, if useful, a `count` expectation.
  Use `fixture: true` for order and placement checks. Set `describe: false`
  to keep an element out of the left-to-right sentence and use `visible_note`
  for an extra statement when it is visible.
- `actors`: one coloured block per character or moving element. Set `width`,
  `height`, `colour`, `label` and `colour_name`.
- `shots`: one entry per page, with a `camera` and positions for
  the characters. The camera accepts `pos` ([x, y, z]), `yaw` (degrees,
  with 0 looking north), `fov` and `pitch`. A character position is
  `[x, z]` or `[x, z, y]`.

```sh
P=projects/my-story
storybook edition set-layout "$P/book-edition" set-plans/setting.json page-id \
  "$P/book-edition/artwork-preparation/layout-page-id"
```

The command renders `layout.png` locally (no provider call). With `--top` images it also writes `sheet.png`, which has those images in a top band and the layout below. `derived.json` holds what is visible where, a layout sentence and yes/no checks. Stage the sheet as the brief's `layout_reference` with the derived `role`, append the sentence to the description, and merge the checks into `visual_checks`.

To measure consistency, ask a reviewer who did not make the images to answer the derived checks for each image, labelled at random. Then run `storybook edition set-score PROJECT answers.json --key key.json` for the agreement rate per image and per arm.
