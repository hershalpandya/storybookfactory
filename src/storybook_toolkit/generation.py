# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Gemini dispatch policy for editions: the owner's budget, generation packets, review gates, pauses and resume.

The journal is written before the paid request. The HTTP adapter lives in providers/gemini_http.py;
dispatch uses only that adapter and never falls back to another provider.
"""

from collections import Counter, defaultdict
from http.client import HTTPException
import json
from math import isfinite
from time import time
from uuid import uuid4

from . import consistency, edition, journal as journals
from .edition import KINDS
from .edition.scene_layouts import blocker as layout_blocker
from .journal import pause
# The packet estimates its inline size with the adapter's wire encoding.
from .providers.gemini_http import MAX_INLINE_BYTES, MODEL, WIRE_JPEG_QUALITY, Gemini, ProviderStop, wire_bytes
from .store import ProjectError, atomic_writer, emit, fingerprint, load, prose, require, serialized, write_json

RUN = "edition-gemini"
OUTPUT_USD = {"1K": 0.0336, "2K": 0.0504}


def journal(root):
    path = journals.run_path(root, RUN)
    if path.is_file():
        return path, load(path)
    return path, {"format_version": 1, "label": "Edition Gemini generation", "cases": {}, "attempts": {}}


def validate_policy(root, edition, op):
    """Owner-set Gemini budget: model, allowed slots and a lifetime submission ceiling."""
    require(op.get("model") == MODEL, f"The supported Gemini model is {MODEL}")
    slots = op.get("slots")
    require(isinstance(slots, list) and slots and len(set(slots)) == len(slots),
            "List each allowed generation slot once")
    pages = {page["id"] for page in edition["pages"]}
    front = edition["covers"]["front"]
    for slot in slots:
        page, _, kind = str(slot).partition("/")
        require(page != edition["covers"]["back"]["id"], "The private back cover is excluded from generation")
        require((page in pages and kind in KINDS)
                or (page == front["id"] and kind in front["art"])
                or (kind == "profile" and page in edition.get("missing_roots", {})),
                f"Unknown generation slot {slot}")
    used = len(journal(root)[1]["attempts"])
    ceiling = op.get("max_submissions")
    require(type(ceiling) is int and ceiling > used,
            f"max_submissions is a lifetime ceiling and must exceed the {used} submissions already made")
    policy = {"model": MODEL, "max_submissions": ceiling, "slots": slots}
    if "max_inputs" in op:
        require(type(op["max_inputs"]) is int and 1 <= op["max_inputs"] <= 14, "max_inputs must be 1 to 14")
        policy["max_inputs"] = op["max_inputs"]
    if "drift_max" in op:
        require(isinstance(op["drift_max"], (int, float)) and 0 <= op["drift_max"] < 0.5,
                "drift_max is a share of pixels, below 0.5")
        policy["drift_max"] = op["drift_max"]
    if "strict_references" in op:
        require(type(op["strict_references"]) is bool, "strict_references is true or false")
        policy["strict_references"] = op["strict_references"]
    if "max_failures_per_slot" in op:
        require(type(op["max_failures_per_slot"]) is int and 1 <= op["max_failures_per_slot"] <= 5,
                "max_failures_per_slot must be 1 to 5")
        policy["max_failures_per_slot"] = op["max_failures_per_slot"]
    if "checks" in op:
        require(set(op["checks"]) <= {"text", "colouring"}, "checks may list text and colouring")
        policy["checks"] = sorted(set(op["checks"]))
    return policy


def policy(manifest, slot):
    value = manifest.get("generation") or {}
    require(value.get("model") == MODEL, "This edition has no approved Gemini model")
    require(type(value.get("max_submissions")) is int and value["max_submissions"] > 0,
            "Edition needs a positive dispatch budget")
    require(slot in value.get("slots", []), f"{slot} is outside this edition's image budget")
    return value


def generation_packet(root, manifest, slot, record, parent=None, edit=None, *, handoff=None):
    page, kind = slot.split("/")
    require(kind in edition.KINDS or kind == "profile", "Unknown generation slot")
    if kind == "profile":
        definition = manifest["missing_roots"][page]
        packet = {"slot": slot, "kind": kind, "role": None, "brief": definition,
                  "references": [], "image": None, "world": None, "events": [],
                  "reading_box_pt": (0, 0, 250, 250), "comparisons": []}
        packet["visual_dependency"] = edition.art_dependency(packet)
    else:
        packet = handoff if handoff is not None else edition.show_handoff(root, page, kind)[0]
    require(packet["role"] != "back", "Back-cover imagery is private and excluded from generation")
    excluded = {item["image"]["sha256"] for item in manifest["covers"]["back"]["art"].values() if item.get("image")}
    ordered = {}

    def attach(image, role, group):
        path = edition.checked_path(root, image)
        require(image["sha256"] not in excluded, "Private back-cover imagery cannot be attached")
        mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                     ".webp": "image/webp"}.get(path.suffix)
        require(mime_type, "Gemini input must be PNG, JPEG or WebP")
        item = ordered.setdefault(image["sha256"], {**{k: v for k, v in image.items() if k != "rendered"},
                                                     "mime_type": mime_type, "roles": [], "groups": []})
        item["roles"].append(role)
        if group not in item["groups"]:
            item["groups"].append(group)

    if parent == "assigned":
        # Edit the slot's current edition art (any source) so a small fix keeps its approved style.
        require(kind != "profile" and packet.get("image"), "The slot has no assigned art to edit")
        require(prose(edit), "Provide a targeted edit instruction")
        attach(packet["image"], "Edit parent: the page's current approved art", "parent")
        parent = "assigned:" + packet["image"]["sha256"]
    elif parent:
        previous = journals.find_attempt(record, parent)
        require(previous["status"] == "captured" and previous["slot"] == slot
                and previous.get("quality") == "localized" and not previous.get("parent"),
                "An edit needs a reviewed localized defect on an original attempt for this slot")
        require(previous["director_dependency"] == edition.director_dependency(packet),
                "The edit parent belongs to a different scene or reference revision")
        require(prose(edit), "Provide a targeted edit instruction")
        attach({"file": previous["file"], "sha256": previous["image_sha256"]}, "Edit parent", "parent")
    else:
        require(edit is None, "Edit instructions require a parent attachment")
    # Additional images can be mistaken for the edit base.
    edit_only = bool(parent)
    for ref in [] if edit_only else packet["references"]:
        attach(ref["image"], f"{ref['subject']} {ref['state']} {ref['view']}: {ref['visible_features']}", ref["catalog"])
    layout_ref = packet["brief"].get("layout_reference") or {}
    rendered = layout_ref.get("rendered")
    if rendered and not edit_only:
        attach(layout_ref, layout_ref["role"], "props")
    for ref in [] if edit_only else packet["comparisons"]:
        role = ref["role"]
        if rendered:
            role = f"Use only for identity and style; use the rendered layout for composition. {role}"
        attach(ref, role, "props")
    if layout_ref and not rendered and not edit_only:
        attach(layout_ref, layout_ref["role"], "props")
    if kind == "profile":
        for source in packet["brief"].get("sources", []):
            attach(source, source["role"], "props")
    counts = Counter(group for item in ordered.values() for group in item["groups"])
    require(len(ordered) <= 14 and counts["characters"] <= 4 and counts["props"] <= 10,
            "Gemini attachment limit reached (14 total, four character and ten object references)")
    limit = (manifest.get("generation") or {}).get("max_inputs")
    require(limit is None or len(ordered) <= limit,
            f"{len(ordered)} inputs exceed this edition's input budget of {limit}; attach the riskiest references only")
    brief = packet["brief"]
    guidance = {k: v for k, v in brief.items()
                if k not in ("references", "comparison_references", "comparison_pages", "layout_reference",
                             "sources", "text_exemptions", "aspect_ratio", "image_size", "prompt")}
    if rendered or manifest.get("require_scene_layouts"):
        guidance.pop("setting", None)
        guidance.pop("standalone_reason", None)
    if rendered and not edit_only:
        guidance["layout_from_camera"] = rendered["text"]
    snapshot = packet["world"]
    if snapshot:
        visible = set(snapshot["visibility"]) | {move["character"] for move in snapshot["movements"]}
        snapshot = {**snapshot, "before": {k: v for k, v in snapshot["before"].items() if k in visible},
                    "occupancy": {k: v for k, v in snapshot["occupancy"].items() if k in visible}}
    if kind == "colouring":
        snapshot = None
    prompt = "Create one landscape storybook image. Do not draw lettering or a frame."
    if kind == "profile":
        prompt = brief.get("prompt") or ("Create one clean storybook reference portrait. Show the declared view, "
                                         "visible features and pose against a plain background.")
    elif kind == "colouring":
        prompt += " Use only the colouring roster in a simple black outline with large, unshaded fill areas."
    if parent:
        prompt += f" Edit attachment 1 only. Preserve passing details. Change: {edit}."
    prompt += "\n" + json.dumps({"visual_brief": guidance, "world": snapshot,
                                  "role_of_each_attachment": [i["roles"] for i in ordered.values()]},
                                 ensure_ascii=False)
    inline_size = sum((len(wire_bytes(edition.local(root, item["file"]))[0]) + 2) // 3 * 4
                      for item in ordered.values())
    require(inline_size + len(prompt.encode()) + 1024 < MAX_INLINE_BYTES,
            "Gemini inline request is too large")
    return {"slot": slot, "kind": kind, "model": MODEL, "parent": parent, "edit": edit, "prompt": prompt,
            "director_dependency": edition.director_dependency(packet),
            "ordered_inputs": list(ordered.values()), "target_pt": packet["reading_box_pt"][2:],
            "aspect_ratio": brief.get("aspect_ratio") if kind == "profile" and brief.get("aspect_ratio")
            else {"illustration": "3:2", "colouring": "4:3", "profile": "1:1"}[kind],
            "image_size": brief.get("image_size") if kind == "profile" and brief.get("image_size")
            else ("2K" if kind == "illustration" else "1K"),
            "wire_encoding": f"PNG inputs sent as JPEG quality {WIRE_JPEG_QUALITY}"}


def packet_warnings(manifest, packet, comparisons=()):
    """Flag ambiguous or missing references in the dry run."""
    warnings = []
    subjects = defaultdict(set)
    for key, ref in manifest["roots"].items():
        subjects[ref["image"]["sha256"]].add(key.split("/")[1])
    for item in packet["ordered_inputs"]:
        shared = subjects.get(item["sha256"], set())
        if len(shared) >= 3:
            warnings.append(f"{item['file']} is one scene used as the reference for {len(shared)} subjects "
                            f"({', '.join(sorted(shared))}); unrelated characters and elements may carry over")
    attached = {item["sha256"] for item in packet["ordered_inputs"]}
    if packet["kind"] == "illustration" and not packet["parent"] and not any(
            ref["sha256"] in attached for ref in comparisons):
        warnings.append("No neighbour comparison is attached; add comparison_references for identity and style if available")
    return warnings


def capture_pending(root, path, record, ident):
    saved = path.parent / "intake" / ident
    if not saved.is_file():
        return None
    captured = journals.capture(root, RUN, ident, resume=True)
    return captured


def reconcile(root, path, record):
    for ident, item in record["attempts"].items():
        if item["status"] != "pending":
            continue
        captured = capture_pending(root, path, record, ident)
        if not captured:
            pause(path, record, "Interrupted submission needs billing/provider reconciliation", item["slot"], ident)
        if captured["status"] != "captured":
            pause(path, load(path), "Interrupted submission was recovered but the image failed intake", item["slot"], ident)
        record = load(path)
    return record


def dispatch(args, provider=None):
    root = args.project
    manifest = edition.load_edition(root)
    settings = policy(manifest, args.slot)
    path, record = journal(root)
    blocked = None if args.parent else layout_blocker(root, manifest, args.slot)
    if blocked:
        if args.dry_run:
            emit({"slot": args.slot, "blockers": [blocked], "calls": 0})
            return None
        raise ProjectError(blocked)
    page, kind = args.slot.split("/")
    handoff = edition.show_handoff(root, page, kind)[0] if kind != "profile" else None
    packet = generation_packet(root, manifest, args.slot, record, args.parent, args.edit, handoff=handoff)
    if not args.parent:
        blocked = layout_blocker(root, manifest, args.slot, packet["ordered_inputs"])
        require(blocked is None, blocked)
    comparisons = handoff["comparisons"] if handoff else ()
    attempts_count = len(record["attempts"])
    budget = {"used_submissions": attempts_count, "max_submissions": settings["max_submissions"],
              "output_estimate_usd": OUTPUT_USD[packet["image_size"]],
              "pricing": "Output image estimate; input and thinking billed separately"}
    if args.dry_run:
        emit({**packet, "budget": budget, "paused": record.get("paused"),
                      "warnings": packet_warnings(manifest, packet, comparisons)})
        return None
    record = reconcile(root, path, record)
    require(not record.get("paused"), f"Gemini dispatch is paused. Read {path}")
    if settings.get("strict_references"):
        shared = [w for w in packet_warnings(manifest, packet) if "one scene used as the reference" in w]
        require(not shared, "Strict references: " + "; ".join(shared))
    regions = [consistency.parse_region(r) for r in (getattr(args, "region", None) or [])]
    if packet["parent"] and settings.get("drift_max") is not None:
        require(regions, "Declare the edit's target region(s) with --region so drift can be measured")
    active = edition.active_reviews(root)
    if handoff:
        accepted = edition.review_for(active, args.slot, handoff["visual_dependency"])
        if accepted and accepted["decision"] == "approved" and not args.parent:
            emit({"result": "reused", "slot": args.slot, "calls": 0})
            return None
    for ident, previous in reversed(list(record["attempts"].items())):
        if previous["case"] == fingerprint(packet) and previous.get("resubmission") not in ("allow", "used"):
            emit({"result": previous["status"], "attempt": ident, "calls": 0})
            return None
        if previous.get("status") == "captured" and previous.get("quality") is None:
            raise ProjectError(f"Review captured attempt {ident} for {previous['slot']} before another submission")
    if attempts_count >= settings["max_submissions"]:
        pause(path, record, "Pilot submission ceiling reached", args.slot)
    approval = edition.review_for(active, f"director:{args.slot}", packet["director_dependency"])
    require(approval and approval["decision"] == "approved", "Current director approval required before dispatch")
    provider = Gemini() if provider is None else provider
    if not provider.present():
        pause(path, record, "Credential missing or inaccessible in the environment and login Keychain", args.slot)
    case = fingerprint(packet)
    ident = uuid4().hex
    attempt = {"case": case, "status": "pending", "started_at": time(), **packet}
    if regions:
        attempt["target_regions"] = regions
    record["cases"][case] = {"packet": packet, "packet_sha256": case,
                             "contract": {"layout": {kind: {"target_pt": packet["target_pt"]}}}}
    for earlier in record["attempts"].values():
        if earlier["case"] == case and earlier.get("resubmission") == "allow":
            earlier["resubmission"] = "used"
    record["attempts"][ident] = attempt
    write_json(path, record)
    try:
        data, provider_id, usage = provider.send(root, packet)
        with atomic_writer(path.parent / "intake" / ident) as file:
            file.write(data)
        attempt.update(provider_id=provider_id, usage=usage)
        if getattr(provider, "source", None):
            attempt["provider_output"] = provider.source
        if getattr(provider, "model_version", None):
            attempt["model_version"] = provider.model_version
        write_json(path, record)
    except ProviderStop as exc:
        attempt.update(status="pending" if exc.ambiguous else "failed", error=str(exc),
                       provider_id=exc.provider_id, usage=exc.usage)
        pause(path, record, str(exc), args.slot, ident)
    captured = capture_pending(root, path, record, ident)
    if captured["status"] != "captured":
        pause(path, load(path), "Gemini produced unusable image bytes: " + captured["error"], args.slot, ident)
    emit(captured)
    return captured


@serialized
def generate(args):
    return dispatch(args)


@serialized
def record_quality(args):
    path, record = journal(args.project)
    attempt = journals.find_attempt(record, args.attempt)
    require(attempt["status"] == "captured" and not attempt.get("quality"), "Attempt is not awaiting visual review")
    require(prose(args.reviewer) and prose(args.evidence) and isfinite(args.seconds) and args.seconds >= 0, "Name, evidence and time are required")
    limit = (edition.load_edition(args.project).get("generation") or {}).get("drift_max")
    if args.decision == "pass" and attempt.get("parent") and limit is not None:
        # Plan v2 P1: an edit may change only its declared target; everything else must stay as approved.
        attempt["drift"] = measured = consistency.edit_drift(args.project, attempt, limit)
        if measured["rejected"]:
            write_json(path, record)
            raise ProjectError(f"Drift gate: {measured['outside_changed']:.2%} of pixels outside the target changed "
                               f"(limit {limit:.2%}), concentrated changes at {measured['hotspots']}; "
                               "record this edit as localized or unusable")
    attempt.update(quality=args.decision, reviewer=args.reviewer, visual_evidence=args.evidence,
                   review_seconds=args.seconds)
    write_json(path, record)
    manifest = edition.load_edition(args.project)
    if args.decision == "unusable" or args.decision == "localized" and attempt.get("parent"):
        # Plan v2 autonomy: with max_failures_per_slot set, escalate only when one slot keeps failing.
        cap = (manifest.get("generation") or {}).get("max_failures_per_slot")
        failures = sum(1 for other in record["attempts"].values() if other["slot"] == attempt["slot"]
                       and (other.get("quality") == "unusable"
                            or other.get("quality") == "localized" and other.get("parent")))
        if cap is None or failures >= cap:
            pause(path, record, "Visual review stopped the pilot: " + args.evidence, attempt["slot"], args.attempt)
    if len(record["attempts"]) >= manifest["generation"]["max_submissions"] and args.decision != "pass":
        pause(path, record, "Pilot submission ceiling reached before visual acceptance", attempt["slot"], args.attempt)
    emit({"attempt": args.attempt, "decision": args.decision})


@serialized
def resume(args):
    path, record = journal(args.project)
    require(prose(args.owner) and prose(args.evidence), "Record the owner decision and resolution")
    if getattr(args, "resubmit", None):
        failed = journals.find_attempt(record, args.resubmit)
        require(failed["status"] == "failed" and not failed.get("resubmission"),
                "Only a failed attempt not yet released can be resubmitted")
        failed["resubmission"] = "allow"
        if not record.get("paused"):
            record.setdefault("resumptions", []).append({
                "reason": "Owner released a failed attempt for resubmission", "slot": failed["slot"],
                "attempt": args.resubmit, "at": time(), "owner": args.owner, "resolution": args.evidence,
                "resumed_at": time()})
            write_json(path, record)
            emit({"state": "released", "attempt": args.resubmit, "journal": str(path)})
            return
    require(record.get("paused"), "The journal is not paused; use --resubmit to release a failed attempt")
    if args.reconcile:
        attempt = journals.find_attempt(record, args.reconcile)
        require(attempt["status"] == "pending", "Reconciliation only applies to an ambiguous submission")
        require(not (path.parent / "intake" / args.reconcile).exists(), "Saved response will be screened on restart")
        require(args.resubmission in ("allow", "deny"), "Record whether reconciliation permits resubmission")
        attempt.update(status="reconciled", reconciliation=args.evidence, reconciled_by=args.owner,
                       resubmission=args.resubmission)
    require(all(a["status"] != "pending" or (path.parent / "intake" / ident).exists()
                for ident, a in record["attempts"].items()), "Reconcile the pending submission first")
    failed_id = record["paused"].get("attempt")
    if failed_id and args.resubmission == "allow" and record["attempts"][failed_id]["status"] == "failed":
        record["attempts"][failed_id]["resubmission"] = "allow"
    record.setdefault("resumptions", []).append({**record.pop("paused"), "owner": args.owner,
                                                  "resolution": args.evidence, "resumed_at": time(),
                                                  "agent": bool(getattr(args, "agent", False))})
    write_json(path, record)
    emit({"state": "resumed", "journal": str(path)})


@serialized
def readback(args):
    return recover(args)


def recover(args, provider=None):
    """Recover the paused, ambiguous submission by reading its stored interaction back by id (no new generation)."""
    path, record = journal(args.project)
    pending = [(ident, a) for ident, a in record["attempts"].items() if a["status"] == "pending"]
    require(len(pending) == 1, "Read-back needs exactly one pending submission")
    ident, attempt = pending[0]
    require(attempt.get("provider_id"), "No interaction id was recorded; reconcile with provider billing instead")
    require(not (path.parent / "intake" / ident).exists(), "The response is already saved; resume to screen it")
    provider = Gemini() if provider is None else provider
    require(provider.present(), "Credential missing or inaccessible")
    try:
        payload = provider.stored(attempt["provider_id"])
        png, _, usage = provider.decode(payload)
    except (HTTPException, OSError, ValueError) as exc:
        raise ProjectError(f"Stored interaction could not be read back: {type(exc).__name__}") from None
    with atomic_writer(path.parent / "intake" / ident) as file:
        file.write(png)
    attempt.update(usage=usage, provider_output=provider.source, readback="Stored interaction read back by id; "
                   "no new generation")
    if provider.model_version:
        attempt["model_version"] = provider.model_version
    write_json(path, record)
    emit({"recovered": ident, "status": payload.get("status"), "next": "gemini-resume --agent, then review"})


@serialized
def probe(args):
    manifest = edition.load_edition(args.project)
    policy(manifest, args.slot)
    path, record = journal(args.project)
    require(not record.get("paused"), f"Gemini dispatch is paused. Read {path}")
    if not Gemini().present():
        pause(path, record, "Credential missing or inaccessible in the environment and login Keychain", args.slot)
    emit({"credential_present": True, "authenticated_access": "unverified", "calls": 0})



# Upper-bound list prices per token (22 Nov 2026): image output ~USD 30/M gives 0.0336 per 1K image;
# thinking is billed here at the same rate, so the estimate errs high.
INPUT_USD_PER_TOKEN = 0.5e-6
OUTPUT_USD_PER_TOKEN = 30e-6


def cost_estimate(attempt):
    """Upper-bound USD for one submission; a lost but delivered call counts as a full image."""
    usage = attempt.get("usage") or {}
    if usage.get("total_output_tokens") is not None:
        return (usage.get("total_input_tokens", 0) * INPUT_USD_PER_TOKEN
                + usage["total_output_tokens"] * OUTPUT_USD_PER_TOKEN)
    if attempt["status"] == "reconciled" and "billed" in (attempt.get("reconciliation") or ""):
        return OUTPUT_USD[attempt.get("image_size", "2K")] + 0.04
    return 0.0


def benchmark(args):
    path, record = journal(args.project)
    groups = defaultdict(list)
    for ident, attempt in record["attempts"].items():
        if attempt["status"] == "captured":
            edition.checked_path(args.project, {"file": attempt["file"], "sha256": attempt["image_sha256"]})
        groups[attempt["slot"]].append({"id": ident, "status": attempt["status"], "quality": attempt.get("quality"),
                                        "provider_id": attempt.get("provider_id"), "usage": attempt.get("usage"),
                                        "parent": attempt.get("parent"), "review_seconds": attempt.get("review_seconds")})
    first_deliveries = [next((a for a in group if a["status"] == "captured"), {}) for group in groups.values()]
    all_attempts = list(record["attempts"].values())
    review_times = [a["review_seconds"] for a in all_attempts if a.get("review_seconds") is not None]
    emit({"journal": str(path), "submissions": len(all_attempts),
                  "first_submission_passes": sum(group[0]["quality"] == "pass" for group in groups.values()),
                  "first_delivered_image_passes": sum(a.get("quality") == "pass" for a in first_deliveries),
                  "root_calls": sum(a["kind"] == "profile" for a in all_attempts),
                  "targeted_edits": sum(bool(a.get("parent")) for a in all_attempts),
                  "captured_images": sum(a["status"] == "captured" for a in all_attempts),
                  "cost_usd": 0 if not all_attempts else None,
                  "cost_estimate_usd": round(sum(cost_estimate(a) for a in all_attempts), 3),
                  "review_seconds": sum(review_times) if review_times else None,
                  "review_times_measured": len(review_times), "owner_resumptions": len(record.get("resumptions", [])),
                  "paused": record.get("paused"), "slots": groups})

def register(add):
    """Add this module's commands under `storybook edition` through edition.register's helper."""
    parser = add("gemini", generate)
    parser.add_argument("slot")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--parent", help="Attempt to edit, or \"assigned\" for the slot's current edition art")
    parser.add_argument("--edit")
    parser.add_argument("--region", action="append",
                        help="Edit target as fractions x0,y0,x1,y1 (repeatable); required when the policy sets drift_max")
    parser = add("gemini-probe", probe)
    parser.add_argument("slot")
    parser = add("gemini-quality", record_quality)
    parser.add_argument("attempt")
    parser.add_argument("decision", choices=("pass", "localized", "unusable"))
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--seconds", type=float, required=True)
    add("gemini-report", benchmark)
    add("gemini-readback", readback)
    parser = add("gemini-resume", resume)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--reconcile")
    parser.add_argument("--resubmission", choices=("allow", "deny"))
    parser.add_argument("--agent", action="store_true",
                        help="An agent recovered under the owner's standing authorization (not an owner decision)")
    parser.add_argument("--resubmit", metavar="ATTEMPT",
                        help="Release a failed attempt so its identical packet may be sent once more")
