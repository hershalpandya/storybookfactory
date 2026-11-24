"""Bounded, human-authorized rounds for artwork created in an external UI."""

from pathlib import Path
from time import time
from uuid import uuid4

from . import edition, journal as journals
from .store import emit, fingerprint, identifier, load, prose, require, serialized, strings, write_json


def path_for(root, run):
    require(identifier(run), "Invalid art round ID")
    return journals.run_path(root, f"art-{run}")


def case_packet(record, attempt):
    case = record["cases"][attempt["case"]]
    packet = case["packet"]
    require(case["packet_sha256"] == fingerprint(packet), "Frozen art packet changed")
    return packet


def merge_checks(checks, additions):
    require(strings(additions), "Visual checks need stable IDs and an observable expectation")
    for key, expected in additions.items():
        require(key not in checks or checks[key] == expected,
                f"Cannot replace frozen visual check {key}")
        checks[key] = expected


@serialized
def start_round(args):
    spec = load(args.plan)
    path = path_for(args.project, args.run)
    require(not path.exists(), "Art round already exists")
    for prior in journals.journal_paths(args.project, "art-"):
        require(load(prior).get("closed"), f"Review and close the previous art round: {prior.parent.name}")
    require(prose(spec["provider"]) and prose(spec["objective"]), "Name the explicitly authorized provider and objective")
    require(type(spec["limit"]) is int and spec["limit"] > 0, "Specify the round's submission limit")
    manifest = edition.load_edition(args.project)
    slots = edition.compile_edition(args.project, manifest)
    require(spec["slots"] and set(spec["slots"]) <= slots.keys(), "The round contains an unknown artwork slot")
    require(all(slots[slot]["role"] != "back" for slot in spec["slots"]),
            "The private back cover is excluded from art rounds")
    write_json(path, {"format_version": 1, "label": spec["objective"], "provider": spec["provider"],
                      "round": spec, "revision": manifest["revision"], "cases": {}, "attempts": {}})
    emit({"round": args.run, "journal": str(path), "limit": spec["limit"], "slots": spec["slots"]})


@serialized
def reserve(args):
    root = args.project
    path = path_for(root, args.run)
    round_record = load(path)
    require(not round_record.get("closed"), "This art round is closed")
    require(len(round_record["attempts"]) < round_record["round"]["limit"], "Art round submission limit reached")
    require(args.slot in round_record["round"]["slots"], "This slot is outside the art round")
    require(all(a.get("quality") for a in round_record["attempts"].values()),
            "Capture and review the current submission, or close the round if intake failed")
    manifest = edition.load_edition(root)
    require(manifest["revision"] == round_record["revision"], "Edition changed after the art round opened")
    page, kind = args.slot.split("/")
    slot = edition.show_handoff(root, page, kind)[0]
    dependency = edition.director_dependency(slot)
    shot = load(args.shot)
    require(prose(shot.get("prompt")), "Record the exact generation prompt")
    checks = {}
    merge_checks(checks, slot["brief"].get("visual_checks", {}))
    excluded = manifest["covers"]["back"]["art"]["illustration"].get("image", {}).get("sha256")
    used = set()
    for ref in shot["inputs"]:
        require(prose(ref["role"]), "Label every attachment with its role")
        edition.checked_path(root, ref)
        require(ref["sha256"] != excluded and ref["sha256"] not in used,
                "Attachments must have distinct digests and exclude the private back cover")
        used.add(ref["sha256"])
    parent = shot.get("edit_parent")
    previous_rounds = [
        load(journal) for journal in journals.journal_paths(root, "art-")
    ]
    for previous in previous_rounds:
        require(not any(
            other["slot"] == args.slot and other.get("edit_parent")
            and other.get("quality") in ("localized", "unusable")
            and other["director_dependency"] == dependency
            for other in previous["attempts"].values()
        ), "A targeted correction failed for this staging; revise the brief before another submission")
    if parent:
        prior_path = path_for(root, parent["round"])
        prior_round = load(prior_path)
        prior_attempt = journals.find_attempt(prior_round, parent["attempt"])
        require(prior_attempt.get("quality") == "localized" and prior_attempt["slot"] == args.slot,
                "A targeted correction needs a localized failure for the same slot")
        require(not prior_attempt.get("edit_parent"),
                "The targeted correction was already attempted; revise staging before trying a new composition")
        require(prior_attempt["director_dependency"] == dependency,
                "The scene changed since the parent was reviewed; prepare a new composition")
        require(shot["inputs"] and shot["inputs"][0]["sha256"] == prior_attempt["image_sha256"],
                "Attach the exact previously reviewed image first")
        for previous in previous_rounds:
            require(all(other.get("edit_parent") != parent for other in previous["attempts"].values()),
                    "A targeted correction has already been submitted for this parent")
        merge_checks(checks, case_packet(prior_round, prior_attempt)["checks"])
    merge_checks(checks, shot.get("checks", {}))
    require(len(checks) >= 2, "Freeze at least two observable criteria")
    ident = uuid4().hex
    comparison_inputs = [
        {"role": f"{ref['subject']} / {ref['view']}", **ref["image"]} for ref in slot["references"]
    ] + slot["comparisons"]
    if slot["image"]:
        comparison_inputs.append({"role": "Current assigned artwork", **slot["image"]})
    packet = {"kind": kind, "slot": args.slot, "director_dependency": dependency,
              "prompt": shot["prompt"], "inputs": shot["inputs"], "checks": checks,
              "comparison_inputs": comparison_inputs, "target_pt": slot["reading_box_pt"][2:]}
    if args.dry_run:
        emit({"round": args.run, "remaining": round_record["round"]["limit"] - len(round_record["attempts"]),
                      **packet})
        return
    round_record["cases"][ident] = {
        "packet": packet, "packet_sha256": fingerprint(packet),
        "contract": {"layout": {kind: {"target_pt": slot["reading_box_pt"][2:]}}}}
    round_record["attempts"][ident] = {"case": ident, "status": "pending", "started_at": time(),
                                       "director_dependency": dependency, "slot": args.slot, "edit_parent": parent}
    write_json(path, round_record)
    emit({"attempt": ident, "journal": str(path), **packet})


