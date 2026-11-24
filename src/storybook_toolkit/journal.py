# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Attempt journals: generation-runs/<run>/run.json, its intake/, images/ and reviews/.

Every workflow that sends work to an image provider (legacy benchmarks, external art rounds, the Gemini
dispatcher) records attempts here: a pending attempt is journaled before the call, the provider output is
saved to intake/ before any screening, and capture moves the attempt to captured or failed exactly once.
"""

from shutil import copyfileobj
import sys
from time import time

from .catalog import publish_png
from .image_quality import inspect_png, validate_png
from .store import ProjectError, atomic_writer, identifier, load, project_file, prose, require, sha256, write_json

RUNS = "generation-runs"


def run_path(root, run):
    require(identifier(run), "Invalid benchmark run ID")
    return project_file(root, f"generation-runs/{run}/run.json")


def target_slot(contract, kind):
    return contract.get("layout", {}).get(kind, {}).get("target_pt")


def journal_paths(root, prefix=""):
    """Every journal in the project, or only those whose run ID starts with prefix."""
    return (root / RUNS).glob(f"{prefix}*/run.json")


def find_attempt(record, ident):
    attempt = record["attempts"].get(ident)
    require(attempt is not None, "Unknown attempt")
    return attempt


def review_path(root, run, attempt):
    return run_path(root, run).parent / "reviews" / f"{attempt}.json"


def pause(path, record, reason, slot, attempt=None):
    """Stop dispatch for an owner decision; the pause is saved before the error is raised."""
    record["paused"] = {"reason": reason, "slot": slot, "attempt": attempt, "at": time()}
    write_json(path, record)
    raise ProjectError(f"Gemini paused for {slot}: {reason}. Journal: {path}")


def prior_art(root, path, attempt_id, pixels):
    known = {}
    for other in journal_paths(root):
        for ident, attempt in load(other)["attempts"].items():
            if (other != path or ident != attempt_id) and attempt["status"] == "captured":
                known[attempt["image_sha256"]] = attempt["pixel_sha256"]
    for record in (root / "root-assets").glob("*/*/*/*.json"):
        data = load(record)
        if data.get("pixel_sha256"):
            known[data["png_sha256"]] = data["pixel_sha256"]
    registry = root / "assets.json"
    if registry.is_file():
        for item in load(registry)["assets"]:
            if item.get("pixel_sha256"):
                known[item["sha256"]] = item["pixel_sha256"]
    if pixels in known.values():
        return True
    for directory in ("candidates", "assets", "root-assets/png"):
        for file in (root / directory).glob("*.png"):
            if file.stem in known:
                continue
            try:
                if inspect_png(file.read_bytes(), check_resolution=False) == pixels:
                    return True
            except ProjectError:
                continue
    return False


def capture(root, run, ident, *, resume=False, error=None, file=None, stdin=False):
    """Move a pending attempt to captured or failed; the intake copy is saved before any screening."""
    path = run_path(root, run)
    record = load(path)
    attempt = find_attempt(record, ident)
    if attempt["status"] != "pending":
        return {"attempt": ident, **attempt}
    incoming = path.parent / "intake" / ident
    if error is not None:
        require(not incoming.exists(), "A provider output was already saved. Use --resume.")
        require(prose(error), "Failure reason cannot be empty")
        attempt.update(status="failed", error=error)
    else:
        if not resume:
            require(not incoming.exists(), "Output was already saved. Use --resume to continue.")
            incoming.parent.mkdir(parents=True, exist_ok=True)
            with atomic_writer(incoming) as output:
                if stdin:
                    copyfileobj(sys.stdin.buffer, output)
                else:
                    with file.open("rb") as source:
                        copyfileobj(source, output)
        require(incoming.is_file(), "No saved provider response for this attempt")
        attempt["received_file"] = incoming.relative_to(root).as_posix()
        if incoming.stat().st_size <= 50 * 1024 * 1024:
            attempt["received_sha256"] = sha256(incoming.read_bytes())
        try:
            require(incoming.stat().st_size <= 50 * 1024 * 1024, "Provider output exceeds the PNG intake limit")
            content = incoming.read_bytes()
            validate_png(content)
            case = record["cases"][attempt["case"]]
            target = target_slot(case.get("contract", {}), case["packet"]["kind"])
            pixels = inspect_png(content, target)
            require(not prior_art(root, path, ident, pixels), "Output duplicates previously captured or registered artwork")
        except ProjectError as exc:
            attempt.update(status="failed", error=str(exc))
        else:
            # The intake copy persists before screening, and survives an interrupted finalization.
            output = publish_png(path.parent / "images", content)
            attempt.update(status="captured", file=output.relative_to(root).as_posix(),
                           image_sha256=sha256(content), pixel_sha256=pixels)
    attempt["finished_at"] = time()
    write_json(path, record)
    return {"attempt": ident, **attempt}


def find_capture(root, key, sha, matches):
    for path in journal_paths(root):
        run = load(path)
        case = run["cases"].get(key)
        if case is None or not matches(case):
            continue
        for ident, attempt in run["attempts"].items():
            if attempt["case"] == key and attempt["status"] == "captured" and attempt["image_sha256"] == sha:
                require(sha256((root / attempt["file"]).read_bytes()) == sha, "Captured attempt bytes changed")
                return path.parent.name, ident
    return None
