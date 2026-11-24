# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Legacy benchmark runs: freeze cases, start attempts, capture results through journal.py and score them."""

import json
import math
from pathlib import Path
from time import time
from uuid import uuid4

from ..catalog import KINDS, profile_definition
# Journal primitives live in journal.py; these names stay importable from attempts.
from ..journal import capture, find_attempt, find_capture, prior_art, review_path, run_path  # noqa: F401
from .scenes import validated_plan
from ..sources import project
from .staging import generation_packet, page_contract
from ..store import (emit, fingerprint, identifier, load, project_command, prose, require, serialized, sha256,
                    write_json)
from .visual_review import evaluate


@serialized
def start_run(args):
    root = args.project
    path = run_path(root, args.run)
    require(not path.exists(), "Benchmark run already exists")
    specification = load(args.specification)
    require(isinstance(specification, dict) and prose(specification.get("label"))
            and isinstance(specification.get("cases"), list) and specification["cases"],
            "A benchmark needs a label and a fixed list of cases")
    plan = None
    cases = {}
    for slot in specification["cases"]:
        require(isinstance(slot, dict), "Invalid benchmark case")
        if slot.get("kind") == "profile":
            require(project(root).get("scene_format_version") == 3, "Profile benchmarks require a format 3 project")
            profile = tuple(slot.get(field) for field in ("catalog", "id", "state", "view"))
            require(profile[0] in KINDS and all(identifier(value) for value in profile[1:]), "Invalid profile case")
            key = f"{'/'.join(profile)}/profile"
            packet = profile_packet(root, profile)
            case = {"packet": packet, "packet_sha256": fingerprint(packet), "profile": profile}
        else:
            page, kind = slot.get("page"), slot.get("kind")
            require(identifier(page) and kind in ("illustration", "colouring"), "Invalid benchmark slot")
            if plan is None:
                plan = validated_plan(root)
                require(plan["format_version"] == 3, "Frozen scene benchmarks use format 3 scenes")
            key = f"{page}/{kind}"
            contract = page_contract(root, page, plan)
            packet = generation_packet(root, contract, kind)
            case = {"packet": packet, "packet_sha256": fingerprint(packet), "contract": contract}
        require(key not in cases, f"Duplicate benchmark case {key}")
        cases[key] = case
    write_json(path, {"format_version": 1, "label": specification["label"], "cases": cases, "attempts": {}})
    emit({"run": args.run, "cases": list(cases)})


def profile_packet(root, profile):
    definition = profile_definition(root, *profile)
    return {"kind": "profile", "references": [], "prompt": (
        "Create an isolated storybook reference PNG for this entity, condition and viewpoint. "
        "Use a plain white or transparent background. Preserve the declared parts and identity.\n"
        + json.dumps(definition, ensure_ascii=False, sort_keys=True, indent=2)
    )}


@serialized
def start_attempt(args):
    root = args.project
    path = run_path(root, args.run)
    record = load(path)
    key = f"{args.page}/{args.kind}"
    require(key in record["cases"], f"{key} was not frozen in this run")
    case = record["cases"][key]
    contract = None
    if "profile" in case:
        packet = profile_packet(root, case["profile"])
    else:
        contract = page_contract(root, args.page)
        packet = generation_packet(root, contract, args.kind)
    if fingerprint(packet) != case["packet_sha256"]:
        # Existing frozen runs used one attachment per subject, even for shared PNGs.
        require(contract is not None and fingerprint(generation_packet(
            root, contract, args.kind, legacy_references=True
        )) == case["packet_sha256"], "Current prompt or references differ from the frozen case")
    settings = load(args.settings)
    require(isinstance(settings, dict) and prose(settings.get("provider")) and prose(settings.get("model")),
            "Settings need named provider and model")
    limit = settings.get("max_image_inputs")
    require("max_image_inputs" not in settings or (type(limit) is int and limit >= 0),
            "max_image_inputs must be a nonnegative integer")
    require(not any(attempt["case"] == key and attempt["status"] == "pending"
                    for attempt in record["attempts"].values()), "Finish or resume the pending attempt for this case")
    parent = None
    edit = None
    if args.parent:
        prior = find_attempt(record, args.parent)
        require(prior["case"] == key and prior["status"] == "captured", "Edit parent needs a captured PNG for this case")
        parent = {"attempt": args.parent, "image_sha256": prior["image_sha256"], "file": prior["file"]}
        source = root / prior["file"]
        require(sha256(source.read_bytes()) == prior["image_sha256"], "Edit parent bytes changed")
        require(args.edit_prompt is not None, "An edit attempt needs a targeted edit prompt file")
        edit = args.edit_prompt.read_text(encoding="utf-8")
        require(prose(edit), "Edit instruction is empty")
    else:
        require(args.edit_prompt is None, "An edit prompt requires a parent attempt")
    input_images = [ref["file"] for ref in packet["references"]]
    prompt = packet["prompt"]
    if parent:
        input_images.insert(0, parent["file"])
        supporting_prompt = generation_packet(root, contract, args.kind, reference_offset=1)["prompt"] if contract else prompt
        prompt = f"Edit image 1 according to this instruction:\n{edit}\n\n{supporting_prompt}"
    require(limit is None or len(input_images) <= limit,
            f"Provider limit is {limit} image inputs, but this attempt needs {len(input_images)} "
            "(including the edit target, if any)")
    attempt_id = uuid4().hex
    attempt = {"case": key, "status": "pending", "settings": settings,
               "packet_sha256": case["packet_sha256"], "prompt": packet["prompt"], "references": packet["references"],
               "provider_payload": {"prompt": prompt, "input_images": input_images}, "started_at": time()}
    if parent:
        attempt.update(parent=parent, edit_instruction=edit)
    record["attempts"][attempt_id] = attempt
    write_json(path, record)
    emit({"attempt": attempt_id, **attempt})