@serialized
def capture(args):
    path = path_for(args.project, args.run)
    record = load(path)
    require(not record.get("closed"), "This art round is closed")
    captured = journals.capture(args.project, path.parent.name, args.attempt, file=args.file, resume=args.resume,
                                error=args.error)
    emit(captured)


@serialized
def review(args):
    path = path_for(args.project, args.run)
    record = load(path)
    attempt = journals.find_attempt(record, args.attempt)
    require(not record.get("closed") and attempt["status"] == "captured",
            "The result is unavailable for review")
    expected = case_packet(record, attempt)["checks"]
    edition.checked_path(args.project, {"file": attempt["file"], "sha256": attempt["image_sha256"]})
    notes = load(args.observations)
    require(prose(notes.get("reviewer")) and set(notes["criteria"]) == set(expected),
            "Identify the reviewer and report every frozen criterion")
    for key, observed in notes["criteria"].items():
        require(observed["decision"] in ("pass", "fail", "uncertain") and prose(observed["evidence"]),
                f"Record the observed feature and image location for {key}")
    failed = [key for key, item in notes["criteria"].items() if item["decision"] != "pass"]
    repair = notes.get("repair")
    if repair is not None:
        require(failed and prose(repair.get("region")) and prose(repair.get("instruction"))
                and repair.get("criteria") and set(repair["criteria"]) == set(failed),
                "A localized repair must name one visible region, instruction and all blocking criteria")
    quality = "pass" if not failed else "localized" if repair or len(failed) == 1 else "unusable"
    if attempt.get("visual_review"):
        attempt.setdefault("review_history", []).append({"quality": attempt["quality"],
                                                          "review": attempt["visual_review"]})
    attempt.update(quality=quality, visual_review=notes)
    write_json(path, record)
    emit({"attempt": args.attempt, "quality": attempt["quality"], "failed": failed})


