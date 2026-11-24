"""Compile an edition into artwork slots and text layout, report its issues, and publish revisions."""

from collections import defaultdict
from copy import deepcopy

from .. import catalog, render, world
from ..consistency import colouring_metrics
from ..textspec import project_lexicon, slot_findings
from ..store import ProjectError, fingerprint, identifier, load, prose, require, sha256, strings, write_json
from .manifest import DISPOSITIONS, KINDS, MANIFEST, ROLES, checked_path, load_edition, page_by_id, pages
from .reviews import active_reviews, review_for
from .scene_layouts import layered_brief


def art_dependency(packet):
    return fingerprint({k: packet[k] for k in ("slot", "brief", "references", "image", "events", "world", "comparisons")})


def director_dependency(packet):
    return art_dependency({**packet, "image": None})


def text_dependency(edition):
    return fingerprint({
        "source": edition["source"], "adaptation": edition["adaptation"], "layout": edition["layout"],
        "metadata": edition["metadata"],
        "pages": [{k: page[k] for k in ("id", "events", "text", "annotations")} for page in edition["pages"]],
    })


def compile_edition(root, edition):
    ids = [p["id"] for p in pages(edition)]
    require(all(identifier(i) for i in ids) and len(set(ids)) == len(ids), "Page IDs must be unique")
    require(edition["pages"] and set(edition["covers"]) == set(ROLES), "Edition needs story pages and both covers")
    for role, page in edition["covers"].items():
        require(page.get("role") == role, f"Cover must declare its {role} role")
    source = edition["source"]
    for artifact in (source["review"], *source["transcripts"], edition["adaptation"]["artifact"]):
        checked_path(root, artifact)
    if edition["layout"].get("font"):
        checked_path(root, edition["layout"]["font"])
    source_count = len(load(checked_path(root, source["review"]))["passages"])
    events = edition["events"]
    require(isinstance(events, list) and events and all(identifier(e["id"]) for e in events),
            "Edition needs stable event IDs")
    by_event = {event["id"]: event for event in events}
    require(len(by_event) == len(events), "Duplicate event IDs")
    require(all(prose(event.get(field)) for event in events for field in ("actor", "action", "speaker")),
            "Each event needs an actor, action and speaker")
    for event in events:
        require(event["source_passages"] and all(type(index) is int and 0 <= index < source_count
                                                for index in event["source_passages"]),
                f"{event['id']}: invalid source passage")
    ordered = [event for page in edition["pages"] for event in page["events"]]
    require(ordered == list(by_event), "Pages must cover each event once, in story order")
    scene_ids = [p["id"] for p in edition["pages"]]
    snapshots = {}
    if edition.get("world"):
        by_entity = edition["catalogs"].get("characters", {})
        snapshots = {entry["scene"]: entry for entry in
                     world.validate_world(edition["world"], set(by_entity), scene_ids)}
    packets = {}
    for page in pages(edition):
        role = page.get("role")
        require(set(page["art"]) == ({"illustration"} if role else set(KINDS)),
                f"{page['id']}: incorrect art slots")
        if not role:
            require(prose(page["text"]) and page["events"], f"{page['id']}: missing text or events")
            validate_marks(page["text"], page["annotations"])
        for kind, item in page["art"].items():
            require(item["disposition"] in DISPOSITIONS and prose(item["reason"]),
                    f"{page['id']}/{kind}: missing disposition or reason")
            brief = item["brief"]
            require(isinstance(brief, dict) and prose(brief.get("description")),
                    f"{page['id']}/{kind}: missing brief")
            require(strings(brief.get("visual_checks", {})),
                    f"{page['id']}/{kind}: visual checks need stable IDs and observable expectations")
            if brief.get("layout_reference"):
                layout_ref = brief["layout_reference"]
                require(isinstance(layout_ref, dict) and prose(layout_ref.get("role")) and layout_ref.get("sha256"),
                        f"{page['id']}/{kind}: a layout reference needs file, sha256 and role")
                if "rendered" not in layout_ref:
                    checked_path(root, layout_ref)
            brief = layered_brief(brief)
            refs = []
            for key in brief.get("references", []):
                require(key in edition["roots"], f"{page['id']}/{kind}: unresolved reference {key}")
                ref = edition["roots"][key]
                require(ref.get("permitted_uses") and kind in ref["permitted_uses"],
                        f"Reference {key} is excluded from {kind}")
                # Bind the review to the root image and identity definition the director saw.
                refs.append({"id": key, **ref, "identity": catalog.state_definition(edition["catalogs"][ref["catalog"]][ref["subject"]], ref["state"])})
            slot = f"{page['id']}/{kind}"
            packet = {"slot": slot, "role": role, "kind": kind, "brief": brief,
                      "world": snapshots.get(page["id"]) if kind == "illustration" else None, "references": refs,
                      "events": [by_event[i] for i in page.get("events", [])],
                      "image": item.get("image")}
            comparisons = []
            # Legacy briefs named neighbours in comparison_pages, which was never attached.
            legacy = [{"page": other, "kind": "illustration",
                       "role": f"Neighbour page {other}: use its illustration style and preserve the identity of recurring elements"}
                      for other in brief.get("comparison_pages", []) if other != page["id"]]
            for item in brief.get("comparison_references", []) + legacy:
                other = page_by_id(edition, item["page"])
                require(other.get("role") != "back", "The private back cover is excluded from visual references")
                comparison = other["art"][item.get("kind", "illustration")].get("image")
                require(comparison, f"Missing comparison artwork: {item['page']}")
                comparisons.append({"role": item["role"], **comparison})
            packet["comparisons"] = comparisons
            packets[slot] = packet
    return packets


