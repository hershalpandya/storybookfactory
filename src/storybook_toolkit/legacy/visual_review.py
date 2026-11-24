"""Compare independent visual observations with the compiled scene contract."""

from pathlib import Path
import re
from time import time

from ..catalog import publish_png
from ..journal import target_slot
from ..store import emit, fingerprint, load, project_command, prose, require, serialized, sha256, write_json
from .staging import approved_set, expected_image, image_roster, page_contract, review_evidence


def read_candidate(path, target_pt=None):
    from ..image_quality import validate_png
    content = path.read_bytes()
    validate_png(content)
    if target_pt is not None:
        from ..image_quality import inspect_png
        inspect_png(content, target_pt)
    return content


def evaluate(contract, kind, image_sha, record, comparisons=()):
    """Score structured observations and evidence, with unknowns treated as failures."""
    require(isinstance(record, dict) and record.get("contract_sha256") == fingerprint(contract)
            and record.get("image_sha256") == image_sha and record.get("kind") == kind,
            "Visual review needs the current contract hash, candidate PNG hash and image kind")
    expected = expected_image(contract, kind)
    failures = review_evidence(record, expected["checks"])
    if contract["contract_version"] >= 2:
        reviewed = record.get("continuity")
        expected_refs = {item["page"]: item["sha256"] for item in comparisons}
        require(isinstance(reviewed, dict) and reviewed.keys() == expected_refs.keys(),
                "Visual review needs continuity evidence for the current comparison images")
        for page, expected_sha in expected_refs.items():
            check = reviewed[page]
            require(isinstance(check, dict) and check.get("sha256") == expected_sha
                    and check.get("result") in ("pass", "fail", "uncertain") and prose(check.get("evidence")),
                    f"Continuity evidence for {page} must identify its current registered image")
            if check["result"] != "pass":
                failures.append(f"continuity/{page}")
        if expected.get("mechanisms"):
            paths = record.get("mechanisms")
            if not isinstance(paths, dict) or paths.keys() != expected["mechanisms"].keys():
                failures.append("mechanisms/coverage")
            if isinstance(paths, dict):
                for ident, path in expected["mechanisms"].items():
                    observation = paths.get(ident)
                    if not isinstance(observation, dict) or observation.get("path") != path or not prose(observation.get("evidence")):
                        failures.append(f"mechanisms/{ident}")
    actual = record.get("subjects")
    extras = record.get("extras")
    require(isinstance(actual, dict) and isinstance(extras, list) and all(prose(item) for item in extras),
            "Visual review needs observed subjects and an extras array")
    if extras:
        failures.append("extra-subjects")
    for ident in sorted(actual.keys() - expected["subjects"].keys()):
        failures.append(f"{ident}/unexpected")
    for ident, subject in expected["subjects"].items():
        observed = actual.get(ident)
        if not isinstance(observed, dict):
            failures.append(f"{ident}/missing")
            continue
        if not prose(observed.get("evidence")):
            failures.append(f"{ident}/evidence")
        if observed.get("view") != subject["view"]:
            failures.append(f"{ident}/view")
        if "visible_legs" in subject and (
            type(observed.get("visible_legs")) is not int or observed["visible_legs"] != subject["visible_legs"]
        ):
            failures.append(f"{ident}/visible_legs")
        if "visible_parts" in subject:
            parts = observed.get("visible_parts")
            expected_parts = subject["visible_parts"]
            if not isinstance(parts, dict) or parts.keys() != expected_parts.keys():
                failures.append(f"{ident}/visible_parts")
            if isinstance(parts, dict):
                for part, count in expected_parts.items():
                    if type(parts.get(part)) is not int or parts[part] != count:
                        failures.append(f"{ident}/visible_parts/{part}")
        facts = observed.get("facts")
        if not isinstance(facts, dict) or facts.keys() != subject["facts"].keys():
            failures.append(f"{ident}/fact-coverage")
        if isinstance(facts, dict):
            for key, value in subject["facts"].items():
                if facts.get(key) != value:
                    failures.append(f"{ident}/facts/{key}")
    return sorted(failures)


def visual_review_path(root, page, kind, image_sha):
    return root / "visual-reviews" / page / kind / f"{image_sha}.json"


def comparison_context(root, contract, kind, plan=None, assets=None):
    if contract["contract_version"] < 2:
        return []
    from .continuity import comparison_images
    from .scenes import validated_plan
    path = root / "assets.json"
    if assets is None:
        assets = load(path)["assets"] if path.exists() else []
    return comparison_images(root, plan if plan is not None else validated_plan(root), contract, kind, assets)


def approved_image(root, contract, kind, image_sha, plan=None, assets=None):
    approved_set(root, contract)
    record = load(visual_review_path(root, contract["page"], kind, image_sha))
    failures = evaluate(contract, kind, image_sha, record, comparison_context(root, contract, kind, plan, assets))
    if contract["contract_version"] >= 2:
        require(record.get("provenance") in ("journaled", "imported"), "Use reviewed intake or explicitly import existing art")
    require(not failures, "Visual review blocked on " + ", ".join(failures))