@serialized
def finish_attempt(args):
    emit(capture_attempt(args))


def capture_attempt(args):
    return capture(args.project, args.run, args.attempt, resume=args.resume, error=args.error,
                   file=getattr(args, "file", None), stdin=getattr(args, "stdin", False))


def captured_attempt(root, contract, kind, sha):
    key = f"{contract['page']}/{kind}"
    current = fingerprint(contract)
    return find_capture(root, key, sha, lambda case: fingerprint(case["contract"]) == current)


def record_profile_review(args, review):
    profile = [args.kind, args.id, args.state, args.view]
    current = fingerprint(profile_packet(args.project, profile))
    key = f"{'/'.join(profile)}/profile"
    capture = find_capture(args.project, key, review["png_sha256"], lambda case: case["packet_sha256"] == current)
    if capture:
        path = attempt_review_path(args.project, *capture)
        if not path.exists():
            snapshot = {"profile_review": review, "reviewed_at": time()}
            add_review_seconds(args, snapshot)
            write_json(path, snapshot)


def attempt_review_path(root, run, attempt):
    return review_path(root, run, attempt)


def add_review_seconds(args, record):
    seconds = getattr(args, "review_seconds", None)
    if seconds is not None:
        require(math.isfinite(seconds) and seconds >= 0, "Review time must be a finite nonnegative number")
        record["review_seconds"] = seconds


@serialized
def reject_profile(args):
    path = run_path(args.project, args.run)
    attempt = find_attempt(load(path), args.attempt)
    require(attempt["case"].endswith("/profile") and attempt["status"] == "captured",
            "Only a captured reference profile can be rejected here")
    review = attempt_review_path(args.project, args.run, args.attempt)
    require(not review.exists() and prose(args.evidence), "Provide evidence for an unreviewed profile")
    snapshot = {"rejection": args.evidence, "reviewed_at": time()}
    add_review_seconds(args, snapshot)
    write_json(review, snapshot)


def report(args):
    root = args.project
    path = run_path(root, args.run)
    record = load(path)
    results = {}
    measured_reviews = []
    for key, case in record["cases"].items():
        contract, packet = case.get("contract"), case["packet"]
        kind = packet["kind"]
        outcomes = []
        for ident, attempt in record["attempts"].items():
            if attempt["case"] != key:
                continue
            failures = [attempt.get("error", attempt["status"])]
            if attempt["status"] == "captured":
                sha = attempt["image_sha256"]
                require(sha256((root / attempt["file"]).read_bytes()) == sha, "Captured benchmark artwork changed")
                review_path = attempt_review_path(root, args.run, ident)
                failures = ["review pending"]
                if review_path.exists():
                    review = load(review_path)
                    if "review_seconds" in review:
                        measured_reviews.append(review["review_seconds"])
                    if kind == "profile":
                        failures = [review["rejection"]] if "rejection" in review else []
                    else:
                        failures = evaluate(contract, kind, sha, review, review.get("comparison_images", []))
            duration = (round(attempt["finished_at"] - attempt["started_at"], 3)
                        if "finished_at" in attempt else None)
            outcomes.append({"attempt": ident, "elapsed_seconds": duration, "failures": failures})
        first = next((number for number, attempt in enumerate(outcomes, 1) if not attempt["failures"]), None)
        results[key] = {"attempts": outcomes, "first_pass_attempt": first}
    first_pass = sum(case["first_pass_attempt"] == 1 for case in results.values())
    emit({"run": args.run, "cases": results, "total_attempts": len(record["attempts"]), "first_pass_cases": first_pass,
          "passed_cases": sum(case["first_pass_attempt"] is not None for case in results.values()),
          "timed_reviews": len(measured_reviews), "measured_review_seconds": round(sum(measured_reviews), 3)})
    if args.min_first_pass is not None:
        require(0 <= args.min_first_pass <= 1, "Minimum first-pass rate must be between 0 and 1")
        require(first_pass / len(results) >= args.min_first_pass, "First-pass benchmark threshold missed")


def register(subparsers):
    p = project_command(subparsers, "benchmark-start", "Freeze production benchmark cases and generation packets", start_run)
    p.add_argument("run")
    p.add_argument("specification", type=Path)
    p = project_command(subparsers, "attempt-start", "Journal a generation call before sending it", start_attempt)
    p.add_argument("run")
    p.add_argument("page", help="Page ID or catalog/entity/state/view for a profile")
    p.add_argument("kind", choices=("illustration", "colouring", "profile"))
    p.add_argument("settings", type=Path)
    p.add_argument("--parent")
    p.add_argument("--edit-prompt", type=Path)
    p = project_command(subparsers, "attempt-finish", "Capture the provider PNG or failure before review", finish_attempt)
    p.add_argument("run")
    p.add_argument("attempt")
    result = p.add_mutually_exclusive_group(required=True)
    result.add_argument("--file", type=Path)
    result.add_argument("--stdin", action="store_true")
    result.add_argument("--resume", action="store_true")
    result.add_argument("--error")
    p = project_command(subparsers, "profile-reject", "Record visual rejection of a captured profile", reject_profile)
    p.add_argument("run")
    p.add_argument("attempt")
    p.add_argument("--evidence", required=True)
    p.add_argument("--review-seconds", type=float)
    p = project_command(subparsers, "benchmark-report", "Score a journaled benchmark", report)
    p.add_argument("run")
    p.add_argument("--min-first-pass", type=float)
