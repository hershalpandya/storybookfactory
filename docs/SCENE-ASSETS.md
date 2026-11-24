# Catalogs, set design and visual review

Keep the story directory, source material, art and reviewer notes private. Start from the approved adaptation and the linked English source. Map each beat to a page, including narrator corrections and open questions. A new series starts with empty project-local catalogs. Pick your own cast, locations, machinery and objects. Import earlier entries only when they fit the new story.

## Character and prop catalogs

Run `storybook init-catalogs PROJECT` once. Fill `character-catalog.json` with one stable ID per visible individual, including extras. For example, give Pip, Nell, Sheep 1, Sheep 2, Mr Horse and Mrs Horse separate entries even if the text calls them a flock or a pair. Record the same ID every time an individual returns. Describe silhouette, markings, accessories, scale and species anatomy. The established `species` and `legs` fields remain available for leg-only character checks. When a design needs other counts, use the counted parts described below.

Fill `prop-catalog.json` with the same structure. Catalog locations, scenery and objects that need continuity, such as the farm, barn, fence, mountain backdrop, well, rope, pulley, bucket and trough. Give the barn's fixed construction its own facts. Track the doors' position and the interior arrangement as state facts. If the barn has permanent double doors and a bed of straw, record both in the catalog so subsequent pages inherit them.

Both files have `format_version: 1` and an `entries` object. A minimal illustrative character entry follows.

```json
{
  "format_version": 1,
  "entries": {
    "pip": {
      "name": "Pip",
      "species": "sheep",
      "legs": 4,
      "description": "An adult ewe with a pale face, pink inner ears and a striped scarf at her neck.",
      "facts": {"scarf-position": "neck", "colour-scarf": "blue striped"},
      "state_fields": ["fleece"],
      "states": {
        "summer-shorn": {
          "description": "A smooth, close-shorn coat in warm summer weather.",
          "facts": {"fleece": "smooth shorn"},
          "profiles": {"front": "Full-body front view.", "left-profile": "Full-body left side view."}
        },
        "summer-unshorn": {
          "description": "Full curly fleece in warm summer weather.",
          "facts": {"fleece": "full curly"},
          "profiles": {"front": "Full-body front view.", "left-profile": "Full-body left side view."}
        }
      }
    }
  }
}
```

Prop entries use the same description, facts and states. A prop can also specify counted parts. Use lowercase ASCII letters, digits, hyphens or underscores for IDs, state keys, fact keys and views. Names should be unique within each catalog. Use short canonical values for facts, such as `"door-design": "crossed double doors"`, `"door-position": "open"` and `"floor": "straw bedding"`. Plan every story condition before creating art. In format 3, `facts` are permanent across states. List every condition-dependent key in `state_fields`. Each state's `facts` may only use those keys, and the key sets must stay separate. Include at least two different views per state. For a well, useful views could show the bucket attachment and free end of the rope from opposite sides.

### Count parts for any design

For a character with more than leg counts, use `form` and `parts` in place of `species` and `legs`. For example, a bee can declare `"form": "honey bee"` and `"parts": {"legs": 6, "wings": 4, "antennae": 2}`. A robot can declare `"form": "tracked robot"` and `"parts": {"treads": 2, "grippers": 2, "lenses": 1}`. For a prop such as a hatch, add only the `parts` mapping, such as `{"hinge-pins": 2, "latches": 1}`. Use a nonempty mapping of lowercase part IDs to nonnegative whole numbers. Include each part you want checked. Counts describe the entity's construction across its catalog states. A part can have a visible count of zero when cropping, occlusion or the view hides it.

For each entry, state and view, run the corresponding profile brief after writing the prose. Give it to an authorized image model or artist to produce a distinct PNG of that subject. Inspect the views together for identity, construction, anatomy, scale and correct state before registering each one.

```sh
storybook profile-brief PROJECT characters pip summer-shorn left-profile
storybook register-reference PROJECT characters pip summer-shorn left-profile pip-left.png \
  --reviewer 'Reviewer name' --evidence 'The scarf stays at the neck and all four limbs align in a standing pose.'
storybook check-catalogs PROJECT
```

Approved PNGs are stored by content hash in `root-assets/png/`. Records under `root-assets/characters/` and `root-assets/props/` bind each PNG to the catalog definition, reviewer and evidence. Changing a definition requires reviewing affected profiles again. Re-register a still-valid PNG with fresh evidence when it qualifies.

For a new story, initialize new catalogs, check the story's cast, construction and conditions against the previous book, then copy qualifying entries one at a time.

```sh
storybook import-catalog-entry NEW_PROJECT PREVIOUS_PROJECT characters pip
storybook import-catalog-entry NEW_PROJECT PREVIOUS_PROJECT props barn
```