def validate_marks(text, marks):
    require(isinstance(marks, list), "Annotations must be an array")
    for mark in marks:
        start, end = mark["start"], mark["end"]
        require(type(start) is int and type(end) is int and 0 <= start < end <= len(text)
                and text[start:end] == mark["text"] and mark["kind"] in ("silent", "liaison"),
                "Annotation offsets do not match the text")
        if mark["kind"] == "liaison":
            require(type(mark["target"]) is int and end <= mark["target"] < len(text)
                    and text[mark["target"]].isalpha(), "Invalid liaison target")


def layout(root, edition):
    settings = edition["layout"]
    font_path = checked_path(root, settings["font"]) if settings.get("font") else render.FONT
    require(sha256(font_path.read_bytes()) == settings["font_sha256"], "Layout font changed")
    prepared = []
    report = {}
    render.check_titles(edition["metadata"], font_path)
    typeset = render.typeset([(page["id"], [(page["text"], page["annotations"])]) for page in edition["pages"]],
                             font_path, keep_french_punctuation=settings.get("keep_french_punctuation", False))
    for page, (lines, height, spans) in zip(edition["pages"], typeset):
        prepared.append((page, lines, height))
        report[page["id"]] = {"spans": spans[0], "reading": render.artwork_boxes(height),
                              "duplex_reverse": render.artwork_boxes(height, True)}
    for role, page in edition["covers"].items():
        report[page["id"]] = {"reading": {"illustration": render.COVER_BOXES[role]}}
    return font_path, prepared, report


def v2_issues(root, edition, page, kind, item, image):
    """Plan v2 checks, enabled per edition by the generation policy's ``checks`` list."""
    enabled = set((edition.get("generation") or {}).get("checks", []))
    found = []
    if "text" in enabled and kind == "illustration" and not page.get("role"):
        missing = slot_findings(page, item["brief"], edition.get("world"), project_lexicon(root))
        if missing:
            found.append("text check missing: " + ", ".join(sorted(missing)))
    if "colouring" in enabled and kind == "colouring" and image:
        try:
            metrics = colouring_metrics(checked_path(root, image))
        except ProjectError:
            return found
        if metrics["grey_share"] > 0.02:
            found.append(f"colouring has grey fills or shading ({metrics['grey_share']:.1%} mid-tone)")
        if not 3 <= metrics["stroke_px"] <= 8:
            found.append(f"colouring line weight {metrics['stroke_px']} px outside 4-8 px at 1000 px width")
    return found


