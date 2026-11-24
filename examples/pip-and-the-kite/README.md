# Example: Pip et le cerf-volant

A two-page story that goes from a transcript to a reading-preview PDF in under a minute, with no image provider and no API key. Use it to see the whole pipeline before you work on your own story.

| File | What it is | Who writes it in a real book |
|---|---|---|
| `transcript.txt` | The story as told, in English, including an aside to leave out | You (a recording transcribed to text) |
| `reviewed-story.json` | The story-only English passages, each citing its transcript line | Your agent drafts it; a person checks it against the transcript |
| `french.json` | The French CE1 adaptation, one passage per source passage, linked to the reviewed story's hash | Your agent drafts it; a French reader checks it |
| `edition-index.json` | Events, pages (text and picture briefs), covers and the Gemini budget | Your agent drafts it from the story |
| `meadow.json` | Shared setting geometry and both page cameras | Your agent stages and checks the camera views |
| `metadata.json` | Title, author, date and back-cover title | You |

The two review files say "Example reviewer". In your own book, put the name of the person who actually checked the text. The toolkit records that as an assertion, so never claim a review that did not happen.

## Run it

From the repository root, after `uv sync --locked`. The output goes under `projects/`, which Git ignores:

```sh
E=examples/pip-and-the-kite
P=projects/pip-workspace-example
uv run --locked storybook init "$P" --workspace
cp "$E/transcript.txt" "$E/reviewed-story.json" "$E/french.json" "$E/edition-index.json" "$E/metadata.json" "$P/inputs/"
uv run --locked storybook register "$P/source-review" "$P/inputs/transcript.txt"
uv run --locked storybook review "$P/source-review" "$P/inputs/reviewed-story.json"
uv run --locked storybook approve-adaptation "$P/source-review" "$P/inputs/french.json"
uv run --locked storybook init-catalogs "$P/source-review"
uv run --locked storybook edition import "$P/book-edition" "$P/source-review" "$P/inputs/edition-index.json" "$P/inputs/metadata.json"
uv run --locked storybook edition check "$P/book-edition"
uv run --locked storybook edition build "$P/book-edition" --mode reading
```

Open `reading.pdf` in the dated `output` path printed by the last command
under `projects/pip-workspace-example/outputs/previews/`. The folder also
contains `reviewed-text.json` and `proof-report.json`. The workspace's
`README.md` explains where the source, edition and output files live. Give
`P` a new path to repeat the example from the start.

The PDF shows the cover, two story pages and the back cover, with shaped French
text and placeholder artwork. `edition check` lists the six open art slots.

## Preview the recurring setting

With the same `P` and `E` from the commands above, render both cameras and
stage the resulting attachments and checks. These commands run offline.

```sh
D="$P/book-edition"
mkdir -p "$D/set-plans"
cp "$E/meadow.json" "$D/set-plans/meadow.json"
uv run --locked storybook edition set-layout "$D" set-plans/meadow.json p01 "$D/artwork-preparation/layout-p01" --stage
uv run --locked storybook edition set-layout "$D" set-plans/meadow.json p02 "$D/artwork-preparation/layout-p02" --stage
uv run --locked storybook edition gemini "$D" p02/illustration --dry-run
```

Compare the two `layout.png` files and look for the staged layout in
`ordered_inputs` in the dry-run output. Inspect the landmark order and actor
positions in each camera view before reviewing the scene for dispatch.

## Next steps toward a finished book

1. **Choose an image provider:** `uv run --locked storybook provider status projects/pip-workspace-example/book-edition` explains the options (a Gemini API key, or a subscription tool such as Codex). See `docs/PROVIDERS.md`.
2. **Make the art:**
   - Generate a cast sheet and a set picture, then one illustration per page, with checks derived from the French text (`storybook edition textspec`).
   - Make batched colouring outlines.

   `docs/EDITIONS.md` has every command. The `storybook-image` skill runs this loop for your agent.
3. **Review and build:** record a visual review for every picture and the text-layout review, then build the reading and print PDFs and check a printed proof.