Imports carry the entry and its verified references. Add or revise states in the new story and create the missing views. Use the series' earlier descriptions and approved art as evidence for identity and settings. Mixed scenes from an old story may contain different season, fleece, barn layouts or accessories. Curate dedicated root profiles for the conditions in the new story.

## Stage and review each page

Write `PROJECT/beats.json` with the adaptation hash and an ordered `beats` object. For every beat, record its zero-based adapted `passage`, the reviewed `source_passages` indexes, a concise `description`, and an observable image `check`. Record narrator corrections in the optional `correction` field and list any entities that must appear in the optional `subjects` array. Give every declared beat exactly one page assignment in ledger order. Cover every reviewed source link for each adapted passage.

```json
{
  "adaptation_sha256": "REPLACE_WITH_ADAPTED_STORY_SHA256",
  "beats": {
    "barn-exit": {
      "passage": 0,
      "source_passages": [0],
      "description": "After shearing, Pip steps into the yard.",
      "check": "Her front hoof and face point out toward the yard."
    }
  }
}
```

Write `PROJECT/scenes.json` with the same adaptation hash. This single-page example assumes the corresponding barn catalog and registered profiles.

```json
{
  "format_version": 3,
  "adaptation_sha256": "REPLACE_WITH_ADAPTED_STORY_SHA256",
  "pages": [
    {
      "id": "page-1",
      "passages": [0],
      "beats": ["barn-exit"],
      "scene": "Pip steps out through the open barn doors.",
      "colouring": "A simple outline of Pip taking a step, with a raised hoof.",
      "set": {
        "location": "Summer barnyard",
        "layout": "The barn fills the rear left. Straw lies behind the threshold. The yard is clear in front.",
        "lighting": "Warm afternoon light from camera right.",
        "camera": "Eye level in the yard, with a clear path across the foreground."
      },
      "characters": {
        "pip": {
          "state": "summer-shorn",
          "view": "left-profile",
          "position": "Just outside the threshold, facing the open yard",
          "action": "Steps toward the yard with one forehoof raised",
          "visible_legs": 3,
          "occlusion": "The far hind leg overlaps the near hind leg."
        }
      },
      "props": {
        "barn": {
          "state": "open-straw",
          "view": "front",
          "position": "Behind Pip, upstage left",
          "use": "Frames the exit between the crossed double doors."
        }
      },
      "colouring_subjects": ["pip"],
      "colouring_placements": {
        "pip": {
          "view": "left-profile", "position": "Centered in the frame",
          "action": "Steps forward with one forehoof raised", "visible_legs": 4
        }
      },
      "checks": {"step-direction": "Pip's head and raised hoof point into the yard."}
    }
  ]
}
```

Assign each adaptation passage exactly once, using zero-based indexes in order. Stage one visible beat per image. Give every entity its view, relative position and action or set role. On the page where an entity first appears in a different state, include `state_change` explaining the story event, even if the previous appearance was several pages ago. A placement can include a `hidden_facts` object mapping inherited fact keys to explicit occlusion or framing reasons. The director checks those reasons. Put pure colour facts under keys prefixed `colour-` or `color-` so the line-art checklist can omit them.

For every placement of a counted entity, supply `visible_parts` with one count per catalog part. When fewer than the catalog total are visible, give the reason under `occluded_parts` for that part. A side-view bee might have this placement.

```json
{
  "state": "flying",
  "view": "side",
  "position": "Hovering just left of the greenhouse hatch",
  "action": "Waits for the hatch to open.",
  "visible_parts": {"legs": 6, "wings": 2, "antennae": 2},
  "occluded_parts": {"wings": "The near wings overlap the far pair."}
}
```

In format 3, add `colouring_placements` to every story page. Supply one complete placement per ID in `colouring_subjects`, including the colouring view, position, action or use, and applicable part or leg counts. The colouring placement inherits the illustration's catalog state. The tool uses the reference for the colouring view. Older format-2 scenes may omit the object and reuse illustration placements.

The optional `covers` object accepts `front` and/or `back`, each with the page's `id`, `scene`, `set`, `characters`, `props` and `checks` fields. The cover has its own state and one illustration. It can depict a later story moment without advancing the interior-page timeline. Omit `passages`, `colouring`, `colouring_subjects` and `colouring_placements` for covers.

For a mechanism, declare anchor labels in the relevant catalog entries, such as `"anchors": {"bucket-ring": "Ring on the bucket", "pulley": "Wheel above the well", "free-end": "Free end on the ground"}`. Add a scene-level `mechanisms` object keyed by mechanism ID. Each value has a `description` and an ordered, continuous `path` of staged `entity.anchor` keys, for example `["well.bucket-ring", "well.pulley", "well.free-end"]`. The visual reviewer reports the path actually visible, with evidence. An unobservable segment should fail or remain uncertain.