def inventory(root, edition, packets):
    reviews = active_reviews(root)
    pixels = defaultdict(list)
    rows = []
    for number, page in enumerate(pages(edition)):
        for kind, item in page["art"].items():
            slot = f"{page['id']}/{kind}"
            packet = packets[slot]
            issues = []
            image = item.get("image")
            if image:
                try:
                    checked_path(root, image)
                except ProjectError as exc:
                    issues.append(str(exc))
                pixels[image["pixel_sha256"]].append(slot)
            else:
                issues.append("missing assignment")
            if item["disposition"] != "reuse":
                issues.append(f"{item['disposition']} artwork")
            for ref in packet["references"]:
                try:
                    checked_path(root, ref["image"])
                except ProjectError as exc:
                    issues.append(str(exc))
            for comparison in packet["comparisons"]:
                try:
                    checked_path(root, comparison)
                except ProjectError as exc:
                    issues.append(str(exc))
            approval = review_for(reviews, slot, art_dependency(packet))
            if not approval or approval["decision"] != "approved":
                issues.append("visual approval missing, rejected or stale")
            issues.extend(v2_issues(root, edition, page, kind, item, image))
            rows.append({"slot": slot, "story_page": number if not page.get("role") else None,
                         "disposition": item["disposition"], "reason": item["reason"], "image": image,
                         "review": approval, "issues": issues})
    duplicates = [slots for slots in pixels.values() if len(slots) > 1]
    by_slot = {row["slot"]: row for row in rows}
    for group in duplicates:
        for slot in group:
            by_slot[slot]["issues"].append("duplicate pixels in " + ", ".join(s for s in group if s != slot))
    return {"revision": edition["revision"], "slots": rows, "duplicate_pixels": duplicates,
            "text_review": review_for(reviews, "text", text_dependency(edition)),
            "owner_proof": review_for(reviews, "owner-proof", edition["revision"])}


def show_handoff(root, page=None, kind=None):
    edition = load_edition(root)
    packets = compile_edition(root, edition)
    _, _, boxes = layout(root, edition)
    selected = []
    for packet in packets.values():
        page_id, packet_kind = packet["slot"].split("/")
        if page is not None and page_id != page or kind is not None and packet_kind != kind:
            continue
        for ref in packet["references"]:
            checked_path(root, ref["image"])
        for comparison in packet["comparisons"]:
            checked_path(root, comparison)
        selected.append({**packet, "visual_dependency": art_dependency(packet),
                         "reading_box_pt": boxes[page_id]["reading"][packet_kind]})
    require(selected, "No matching storybook slots")
    return selected


def changes(root, before, after):
    old, new = [compile_edition(root, edition) for edition in (before, after)]
    reviews = active_reviews(root)
    reopened = []
    for slot in sorted(set(old) | set(new)):
        previous = old.get(slot)
        current = new.get(slot)
        if previous and current and art_dependency(previous) == art_dependency(current):
            continue
        reasons = ([k for k in ("brief", "references", "image", "events", "world", "comparisons") if previous[k] != current[k]]
                   if previous and current else ["slot added" if current else "slot removed"])
        reopened.append({"slot": slot, "reasons": reasons, "previous": review_for(reviews, slot, art_dependency(previous))
                         if previous else None, "next": "review staging and pixels" if current else "archive"})
    return {"revision": after["revision"], "visual_changes": reopened,
            "text_layout_reopened": text_dependency(before) != text_dependency(after),
            "owner_proof_reopened": before["revision"] != after["revision"]}


def publish(root, draft, parent=None):
    draft = deepcopy(draft)
    draft.pop("revision", None)
    draft["parent"] = parent
    compile_edition(root, draft)
    draft["revision"] = fingerprint(draft)
    write_json(root / "revisions" / f"{draft['revision']}.json", draft)
    write_json(root / MANIFEST, draft)
    return draft
