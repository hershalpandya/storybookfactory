# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""The scene-plan (scenes.json, formats 1 to 3) workflow that predates editions.

scenes         scene plans, the asset registry and the scene handoff
staging        format 2/3 page contracts, set reviews and generation packets
continuity     beats, mechanisms and comparison images
visual_review  image checklists, visual reviews and the offline benchmark
attempts       journaled benchmark runs and profile attempts (journal.py holds the shared primitives)
book           layout preflight and the scene-plan PDF render

The edition package depends on this workflow only through export_for_edition.
"""

from .. import world
from ..catalog import reference, reference_record
from ..store import ProjectError, load, sha256
from . import attempts, book, scenes, staging, visual_review


def register(subparsers):
    """Add the scene-plan commands, in their historical order (check-world belongs to world.py)."""
    staging.register(subparsers)
    visual_review.register(subparsers)
    attempts.register(subparsers)
    scenes.register(subparsers)
    book.register_preflight(subparsers)
    world.register(subparsers)
    book.register(subparsers)


def export_for_edition(source):
    """Everything an edition import reads from a reviewed scene-plan project, besides the source review and
    adaptation that sources.py validates: (registry, catalogs, roots). registry maps (page, kind) to the asset
    record, catalogs holds entries by kind, and roots holds each verified root reference (in catalog order) with
    its source PNG path under "image_path"."""
    registry_path = source / "assets.json"
    registry = {(row["page"], row["kind"]): row for row in load(registry_path)["assets"]} \
        if registry_path.is_file() else {}
    entries_by_kind = {}
    roots = {}
    for kind, filename in (("characters", "character-catalog.json"), ("props", "prop-catalog.json")):
        path = source / filename
        if not path.is_file():
            entries_by_kind[kind] = {}
            continue
        entries = load(path)["entries"]
        entries_by_kind[kind] = entries
        for subject, entry in entries.items():
            for state_id, state in entry["states"].items():
                for view in state["profiles"]:
                    key = f"{kind}/{subject}/{state_id}/{view}"
                    path = reference_record(source, kind, subject, state_id, view)
                    if not path.is_file():
                        continue
                    record = load(path)
                    try:
                        reference(source, kind, subject, entry, state_id, view)
                    except (OSError, ProjectError):
                        continue
                    image = source / "root-assets" / "png" / (record["png_sha256"] + ".png")
                    if not image.is_file() or sha256(image.read_bytes()) != record["png_sha256"]:
                        continue
                    roots[key] = {"catalog": kind, "subject": subject, "state": state_id, "view": view,
                                  "image_path": image, "reviewer": record["reviewer"],
                                  "visible_features": record["evidence"]}
    return registry, entries_by_kind, roots
