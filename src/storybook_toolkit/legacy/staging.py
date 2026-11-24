"""Compile a page's set, blocking, references and visual acceptance contract."""

import json
from pathlib import Path

from ..catalog import KINDS, catalogs, state_references
from ..store import counts, fingerprint, identifier, load, project_command, prose, require, strings, write_json

IMAGE_CHECKS = {"anatomy", "identity", "set_continuity", "visible_action", "page_ready", "simple_line_art"}


def validate_placement(context, entry, kind, position):
    definition = entry["states"][position["state"]]
    view = position.get("view")
    require(identifier(view) and view in definition["profiles"] and prose(position.get("position")),
            f"{context} needs a declared view and a blocking position")
    facts = {**entry["facts"], **definition["facts"]}
    hidden = position.get("hidden_facts", {})
    require(strings(hidden) and hidden.keys() <= facts.keys(), f"{context} needs known hidden facts with reasons")
    if kind == "characters":
        require(prose(position.get("action")), f"{context} needs an action")
    else:
        require(prose(position.get("use")), f"{context} needs a description of its role in the set")

    if "parts" in entry:
        require(not {"visible_legs", "occlusion"} & position.keys(),
                f"{context} uses visible_parts and occluded_parts for named parts")
        visible = position.get("visible_parts")
        totals = entry["parts"]
        require(counts(visible) and visible.keys() == totals.keys(),
                f"{context} needs a nonnegative integer visible count for every named part")
        for part, count in visible.items():
            require(count <= totals[part], f"{context} has {count} visible {part}, exceeding the catalog total of {totals[part]}")
        occluded = {key for key, count in visible.items() if count < totals[key]}
        reasons = position.get("occluded_parts", {})
        require(strings(reasons) and reasons.keys() == occluded,
                f"{context} needs an occlusion reason for each partly or fully hidden part")
    else:
        require(not {"visible_parts", "occluded_parts"} & position.keys(),
                f"{context} needs named parts in its catalog to plan their visibility")
        if kind == "characters":
            count = position.get("visible_legs")
            require(type(count) is int and 0 <= count <= entry["legs"],
                    f"{context} needs a plausible planned visible leg count")
            if count < entry["legs"]:
                require(prose(position.get("occlusion")), f"{context} needs a reason for the hidden legs")


def placements(page, entries, kind, previous):
    roster = page.get(kind)
    require(isinstance(roster, dict), f"{page['id']} requires a {kind} object")
    for ident, position in roster.items():
        context = f"{page['id']} {ident}"
        require(ident in entries and isinstance(position, dict), f"{context} needs an individual catalog entry")
        entry = entries[ident]
        state = position.get("state")
        require(identifier(state) and state in entry["states"], f"{context} needs a declared state")
        change = position.get("state_change")
        old = previous.get(ident)
        if old is not None and old != state:
            require(prose(change), f"{context} changes from {old} to {state} without a story reason")
        else:
            require(change is None, f"{context} has a state-change note without a transition")
        previous[ident] = state
        validate_placement(context, entry, kind, position)


def validate_staging(root, plan):
    entries = catalogs(root)
    from .continuity import mechanisms, validate_production_catalog
    production = plan["format_version"] == 3
    if production:
        validate_production_catalog(entries)
    previous = {}
    from .scenes import all_pages, image_kinds
    for page in all_pages(plan):
        cover = "colouring" not in image_kinds(plan, page["id"])
        set_design = page.get("set")
        require(isinstance(set_design, dict) and all(prose(set_design.get(key)) for key in
                ("location", "layout", "lighting", "camera")),
                f"{page['id']} needs set location, layout, lighting and camera prose")
        for kind in KINDS:
            placements(page, entries[kind], kind, {} if cover else previous)
        require(isinstance(page.get("checks"), dict) and bool(page["checks"]) and strings(page["checks"])
                and not page["checks"].keys() & IMAGE_CHECKS
                and (not production or all(not key.startswith(("beat-", "continuity-")) for key in page["checks"])),
                f"{page['id']} needs observable story and set checks with non-reserved keys")
        if production:
            mechanisms(page, entries)
        if cover:
            continue
        if production:
            require("colouring_placements" in page, f"{page['id']} needs independent colouring_placements")
        subject = page.get("colouring_subjects")
        require(isinstance(subject, list) and bool(subject) and all(isinstance(i, str) for i in subject)
                and len(set(subject)) == len(subject) and set(subject) <= page["characters"].keys() | page["props"].keys(),
                f"{page['id']} needs unique colouring subjects selected from the staged cast and props")
        if "colouring_placements" in page:
            alternate = page["colouring_placements"]
            require(isinstance(alternate, dict) and alternate.keys() == set(subject),
                    f"{page['id']} needs one colouring placement per colouring subject")
            for ident, position in alternate.items():
                context = f"{page['id']} colouring {ident}"
                require(isinstance(position, dict) and not {"state", "state_change"} & position.keys(),
                        f"{context} must inherit the illustration state")
                kind = "characters" if ident in page["characters"] else "props"
                validate_placement(context, entries[kind][ident], kind,
                                   {**position, "state": page[kind][ident]["state"]})