Run `storybook layout-preflight PROJECT METADATA` with the intended print font. The command checks text fit and writes `layout.json` with the actual print slots. It needs the plan and approved text, and can run before illustration generation. Then run `storybook set-preflight PROJECT PAGE`. Have a set director, such as a separate review pass by an agent or a named human, inspect the contract, root PNGs, source beat and adjacent sets. Look for missing cast or scenery, contradictory conditions, implausible anatomy or blocking, and changes in features such as the barn door construction, straw placement and the well rope's route. Revise the staging if a check fails or remains uncertain. Record a reviewer, the reported hash and evidence under each requested check key.

```json
{
  "contract_sha256": "FROM_SET_PREFLIGHT",
  "reviewer": "Named set director",
  "checks": {
    "story_beat_and_complete_roster": {"result": "pass", "evidence": "Pip is the only visible actor in the exit beat."},
    "set_layout_and_adjacent_page_continuity": {"result": "pass", "evidence": "Both crossed door panels and the straw interior carry through."},
    "state_transitions_and_reference_match": {"result": "pass", "evidence": "The left profile is the approved shorn Pip."},
    "camera_blocking_and_anatomy": {"result": "pass", "evidence": "The side view supports one far hind leg hidden by the near leg."},
    "colouring_scope": {"result": "pass", "evidence": "The single stepping sheep reads as a small outline."}
  }
}
```

```sh
storybook review-set PROJECT PAGE set-review.json
storybook scene-handoff PROJECT --page PAGE --kind illustration > illustration-packet.json
storybook scene-handoff PROJECT --page PAGE --kind colouring > colouring-packet.json
```

Use the generated prompt as written, with the numbered PNGs in packet order. Paths are relative to the story directory. Each numbered PNG can supply the selected view for several subjects. Shared PNGs appear once in the attachment list, and the prompt names every role. The remaining approved views are available in preflight and for visual judging. The toolkit gates its handoff on the current set review. Save the returned PNG locally before any further calls. For a repair, use the current candidate as the edit target and include the applicable approved profiles; verify the entire result after the edit.

## Inspect, score and register the result

```sh
storybook image-checklist PROJECT PAGE illustration candidate.png
storybook review-image PROJECT PAGE illustration candidate.png visual-review.json
storybook register-asset PROJECT PAGE illustration candidate.png
storybook check-assets PROJECT
```

Run the same sequence for the colouring PNG. The image checklist supplies hashes, fact keys, reference paths and qualitative checks. Its `comparison_images` field lists the most recent registered artwork showing each returning subject, including nonadjacent scenes. Review those exact files. Finish the illustration first so its art is available when reviewing the matching colouring PNG. Have a visual reviewer inspect the pixels at usable size, count the required parts for each subject, identify its view and record the facts that are actually visible. For counted designs, report `visible_parts` for every listed key, or `null` for an uncertain count. For a leg-only character, use `visible_legs`. Verify how parts attach and align in the planned view and pose. Compare stable features to the approved catalog and neighbouring art. Supply observed values using the catalog's vocabulary for exact matching. Mark ambiguous values `null` or use `uncertain` for qualitative checks. An unmatched, repeated or extra subject goes in `extras`.

The review JSON contains `contract_sha256`, `image_sha256`, `kind`, `reviewer`, `extras` (an array), `checks` (every key requested by the checklist) and `subjects`. For example, `subjects` could contain the following record for Pip.

```json
{
  "pip": {
    "view": "left-profile",
    "visible_legs": 3,
    "facts": {"scarf-position": "neck", "colour-scarf": "blue striped", "fleece": "smooth shorn"},
    "evidence": "Three separate hooves are visible, the far rear limb is overlapped, and the scarf sits under the jaw."
  }
}
```

In format 3 also include a `continuity` object keyed by every page in `comparison_images`. For each provide its `sha256`, `result`, and `evidence`. Use an empty object when the checklist has no comparison images. When the checklist lists mechanisms, use its unordered anchor vocabulary to identify the parts. Add a `mechanisms` object keyed by mechanism ID, with the observed `path` and `evidence` on each. An incomplete path fails. Replacing a registered comparison image requires a new review of the dependent assets. New scene PNGs need a captured attempt. Use `review-image --import-existing` for archived artwork that qualifies for the current contract.

Each check contains a `result` of `pass`, `fail` or `uncertain`, and nonempty `evidence`. The scorer compares the observed roster, profile, count and visible facts to the contract and requires every qualitative check to pass. It verifies PNG structure and hashes independently of those observations. The reviewer supplies the interpretation of the pixels. Keep the benchmark evaluator independent of the generation pass and record what the evaluator actually saw.

