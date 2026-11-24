"""Built-in language module descriptions; no automatic pronunciation engine."""

MODULES = {
    "fr-CE1": {
        "name": "French CE1", "status": "supported with human review",
        "annotation_kinds": ["silent", "liaison"],
        "reading_level": "CE1: short, clear sentences and age-appropriate vocabulary; review meaning and natural French.",
        "adaptation": "Preserve story events, voice, names and unresolved source uncertainties; review grammar and register with a French reader.",
        "typography": "Marelle 2 is the v10 reference; shape accented text and verify font coverage and legibility.",
        "annotations": "Optional story-specific silent-letter spans and liaison links, reviewed in context; no automatic rules or certification.",
        "guidance": "Keep complete spelling. Grey silent letters in the chosen ordinary reading; keep sounded consonants dark and connect a pronounced liaison to the following word with an arc. Sound groups remain dark. Do not impose optional liaisons. Pronunciation varies; review every occurrence, including context-dependent words and silent e. Cover and back use uniform colour. Check a print proof.",
    },
    "test-xx": {
        "name": "Non-French test fixture", "status": "test fixture only; not linguistic support",
        "annotation_kinds": [],
        "reading_level": "Synthetic fixture; no reading-level guidance is implemented.",
        "adaptation": "Synthetic fixture only; a real language module and review are required.",
        "typography": "No font or shaping requirements have been established.",
        "annotations": "No pronunciation system is implemented.", "guidance": "Do not use this fixture for a real book.",
    },
}


def get_module(identifier):
    if not isinstance(identifier, str):
        raise ValueError("Language module ID must be a string")
    try:
        return MODULES[identifier]
    except KeyError as exc:
        raise ValueError(f"Unknown language module {identifier!r}; support is not implemented") from exc