def image_checklist(args):
    contract = page_contract(args.project, args.page)
    approved_set(args.project, contract)
    expected = expected_image(contract, args.kind)
    roster = image_roster(contract, args.kind)
    subjects = {}
    for ident, item in expected["subjects"].items():
        checklist = {"name": roster[ident]["name"], "fact_keys": sorted(item["facts"]),
                     "count_visible_legs": "visible_legs" in item, "references": roster[ident]["references"]}
        if "visible_parts" in item:
            checklist["count_visible_parts"] = sorted(item["visible_parts"])
        subjects[ident] = checklist
    packet = {
        "contract_sha256": fingerprint(contract),
        "image_sha256": sha256(read_candidate(args.file, target_slot(contract, args.kind))),
        "kind": args.kind, "subjects": subjects, "checks": expected["checks"],
    }
    if contract["contract_version"] >= 2:
        packet["comparison_images"] = comparison_context(args.project, contract, args.kind)
        packet["mechanisms"] = list(expected.get("mechanisms", {}))
        packet["mechanism_anchors"] = {
            key: dict(sorted(contract["mechanisms"][key]["labels"].items()))
            for key in packet["mechanisms"]
        }
    emit(packet)


@serialized
def review_image(args):
    contract = page_contract(args.project, args.page)
    approved_set(args.project, contract)
    comparisons = comparison_context(args.project, contract, args.kind)
    content = read_candidate(args.file, target_slot(contract, args.kind))
    image_sha = sha256(content)
    record = load(args.review)
    failures = evaluate(contract, args.kind, image_sha, record, comparisons)
    if contract["contract_version"] >= 2:
        from .attempts import add_review_seconds, attempt_review_path, captured_attempt
        capture = captured_attempt(args.project, contract, args.kind, image_sha)
        require(capture is not None or getattr(args, "import_existing", False),
                "Capture new artwork with attempt-finish or explicitly review existing art with --import-existing")
        record["comparison_images"] = comparisons
        record["provenance"] = "journaled" if capture else "imported"
        record["reviewed_at"] = time()
        add_review_seconds(args, record)
        if capture:
            snapshot = attempt_review_path(args.project, *capture)
            if not snapshot.exists():
                write_json(snapshot, record)
    publish_png(args.project / "candidates", content)
    write_json(visual_review_path(args.project, args.page, args.kind, image_sha), record)
    require(not failures, "Visual review blocked on " + ", ".join(failures))


def benchmark_report(root, run):
    """Score a declared batch, including failures before a usable PNG existed."""
    require(isinstance(run, dict) and prose(run.get("label")) and isinstance(run.get("cases"), list)
            and bool(run["cases"]), "Benchmark requires a label and at least one case")
    from .scenes import validated_plan
    plan = validated_plan(root)
    require(plan["format_version"] < 3, "Use a frozen run and benchmark-report for format 3")
    results = []
    seen = set()
    for case in run["cases"]:
        require(isinstance(case, dict), "Invalid benchmark case")
        page, kind = case["page"], case["kind"]
        require(kind in ("illustration", "colouring") and (page, kind) not in seen, "Invalid or repeated benchmark case")
        seen.add((page, kind))
        contract = page_contract(root, page, plan)
        approved_set(root, contract)
        require(case.get("contract_sha256") == fingerprint(contract), f"Benchmark contract changed for {page}/{kind}")
        attempts = case.get("attempts")
        require(isinstance(attempts, list), "Benchmark case requires ordered attempts")
        outcome = []
        for number, attempt in enumerate(attempts, 1):
            require(isinstance(attempt, dict), "Invalid benchmark attempt")
            if "error" in attempt:
                require(prose(attempt["error"]) and "image_sha256" not in attempt, "Invalid failed attempt")
                failures = ["no-candidate"]
            else:
                digest = attempt.get("image_sha256")
                require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "Invalid benchmark image hash")
                content = read_candidate(root / "candidates" / f"{digest}.png")
                require(sha256(content) == digest, "Benchmark candidate bytes changed")
                path = visual_review_path(root, page, kind, digest)
                failures = evaluate(contract, kind, digest, load(path))
            outcome.append({"attempt": number, "failures": failures})
        results.append({"page": page, "kind": kind, "attempts": outcome,
                        "first_pass_attempt": next((item["attempt"] for item in outcome if not item["failures"]), None)})
    return {"label": run["label"], "cases": results,
            "total_attempts": sum(len(item["attempts"]) for item in results),
            "first_pass_cases": sum(item["first_pass_attempt"] == 1 for item in results),
            "passed_cases": sum(item["first_pass_attempt"] is not None for item in results)}


def benchmark_images(args):
    run = load(args.run)
    report = benchmark_report(args.project, run)
    emit(report)
    minimum = args.min_first_pass
    if minimum is not None:
        require(0 <= minimum <= 1, "Minimum first-pass rate must be between 0 and 1")
        require(report["first_pass_cases"] / len(report["cases"]) >= minimum, "First-pass benchmark threshold missed")


def register(subparsers):
    for name, help_text, handler in (
        ("image-checklist", "Print the visual inspection checklist for a PNG", image_checklist),
        ("review-image", "Record and score visual observations", review_image),
    ):
        p = project_command(subparsers, name, help_text, handler)
        p.add_argument("page")
        p.add_argument("kind", choices=("illustration", "colouring"))
        p.add_argument("file", type=Path)
        if name == "review-image":
            p.add_argument("review", type=Path)
            p.add_argument("--review-seconds", type=float)
            p.add_argument("--import-existing", action="store_true", help="Review existing art outside the generation journal")
    p = project_command(subparsers, "benchmark-images", "Score first-pass image fidelity and retries", benchmark_images)
    p.add_argument("run", type=Path)
    p.add_argument("--min-first-pass", type=float)
