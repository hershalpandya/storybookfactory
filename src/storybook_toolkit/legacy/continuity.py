"""Structured story beats and staged mechanism paths."""

import re

from ..store import identifier, load, prose, require, sha256, strings


def beat_ledger(root, plan, adaptation):
    ledger = load(root / "beats.json")
    require(isinstance(ledger, dict) and ledger.get("adaptation_sha256") == plan["adaptation_sha256"],
            "beats.json must identify the current adaptation")
    beats = ledger.get("beats")
    require(isinstance(beats, dict) and bool(beats), "beats.json requires an ordered beats object")
    for ident, beat in beats.items():
        require(identifier(ident) and isinstance(beat, dict), "Invalid beat ID or definition")
        passage = beat.get("passage")
        require(type(passage) is int and 0 <= passage < len(adaptation["passages"]), f"{ident} needs an adapted passage")
        sources = beat.get("source_passages")
        require(isinstance(sources, list) and bool(sources) and all(type(i) is int for i in sources)
                and set(sources) <= set(adaptation["passages"][passage]["source_passages"]),
                f"{ident} needs linked reviewed source passages")
        require(prose(beat.get("description")) and prose(beat.get("check")) and
                ("correction" not in beat or prose(beat["correction"])), f"{ident} needs a beat description and observable check")
        subjects = beat.get("subjects", [])
        require(isinstance(subjects, list) and all(identifier(subject) for subject in subjects)
                and len(subjects) == len(set(subjects)), f"{ident} needs unique subject IDs")

    assigned = []
    for page in plan["pages"]:
        ids = page.get("beats")
        require(isinstance(ids, list) and all(identifier(ident) and ident in beats for ident in ids),
                f"{page['id']} needs beat IDs from beats.json")
        staged = page["characters"].keys() | page["props"].keys()
        for ident in ids:
            missing = set(beats[ident].get("subjects", [])) - staged
            require(not missing, f"{page['id']} beat {ident} is missing staged subjects: {', '.join(sorted(missing))}")
        indices = [beats[ident]["passage"] for ident in ids]
        require(indices == sorted(indices) and list(dict.fromkeys(indices)) == page["passages"],
                f"{page['id']} needs ordered beats covering each assigned passage")
        for passage in page["passages"]:
            covered = {source for ident in ids if beats[ident]["passage"] == passage
                       for source in beats[ident]["source_passages"]}
            require(covered == set(adaptation["passages"][passage]["source_passages"]),
                    f"{page['id']} beats omit a reviewed source link from passage {passage}")
        assigned.extend(ids)
    require(assigned == list(beats), "Pages must cover every declared beat exactly once and in ledger order")
    return beats


def mechanisms(page, entries):
    routes = page.get("mechanisms", {})
    require(isinstance(routes, dict), f"{page['id']} needs a mechanisms object")
    anchors = {}
    for kind, catalog in entries.items():
        for ident in page[kind]:
            anchors.update({f"{ident}.{key}": value for key, value in catalog[ident].get("anchors", {}).items()})
    for ident, route in routes.items():
        require(identifier(ident) and isinstance(route, dict) and prose(route.get("description")),
                "Each mechanism needs an ID and description")
        path = route.get("path")
        require(isinstance(path, list) and len(path) >= 2 and
                all(isinstance(point, str) and point in anchors for point in path) and len(set(path)) == len(path),
                f"{ident} needs a continuous ordered path of distinct staged catalog anchors")
    return {ident: {**route, "labels": {point: anchors[point] for point in route["path"]}}
            for ident, route in routes.items()}


def validate_production_catalog(entries):
    for catalog in entries.values():
        for ident, entry in catalog.items():
            fields = entry.get("state_fields", [])
            require(isinstance(fields, list) and all(identifier(key) for key in fields)
                    and len(set(fields)) == len(fields) and not set(fields) & entry["facts"].keys(),
                    f"{ident} needs distinct state_fields separate from permanent facts")
            for state, definition in entry["states"].items():
                extra = definition["facts"].keys() - set(fields)
                require(not extra, f"{ident}/{state} changes undeclared or permanent facts: {', '.join(sorted(extra))}")
            require(strings(entry.get("anchors", {})), f"{ident} needs named anchors with descriptions")


def comparison_images(root, plan, contract, kind, assets):
    """Select the most recent registered illustration for each returning subject."""
    from .staging import image_roster

    subject_ids = set(image_roster(contract, kind))
    registered = {item["page"]: item for item in assets if item["kind"] == "illustration"}
    earlier = []
    for page in plan["pages"]:
        if page["id"] == contract["page"]:
            if kind == "colouring":
                earlier.append(page)
            break
        earlier.append(page)

    comparisons = []
    for page in reversed(earlier):
        item = registered.get(page["id"])
        shared = subject_ids & (page["characters"].keys() | page["props"].keys())
        if item and shared:
            sha = item["sha256"]
            require(isinstance(sha, str) and re.fullmatch("[0-9a-f]{64}", sha)
                    and item["file"] == f"assets/{sha}.png", "Invalid continuity asset path")
            require(sha256((root / item["file"]).read_bytes()) == sha,
                    f"Previous art for {page['id']} changed since registration")
            comparisons.append({"page": page["id"], "sha256": sha, "file": item["file"], "subjects": sorted(shared)})
            subject_ids -= shared
        if not subject_ids:
            break
    return comparisons
