# Experimental world timeline

`storybook check-world PROJECT` validates an optional `world.json` against the project's character catalog and the ordered page IDs in `scenes.json`. It reports each declared occupancy snapshot. This is an early redesign component: it does not yet change staging prompts, check images, or gate releases. The series manifest preferences are guidance; format-3 production uses the project catalogs and scene contracts, so copy applicable preferences into those explicitly until automatic propagation is implemented.

Declare `format_version: 1`, a `zones` object of ID to description, and a `connections` array of two-zone arrays. `initial_occupancy` maps known character-catalog IDs to zones. The ordered `scenes` array must match every scene page ID exactly. Each scene may include an `events` list, where each event gives `character`, `from`, `to` and `reason`; transitions follow a declared connection and originate at the character's actual location. Each scene lists `visible_zones` and a `visibility` entry for every character in those zones. Each entry must say `visible` or `occluded` and provide evidence for that declaration. Characters outside those zones remain in their prior locations.

This is a declaration check, not a vision system: an apparently valid timeline does not establish whether a generated picture contains the right animal or barn. Review the actual images and their catalog references independently.

Versioned editions embed the timeline directly. Their scene handoff includes
before/after occupancy, movements, visibility and optional object custody. See
[Transcript-to-book editions](EDITIONS.md) for transfers and assertions. Existing
legacy `check-world` continues to work with `world.json`.