Failed and passing review records remain under `visual-reviews/`; scored PNGs are retained under `candidates/`. A rejected, missing or stale review blocks registration and production rendering. To replace an existing slot after a new review, use `register-asset ... --replace`. `check-assets` verifies bytes and reports missing slots. Changes to the page, relevant catalogs, root images or adjacent set context require rerunning affected reviews. Keep the full story directory to resume. Use a single writer when directly editing JSON.

## Capture and benchmark a generator

Freeze a case list before calling the image model. For a small pilot, choose a cover, two views of a recurring set, a crowd and a mechanism. Use a separate frozen run for root profiles so you can measure their preparation cost. A scene case uses `page` and `kind`. A root case looks like `{"kind": "profile", "catalog": "characters", "id": "pip", "state": "summer-shorn", "view": "left-profile"}`. The top-level JSON has a `label` and a `cases` array. Record the provider and model in a separate settings JSON, along with seed or other parameters when available. Set `max_image_inputs` when the provider has a known attachment limit. For the built-in image generator used in an early pilot, this was five. The edit target uses one slot.

```sh
storybook benchmark-start PROJECT pilot cases.json
storybook attempt-start PROJECT pilot page-1 illustration settings.json
storybook attempt-finish PROJECT pilot ATTEMPT_ID --file provider-output.png
storybook image-checklist PROJECT page-1 illustration CAPTURED_PATH
storybook review-image PROJECT page-1 illustration CAPTURED_PATH review.json --review-seconds 42
storybook benchmark-report PROJECT pilot --min-first-pass 0.8
```

The start command prints the frozen prompt and ordered references. Use its `provider_payload.prompt` and ordered `provider_payload.input_images` as the exact submission. If the payload exceeds `max_image_inputs`, the command reports the count before opening an attempt. Call the provider only after an attempt opens. Pass returned bytes through `--file` or `--stdin`. For a transfer failure use `--error '...'`. If the response was saved and the command stopped during screening, use `--resume` for the same ID. The journal preserves even rejected input before review. It screens for undecodable, blank or undersized PNGs and for duplicate decoded pixels, including images from earlier runs. For page art it requires at least 120 effective DPI at the planned print fit and at least 128 pixels in both dimensions. Root profiles require at least 256 pixels on the shorter side.

To edit an attempt, open a new attempt with `--parent ATTEMPT_ID --edit-prompt EDIT_FILE`. The journal records the original PNG hash and the exact edit instruction separately from the base prompt. The emitted provider payload puts the parent at image 1, adjusts the supporting reference numbers, and includes the exact edit instruction. If staging or the root library changes, freeze a new run for the revised cases.

For root profiles use the slot `characters/pip/summer-shorn/left-profile profile` in place of `page-1 illustration`. After capture, approve the PNG with `register-reference` or reject it with `profile-reject PROJECT RUN ATTEMPT_ID --evidence '...'`. Supply `--review-seconds` to record actual review work when measured. The report includes attempt counts, first-pass and eventual acceptance, failure reasons, elapsed capture time, and the total across timed reviews. Unattempted cases stay in the denominator. Local records track reported provider calls. An actual provider integration is external.

For historical calibration, keep a private set of labeled PNGs with known errors such as extra limbs, a patch of unintended wool, or an interrupted rope. Give those pixels and the checklist to the reviewer separately from generation. Use dry contract scoring to check whether their observations reject the known defects, then keep any live comparison in its own journal. Offline fixtures exercise the gates with authored observations.

## Older projects

Format-1 and format-2 projects can still use their existing workflows. New projects require format 3. To migrate, keep a private backup of the old plan, registry and artwork. Add the beat ledger, independent colouring placements, fixed facts and declared state fields. Catalog edits invalidate affected root-profile approval records. Re-register qualifying reference PNGs with current evidence. Set the project minimum `scene_format_version` and the scene plan `format_version` to 3, run layout preflight and redo set and image reviews. Existing candidates can use `--import-existing`; such reviews do not qualify as new generation attempts. The former `benchmark-images` report remains available for legacy manifests.

Format-1 scene plans name entities from a series manifest, which the toolkit does not ship: put it in the project as `series-manifest.json` or point `STORYBOOK_SERIES_MANIFEST` at it. The manifest lists `entities` (with `reference_ids`) and `references` (with `path` and `use`). Reference PNGs resolve against `STORYBOOK_REFERENCE_DIR` (an absolute directory) or the manifest's `local_reference_root.relative_to_manifest`. Keep the manifest and its PNGs in the private project.

Before treating a book as final, have a human approve the page sequence, source and language fidelity, art and continuity, layout and physical print and sewn proof.
