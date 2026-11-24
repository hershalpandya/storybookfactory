"""Derive visual checks from project-declared characters and story elements."""

import re
import unicodedata

from .store import ProjectError, load, project_file, require

PROJECT_FILE = "textspec.json"
PLURAL_DETERMINERS = {"des", "les", "leurs", "nos", "mes", "ses", "vos", "tous", "toutes", "aux"}
NUMBERS = {"deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10}


def fold(text):
    """Lower-case, strip accents and normalise apostrophes so lexicon keys match."""
    text = unicodedata.normalize("NFKD", text.replace("’", "'")).encode("ascii", "ignore").decode()
    return text.lower()


def words(text):
    return re.findall(r"[a-z]+", fold(text))


def project_lexicon(root):
    """Load vocabulary and relationships declared in the edition's textspec.json."""
    path = project_file(root, PROJECT_FILE) if root else None
    data = load(path) if path and path.is_file() else {}
    require(isinstance(data, dict), "textspec.json must contain an object")
    try:
        return {
            "words": {fold(word): (group, list(subjects))
                      for word, (group, subjects) in data.get("words", {}).items()},
            "plural_forms": {fold(word) for word in data.get("plural_forms", [])},
            "named": [(re.compile(pattern), subject) for pattern, subject in data.get("named", [])],
            "contacts": [(re.compile(pattern), description) for pattern, description in data.get("contacts", [])],
            "occupied_zones": dict(data.get("occupied_zones", {})),
        }
    except (AttributeError, TypeError, ValueError, re.error) as exc:
        raise ProjectError(f"Invalid textspec.json: {exc}") from exc


def required_checks(text, world=None, references=(), lexicon=None):
    """Required check IDs and expectations from declared vocabulary and visible elements."""
    lexicon = lexicon if lexicon is not None else project_lexicon(None)
    table, plural_forms = lexicon["words"], lexicon["plural_forms"]
    tokens = words(text)
    found = {}
    for index, token in enumerate(tokens):
        if token not in table:
            continue
        group, subjects = table[token]
        before = tokens[max(0, index - 2):index]
        count = next((NUMBERS[w] for w in before if w in NUMBERS), None)
        plural = token in plural_forms or (any(w in PLURAL_DETERMINERS for w in before[-1:])
                                           and token.endswith(("s", "x")))
        minimum = count or (2 if plural else 1)
        entry = found.setdefault(group, {"subjects": subjects, "minimum": 0, "exact": None})
        entry["minimum"] = max(entry["minimum"], minimum)
        if count:
            entry["exact"] = count
    folded = fold(text)
    for pattern, subject in lexicon["named"]:
        if pattern.search(folded):
            found.setdefault(f"named-{subject}", {"subjects": [subject], "minimum": 1, "exact": None})
    checks = {}
    for group, entry in sorted(found.items()):
        if entry["exact"]:
            amount = f"exactly {entry['exact']}"
        elif entry["minimum"] >= 2:
            amount = "at least two"
        else:
            amount = "at least one"
        checks[f"text-{group}"] = (f"The text names {group.replace('named-', '')}: {amount} visible "
                                   f"(catalog subjects: {', '.join(entry['subjects'])}), each whole inside the frame.")
    for number, (pattern, meaning) in enumerate(lexicon["contacts"], 1):
        if pattern.search(folded):
            checks[f"text-contact-{number}"] = f"The text describes a physical contact: {meaning}, readable at page size."
    visible_elements = set(found) | {key.split("/")[1] for key in references if key.startswith("props/")}
    occupancy = (world or {}).get("initial_occupancy", {})
    for element, zone in sorted(lexicon["occupied_zones"].items()):
        if element in visible_elements:
            residents = sorted(character for character, location in occupancy.items() if location == zone)
            if residents:
                checks[f"text-{element}-residents"] = (
                    f"Show some characters from {zone} ({', '.join(residents)}) when the zone is visible, "
                    "excluding characters staged elsewhere on the page."
                )
    return checks


def missing_checks(required, brief):
    """Return checks an illustration brief neither covers nor explicitly waives."""
    present = set(brief.get("visual_checks", {}))
    waived = brief.get("text_exemptions", {})
    return {key: value for key, value in required.items()
            if key not in present and not (isinstance(waived.get(key), str) and waived[key].strip())}


def slot_findings(page, brief, world=None, lexicon=None):
    required = required_checks(page.get("text", ""), world, brief.get("references", []), lexicon)
    return missing_checks(required, brief)
