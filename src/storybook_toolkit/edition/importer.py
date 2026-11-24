"""Import a reviewed scene-plan project into a new edition."""

from copy import deepcopy

from .. import render
from ..legacy import export_for_edition
from ..sources import project
from ..store import emit, fingerprint, load, prose, require, serialized, sha256
from .manifest import MANIFEST, blob, checked_path, load_edition, local, picture
from .slots import compile_edition, inventory, publish


def import_roots(root, roots, settings):
    """Store the verified source root references in the edition's content store."""
    stored = {}
    for key, ref in roots.items():
        stored[key] = {"catalog": ref["catalog"], "subject": ref["subject"], "state": ref["state"], "view": ref["view"],
                       "image": picture(root, ref["image_path"]), "reviewer": ref["reviewer"],
                       "visible_features": ref["visible_features"],
                       "permitted_uses": ["illustration", "colouring"], **settings.get(key, {})}
    return stored


def initialise(args):
    out, source = args.project, args.source
    require(source.resolve() != out.resolve(), "Choose a separate edition directory")
    config = project(source)
    require(config.get("reviewed_story") and config.get("adapted_story"), "Import a reviewed source and adaptation first")
    reviewed = checked_path(source, config["reviewed_story"])
    approved = checked_path(source, config["adapted_story"])
    spec = load(args.specification)
    metadata = render.book_metadata(args.metadata)
    imported_adaptation = checked_path(source, {"file": spec["adaptation"], "sha256": spec["adaptation_sha256"]}) \
        if spec.get("adaptation") else approved
    adaptation = load(imported_adaptation)
    require(adaptation["source_sha256"] == config["reviewed_story"]["sha256"], "Adaptation refers to a different source review")
    source_review = load(reviewed)
    require(source_review.get("human_reviewed") is True and prose(source_review.get("reviewer")),
            "Import requires a named human source review")
    require(prose(adaptation.get("reviewer")) and type(adaptation.get("human_approved")) is bool,
            "Record the language reviewer and approval status")
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Validation above reads only the source project; writing the edition takes the edition's lock.
    serialized(lambda locked: write_import(locked.project, args.font, source, reviewed, imported_adaptation, config,
                                           source_review, adaptation, spec, metadata))(args)


def write_import(root, font, source, reviewed, adapted, config, source_review, adaptation, spec, metadata):
    """Publish the first revision (or confirm the same import) in an edition directory."""
    registry, catalogs, verified = export_for_edition(source)
    roots = import_roots(root, verified, spec.get("roots", {}))
    missing = []

    def make_page(record):
        record = deepcopy(record)
        for kind, item in record["art"].items():
            file = item.pop("file", None)
            registered = registry.get((item.pop("registered_page", record["id"]), kind))
            if file is None and registered is not None:
                file = registered["file"]
            image = local(source, file) if file else None
            if image and image.is_file():
                item["image"] = picture(root, image)
                if registered and file == registered["file"]:
                    require(registered["sha256"] == item["image"]["sha256"], f"Registry digest changed: {file}")
                item["imported_from"] = file
            elif file:
                missing.append({"slot": f"{record['id']}/{kind}", "file": file})
        return record

    settings = {"font_sha256": sha256((font or render.FONT).read_bytes()),
                "page_size": "A4 landscape", "typography": "marelle-shaped-v1"}
    if font:
        settings["font"] = blob(root, font)
    draft = {
        "format_version": 1, "parent": None,
        "source": {"review": blob(root, reviewed), "reviewer": source_review["reviewer"],
                   "human_reviewed": source_review["human_reviewed"],
                   "transcripts": [{**entry, **blob(root, checked_path(source, entry))} for entry in config["transcripts"]]},
        "adaptation": {"artifact": blob(root, adapted), "language": adaptation["language"],
                       "reviewer": adaptation["reviewer"], "human_approved": adaptation["human_approved"],
                       "role": spec.get("language_reviewer_role", "human" if adaptation["human_approved"] else "independent-ai")},
        "metadata": metadata, "layout": settings, "events": spec["events"],
        "catalogs": catalogs, "roots": roots, "world": spec.get("world"), "generation": spec.get("generation"), "missing_roots": spec.get("missing_roots", {}),
        "covers": {key: make_page(value) for key, value in spec["covers"].items()},
        "pages": [make_page(value) for value in spec["pages"]],
        "import": {"specification_sha256": fingerprint(spec), "missing_files": missing},
    }
    candidate = fingerprint(draft)
    if (root / MANIFEST).exists():
        require((root / "revisions" / f"{candidate}.json").exists(),
                "This directory contains a different edition; use a new directory for another import")
        result = load_edition(root, candidate)
    else:
        result = publish(root, draft)
    emitted = inventory(root, result, compile_edition(root, result))
    emit({"revision": result["revision"], "missing_files": missing, "duplicate_pixels": emitted["duplicate_pixels"],
          "unavailable_roots": sorted(set(spec.get("roots", {})) - set(roots))})
