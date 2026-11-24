# Project format and transcript preparation

Projects contain private source material. Keep project directories out of Git and share them only with permission. Version 1 uses UTF-8 JSON and UTF-8 English transcript files; the toolkit does not transcribe or verify audio. Save supplied wording faithfully, including foreign phrases. File comparison detects byte equality and line differences, not narrative meaning; wording that matches across transcripts can still be wrong.

## Workflow

1. `storybook init my-project` creates an empty project. Resume by using the same directory in subsequent commands.
2. `storybook register my-project transcript.txt` copies each supplied English transcript into the project and records its SHA-256, original basename and assigned ID. Register multiple inputs separately, even duplicates. Do not edit registered copies; changed or missing copies cause comparison and review to fail.
3. `storybook compare my-project` reports exact byte duplicates and displays pairwise line diffs. Differences include formatting and may miss semantic ambiguity. Inspect the originals and ask the narrator or another knowledgeable person about uncertain words. Do not invent missing wording or claim that transcript evidence confirms audio.
4. With an agent or manually, reconcile the inputs into a separate JSON draft following the example below. Preserve the narrator's voice, story events and foreign phrases as supplied; remove unrelated conversation, asides and interruptions. Link every passage to the source IDs and specific locations (for example, line ranges or quoted anchors). Describe disputes, alternatives and unresolved wording in `uncertainty`, including source locations for each alternative. An empty uncertainty string means none was identified, not that the passage is proven correct. Keep uncertainty visible and obtain human decisions where possible; retain unresolved points rather than guessing. The tool does not perform this interpretation.
5. A human reads the sources and draft, checks omissions, voice, phrases, citations and unresolved disputes, then supplies their name and explicitly sets `human_reviewed` to `true`. Run `storybook review my-project draft.json`. This validates structure and registered IDs and saves `reviewed-story.json`; it cannot verify the reviewer's identity, the accuracy of citations, or the quality of review. Human review is required before treating it as a story source, and unresolved uncertainty still needs attention.

```json
{
  "format_version": 1,
  "human_reviewed": true,
  "reviewer": "Example reviewer",
  "passages": [
    {
      "text": "The little fox said bonjour to the moon.",
      "sources": [
        {"transcript_id": "T0001", "location": "line 1"},
        {"transcript_id": "T0002", "location": "line 1"}
      ],
      "uncertainty": "T0001 line 1 says moon; T0002 line 1 says sun. The narrator has not resolved this."
    }
  ]
}
```

New projects store `scene_format_version: 3` in `project.json`. The file also has `format_version: 1`, a `transcripts` array of IDs, relative copy paths, original basenames and SHA-256 hashes, and `reviewed_story`, either null or a file path and SHA-256. `reviewed-story.json` is the separate machine-readable artifact above. Source locations are human-readable and are not automatically verified. Additional JSON fields are retained. The reviewer should use one passage per independently traceable portion; references may identify multiple competing sources.

Registering another input clears the project's reviewed-story pointer because the new evidence needs review. The old artifact remains on disk to prevent accidental data loss: archive or rename it before saving a new reviewed story. To revise a review, likewise archive the existing artifact first and save a newly reviewed draft. A downstream consumer must check the pointer, artifact hash, and transcript hashes and require an appropriate human review; the presence of an old file alone is not approval. Keep drafts and archives private too. This version has no automatic migration or audio integration.