def compile_subject(entry, kind, position, refs):
    state = entry["states"][position["state"]]
    view = position["view"]
    row = {
        "kind": kind, "name": entry["name"], "description": entry["description"],
        "state_description": state["description"], "blocking": position,
        "profile_description": state["profiles"][view],
        "references": sorted(refs, key=lambda ref: (ref["view"] != view, ref["view"])),
        "visible_facts": {key: value for key, value in {**entry["facts"], **state["facts"]}.items()
                          if key not in position.get("hidden_facts", {})},
    }
    if "parts" in entry:
        row["parts"] = entry["parts"]
        if kind == "characters":
            row["form"] = entry["form"]
    elif kind == "characters":
        row.update(species=entry["species"], anatomical_legs=entry["legs"])
    return row


def compile_page(root, plan, page, entries, passages):
    roster = {}
    colouring_roster = {}
    for kind in KINDS:
        for ident, position in sorted(page[kind].items()):
            entry = entries[kind][ident]
            refs = state_references(root, kind, ident, entry, position["state"], plan["format_version"] == 3)
            roster[ident] = compile_subject(entry, kind, position, refs)
            alternate = page.get("colouring_placements", {}).get(ident)
            if alternate is not None:
                colouring_roster[ident] = compile_subject(
                    entry, kind, {**alternate, "state": position["state"]}, refs
                )
    pages = plan["pages"]
    prior = {}
    if page in pages:
        index = pages.index(page)
        neighbors = [p for p in pages[max(0, index - 1):index + 2] if p is not page]
        for earlier in pages[:index]:
            for kind in KINDS:
                for ident, position in earlier[kind].items():
                    if ident in roster:
                        prior[ident] = {"page": earlier["id"], "state": position["state"]}
    else:
        neighbors = pages if len(pages) == 1 else [pages[0], pages[-1]]
    contract = {
        "last_appearances": prior,
        "adjacent_sets": [{key: p[key] for key in ("id", "set", "characters", "props")} for p in neighbors],
        "contract_version": 1, "adaptation_sha256": plan["adaptation_sha256"], "page": page["id"],
        "passages": [passages[i]["text"] for i in page.get("passages", [])], "set": page["set"], "roster": roster,
        "illustration": page["scene"], "colouring": page.get("colouring"),
        "colouring_subjects": page.get("colouring_subjects", []), "checks": page["checks"],
    }
    if plan["format_version"] == 3:
        from .continuity import mechanisms
        ledger = load(root / "beats.json")["beats"]
        contract["contract_version"] = 2
        contract["beats"] = {key: ledger[key] for key in page.get("beats", [])}
        reviewed = load(root / "reviewed-story.json")["passages"]
        source_indices = {i for beat in contract["beats"].values() for i in beat["source_passages"]}
        contract["reviewed_sources"] = {str(i): reviewed[i] for i in sorted(source_indices)}
        contract["mechanisms"] = mechanisms(page, entries)
        from .book import approved_layout
        layout = approved_layout(root, plan)
        contract["layout"] = layout["pages"][page["id"]]
        contract["typography"] = {key: layout[key] for key in ("metadata_sha256", "font_sha256")}
    if colouring_roster:
        contract["colouring_roster"] = colouring_roster
    return contract