@serialized
def close(args):
    path = path_for(args.project, args.run)
    record = load(path)
    require(not record.get("closed") and prose(args.lessons), "Record what the round changes about the next approach")
    require(all(a["status"] == "failed" or a.get("quality") for a in record["attempts"].values()),
            "Capture and review each dispatched attempt before closing the round")
    record.update(closed=True, lessons=args.lessons, closed_at=time())
    write_json(path, record)
    emit({"round": args.run, "submissions": len(record["attempts"]), "lessons": args.lessons,
                  "passes": sum(a.get("quality") == "pass" for a in record["attempts"].values())})


def status(args):
    path = path_for(args.project, args.run)
    record = load(path)
    active = edition.load_edition(args.project)
    current = edition.compile_edition(args.project, active)
    limit = record["round"]["limit"]
    remaining = limit - len(record["attempts"])
    corrected = {
        (parent["round"], parent["attempt"])
        for journal in journals.journal_paths(args.project, "art-")
        for other in load(journal)["attempts"].values()
        if (parent := other.get("edit_parent"))
    }
    rows = []
    resolved_slots = set()
    for ident, attempt in record["attempts"].items():
        packet = case_packet(record, attempt)
        slot = current.get(attempt["slot"])
        decision = attempt.get("quality")
        stale = not slot or attempt["director_dependency"] != edition.director_dependency(slot)
        received = (path.parent / "intake" / ident).is_file()
        if attempt["status"] == "pending":
            action = "resume-intake" if received else "reconcile-provider"
        elif attempt["status"] == "failed":
            action = "inspect-intake-failure"
        elif stale:
            action = "restage"
        elif not decision:
            action = "review-candidate"
        elif decision == "pass":
            assigned = (slot.get("image") or {}).get("sha256") == attempt["image_sha256"]
            action = "assigned" if assigned else "assign-reviewed-candidate"
            if assigned:
                resolved_slots.add(attempt["slot"])
        elif (decision == "localized" and not attempt.get("edit_parent")
              and (args.run, ident) not in corrected):
            action = "consider-one-targeted-correction"
        else:
            action = "restage"
        if args.attempt and args.attempt != ident:
            continue
        rows.append({"attempt": ident, "slot": attempt["slot"], "status": attempt["status"],
                     "quality": decision, "next_action": action, "error": attempt.get("error"),
                     "image": attempt.get("file"), "image_sha256": attempt.get("image_sha256"),
                     "checks": packet["checks"], "inputs": packet["inputs"],
                     "comparisons": packet.get("comparison_inputs", []), "target_pt": packet.get("target_pt"),
                     "observations": attempt.get("visual_review")})
    require(not args.attempt or rows, "Unknown art attempt")
    pending = any(a["status"] == "pending" for a in record["attempts"].values())
    unreviewed = any(a["status"] == "captured" and not a.get("quality") for a in record["attempts"].values())
    intake_failed = any(a["status"] == "failed" for a in record["attempts"].values())
    can_reserve = not any((record.get("closed"), pending, unreviewed, intake_failed,
                           active["revision"] != record["revision"], remaining <= 0))
    emit({"round": args.run, "journal": str(path), "provider": record["provider"],
                  "frozen_revision": record["revision"], "active_revision": active["revision"],
                  "closed": record.get("closed", False), "remaining": remaining, "can_reserve": can_reserve,
                  "unstarted_slots": [slot for slot in record["round"]["slots"]
                                      if slot not in {a["slot"] for a in record["attempts"].values()}],
                  "assigned_slots": sorted(resolved_slots), "attempts": rows})


def register(add):
    """Add this module's commands under `storybook edition` through edition.register's helper."""
    p = add("art-round", start_round)
    p.add_argument("run")
    p.add_argument("plan", type=Path)
    p = add("art-start", reserve)
    p.add_argument("run")
    p.add_argument("slot")
    p.add_argument("shot", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p = add("art-capture", capture)
    p.add_argument("run")
    p.add_argument("attempt")
    outcome = p.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--file", type=Path)
    outcome.add_argument("--resume", action="store_true")
    outcome.add_argument("--error")
    p = add("art-review", review)
    p.add_argument("run")
    p.add_argument("attempt")
    p.add_argument("observations", type=Path)
    p = add("art-status", status)
    p.add_argument("run")
    p.add_argument("--attempt")
    p = add("art-close", close)
    p.add_argument("run")
    p.add_argument("--lessons", required=True)
