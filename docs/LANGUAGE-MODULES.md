# Language modules and adapted stories

`storybook languages` lists the built-in modules; `storybook languages fr-CE1` shows the complete guidance. The registry in `storybook_toolkit.languages` maps a stable ID to a name, support status, adaptation and reading-level guidance, typography/shaping requirements, annotation capability and guidance. Add an appropriate module and human linguistic review before claiming another language is supported. `test-xx` is a synthetic non-French fixture, not a language implementation. Unknown IDs fail explicitly. Each module declares its supported annotation kinds; the fixture supports none. Core validation does not infer pronunciation or apply French word lists.

The French CE1 reading aid preserves spelling, greys silent letters in the chosen reading, and draws arcs for selected pronounced liaisons. Do not grey sound groups merely because several letters form one sound; do not impose optional liaisons. Assess every occurrence in its sentence, especially final consonants, silent e and context-dependent words. For example, the final s in “tous” may be pronounced or silent depending on context; a liaison is not the same thing as a normally pronounced final consonant. Regional and reading-style variation matters. These marks are a decoding aid, not IPA or an official universal school standard. Cover and back text are uniformly coloured. Check accent shaping, font coverage and legibility in a physical proof. Marelle 2 is the bundled font for French CE1.

## Agent-assisted workflow

After the English source is human-reviewed, ask an agent to adapt it using the selected module. Preserve events, voice, names and unresolved source uncertainties; review fidelity, natural wording, grammar, reading level and any annotation with a competent human. The agent proposes marks for each occurrence in context; use a human language review to confirm pronunciation. The human explicitly approves the adapted text and reviews every mark before scene planning. Unmarked passages are allowed and do not mean that every possible mark has been checked or that an annotation system has been applied comprehensively. Human approval is recorded, not independently verified or certified.

Create a private JSON draft as follows, substituting the SHA-256 from `project.json`'s current `reviewed_story` and the actual reviewed passages and decisions:

```json
{
  "format_version": 1,
  "language": "fr-CE1",
  "source_sha256": "REPLACE_WITH_REVIEWED_SOURCE_SHA256",
  "human_approved": true,
  "reviewer": "Example reviewer",
  "passages": [{
    "text": "Les amis.",
    "source_passages": [0],
    "annotations": [{"kind": "liaison", "start": 2, "end": 3, "text": "s", "target": 4, "context_reviewed": true, "note": "Pronounced liaison in this phrase."}]
  }]
}
```

Offsets are zero-based Unicode code point indices into the exact passage text; `end` is exclusive. `silent` marks a span; `liaison` marks a sounded span and `target` points to the first letter of the following word after whitespace. `text` must match the span. A nonempty English `note` records the contextual decision. The validator checks the shape and offsets, not pronunciation, completeness, source fidelity, reviewer identity or approval quality. An empty `annotations` array explicitly records no marks. `source_passages` are zero-based indexes into the reviewed English story; resolve its uncertainty during human review and retain unresolved issues visibly in the source and adaptation as appropriate. Additional fields such as review notes or uncertainties are retained.

Run `storybook approve-adaptation PROJECT draft.json`. It checks the current reviewed source and transcript hashes, stores `adapted-story.json` and a hash-bearing `adapted_story` pointer in `project.json`. It refuses to overwrite an existing artifact: archive private old files before revision. Registering new evidence or reviewing a replacement source clears the adaptation pointer, without deleting the old artifact. Before scene planning or other downstream use, run `storybook check-adaptation PROJECT` to check the pointer, adaptation hash, matching source hash, current source pointer, transcript integrity, language module, and recorded human approval; a stale file or draft alone is not approval. Continue with the [scene and asset handoff](SCENE-ASSETS.md).