DIRECTOR_CHECKS = (
    "story_beat_and_complete_roster", "set_layout_and_adjacent_page_continuity",
    "state_transitions_and_reference_match", "camera_blocking_and_anatomy", "colouring_scope",
)


def page_contract(root, page_id, plan=None):
    from .scenes import all_pages, validated_plan
    if plan is None:
        plan = validated_plan(root)
    require(plan["format_version"] >= 2, "Staged workflow requires scenes format_version 2 or later")
    page = next((page for page in all_pages(plan) if page["id"] == page_id), None)
    require(page is not None, f"Unknown page {page_id}")
    return compile_page(root, plan, page, catalogs(root), load(root / "adapted-story.json")["passages"])


def director_checks(contract):
    return DIRECTOR_CHECKS if contract["colouring"] else DIRECTOR_CHECKS[:-1]


def review_evidence(record, expected):
    require(isinstance(record, dict) and prose(record.get("reviewer")), "Review needs a named reviewer")
    checks = record.get("checks")
    require(isinstance(checks, dict) and checks.keys() == set(expected), "Review needs evidence for every check")
    for key, check in checks.items():
        require(isinstance(check, dict) and check.get("result") in ("pass", "fail", "uncertain")
                and prose(check.get("evidence")), f"Review check {key} needs a result and evidence")
    return [key for key, check in checks.items() if check["result"] != "pass"]


def preflight(args):
    contract = page_contract(args.project, args.page)
    print(json.dumps({
        "contract_sha256": fingerprint(contract), "checks": list(director_checks(contract)), "contract": contract,
    }, ensure_ascii=False, indent=2))


def review_set(args):
    contract = page_contract(args.project, args.page)
    record = load(args.review)
    require(isinstance(record, dict) and record.get("contract_sha256") == fingerprint(contract),
            "Set review must identify the current contract from set-preflight")
    failures = review_evidence(record, director_checks(contract))
    write_json(set_review_path(args.project, args.page), record)
    require(not failures, "Set review blocked on " + ", ".join(failures))


def set_review_path(root, page):
    return root / "set-reviews" / f"{page}.json"


def approved_set(root, contract):
    record = load(set_review_path(root, contract["page"]))
    require(isinstance(record, dict) and record.get("contract_sha256") == fingerprint(contract), "Set review is stale")
    failures = review_evidence(record, director_checks(contract))
    require(not failures, "Set review blocked on " + ", ".join(failures))
    return record


def image_roster(contract, kind):
    require(kind in ("illustration", "colouring") and contract[kind], "Image kind unavailable for this page")
    if kind == "illustration":
        return contract["roster"]
    roster = contract.get("colouring_roster", contract["roster"])
    return {ident: roster[ident] for ident in contract["colouring_subjects"]}


def expected_image(contract, kind):
    colouring = kind == "colouring"
    roster = image_roster(contract, kind)
    subjects = {}
    for ident, item in roster.items():
        expected = {"view": item["blocking"]["view"], "facts": item["visible_facts"]}
        if colouring:
            # Uncoloured line art still needs silhouette, anatomy and recognizable structure.
            expected["facts"] = {key: value for key, value in expected["facts"].items()
                                 if not key.startswith(("colour-", "color-"))}
        if "parts" in item:
            expected["visible_parts"] = item["blocking"]["visible_parts"]
        elif item["kind"] == "characters":
            expected["visible_legs"] = item["blocking"]["visible_legs"]
        subjects[ident] = expected
    checks = dict(sorted(contract["checks"].items())) if not colouring else {
        "simple_line_art": "Fresh outline suitable for colouring, depicting the requested story moment."
    }
    if any("visible_parts" in item for item in subjects.values()):
        checks["anatomy"] = "Check that visible body and mechanical parts align with each subject's view, pose and occlusion."
    elif any("visible_legs" in item for item in subjects.values()):
        checks["anatomy"] = "All visible heads, torsos and limbs align with each animal's view, pose and occlusion."
    if any(item["kind"] == "characters" for item in roster.values()):
        checks["identity"] = "Every individual matches the approved reference and nearby pages wherever visible."
    if any(item["kind"] == "props" for item in roster.values()):
        checks["set_continuity"] = "Visible props match their approved profiles, positions and planned arrangement."
    if not colouring:
        checks.update({f"beat-{key}": beat["check"] for key, beat in contract.get("beats", {}).items()})
    checks["visible_action"] = "The requested action and blocking read clearly at page size."
    checks["page_ready"] = "The image has clean framing, no unwanted text, and reads clearly at page size."
    result = {"subjects": subjects, "extras": [], "checks": checks}
    if not colouring and contract.get("mechanisms"):
        result["mechanisms"] = {key: route["path"] for key, route in contract["mechanisms"].items()}
    return result


def generation_packet(root, contract, kind, *, legacy_references=False, reference_offset=0):
    approved_set(root, contract)
    expected = expected_image(contract, kind)
    colouring = kind == "colouring"
    prompt = ["Create simple black outline art for a children's colouring page." if colouring else
              "Create a children's storybook illustration.", contract[kind]]
    if not colouring:
        prompt += [f"{key.capitalize()}: {value}" for key, value in sorted(contract["set"].items())]
    if "layout" in contract:
        w, h = contract["layout"][kind]["target_pt"]
        prompt.append(f"Compose for an artwork slot {w:g} by {h:g} points (width by height).")
    if not colouring:
        for beat in contract.get("beats", {}).values():
            if "correction" in beat:
                prompt.append(f"Story correction to preserve: {beat['correction']}")
        for key, route in contract.get("mechanisms", {}).items():
            points = " → ".join(f"{point} ({route['labels'][point]})" for point in route["path"])
            prompt.append(f"{key}: {route['description']} Continuous route: {points}.")
    references = []
    attachment_indexes = {}
    roster = image_roster(contract, kind)
    for ident, subject in expected["subjects"].items():
        item = roster[ident]
        position = item["blocking"]
        prompt.append(f"{item['name']} ({ident}). {item['description']} {item['state_description']} "
                      f"{position['position']}. {position.get('action', position.get('use'))}. "
                      f"View {position['view']}. {item['profile_description']}")
        for key, value in sorted(subject["facts"].items()):
            prompt.append(f"{key}: {value}")
        if "form" in item:
            prompt.append(f"Form: {item['form']}")
        if "visible_parts" in subject:
            for part, count in sorted(subject["visible_parts"].items()):
                reason = position.get("occluded_parts", {}).get(part)
                line = f"{part}: {item['parts'][part]} total, {count} visible."
                prompt.append(f"{line} Occlusion: {reason}" if reason else line)
        elif "visible_legs" in subject:
            prompt.append(f"Anatomical legs: {item['anatomical_legs']}. Visible legs: {subject['visible_legs']}. "
                          + (position.get("occlusion") or ""))
        ref = item["references"][0]
        role = {"subject": ident, "view": ref["view"]}
        index = None if legacy_references else attachment_indexes.get(ref["sha256"])
        if index is None:
            index = len(references)
            attachment_indexes[ref["sha256"]] = index
            references.append({"subject": ident, **ref})
        else:
            attachment = references[index]
            roles = attachment.setdefault("roles", [{"subject": attachment["subject"], "view": attachment["view"]}])
            roles.append(role)
        prompt.append(f"Reference {index + 1 + reference_offset} shows {item['name']} in the {ref['view']} view "
                      "for identity or construction in this state.")
    prompt.extend(expected["checks"].values())
    prompt.append("Depict only the listed subjects. Keep printed story text out of the picture.")
    return {"packet_version": 1, "page": contract["page"], "kind": kind,
            "contract_sha256": fingerprint(contract), "prompt": "\n".join(prompt), "references": references,
            "expected": expected}


def register(subparsers):
    p = project_command(subparsers, "set-preflight", "Print the set director's review packet", preflight)
    p.add_argument("page")
    p = project_command(subparsers, "review-set", "Record the set director's evidence", review_set)
    p.add_argument("page")
    p.add_argument("review", type=Path)
