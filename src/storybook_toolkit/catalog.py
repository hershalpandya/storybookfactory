# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Story-local character and prop catalogs and approved root reference assets."""

from pathlib import Path
import re

from .image_quality import inspect_png, validate_png
from .sources import project
from .store import (ProjectError, atomic_writer, counts, emit, fingerprint, identifier, load, project_command,
                    project_file, prose, require, serialized, sha256, strings, write_json)


KINDS = ("characters", "props")


def catalog_path(root, kind):
    return root / ("character-catalog.json" if kind == "characters" else "prop-catalog.json")


def validate_catalog(data, kind):
    require(isinstance(data, dict) and data.get("format_version") == 1 and isinstance(data.get("entries"), dict),
            f"{kind} catalog requires format_version 1 and an entries object")
    names = set()
    for ident, entry in data["entries"].items():
        require(identifier(ident) and isinstance(entry, dict), f"Invalid {kind} entry {ident}")
        name = entry.get("name")
        require(prose(name) and prose(entry.get("description")) and strings(entry.get("facts")),
                f"{ident} requires a name, prose description and facts object")
        normalized = " ".join(name.split()).casefold()
        require(normalized not in names, f"Duplicate {kind} name {name}")
        names.add(normalized)
        if "parts" in entry:
            require(counts(entry["parts"]) and bool(entry["parts"]), f"{ident} requires counts for named parts")
            if kind == "characters":
                require(prose(entry.get("form")) and not {"species", "legs"} & entry.keys(),
                        f"{ident} requires a form when using parts and must omit species and legs")
        elif kind == "characters":
            require(prose(entry.get("species")) and type(entry.get("legs")) is int and entry["legs"] >= 0,
                    f"{ident} requires a species and the anatomical number of legs")
        states = entry.get("states")
        require(isinstance(states, dict) and bool(states), f"{ident} requires declared states")
        for state, definition in states.items():
            require(identifier(state) and isinstance(definition, dict) and prose(definition.get("description"))
                    and strings(definition.get("facts")) and strings(definition.get("profiles"))
                    and len(definition["profiles"]) >= 2,
                    f"{ident}/{state} requires state prose, facts and at least two distinct profile specifications")
    return data["entries"]


def catalogs(root):
    entries = {}
    for kind in KINDS:
        entries[kind] = validate_catalog(load(catalog_path(root, kind)), kind)
    require(not entries["characters"].keys() & entries["props"].keys(), "Character and prop IDs must be globally unique")
    return entries


def state_definition(entry, state):
    """Only edits affecting a selected state invalidate its approved references."""
    return {**{key: value for key, value in entry.items() if key != "states"}, "state": entry["states"][state]}


def reference_record(root, kind, ident, state, view):
    return root / "root-assets" / kind / ident / state / f"{view}.json"


def reference(root, kind, ident, entry, state, view):
    record_path = reference_record(root, kind, ident, state, view)
    record = load(record_path)
    require(isinstance(record, dict) and record.get("definition_sha256") == fingerprint(state_definition(entry, state))
            and prose(record.get("reviewer")) and prose(record.get("evidence")),
            f"Stale or incomplete root reference {ident}/{state}/{view}")
    sha = record.get("png_sha256")
    require(isinstance(sha, str) and re.fullmatch("[0-9a-f]{64}", sha), f"Invalid root reference hash for {ident}")
    path = root / "root-assets" / "png" / f"{sha}.png"
    content = path.read_bytes()
    require(sha256(content) == sha, f"Root reference bytes changed for {ident}/{state}/{view}")
    validate_png(content)
    return {"view": view, "file": path.relative_to(root).as_posix(), "sha256": sha}


def publish_png(directory, content):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{sha256(content)}.png"
    if target.exists():
        require(target.read_bytes() == content, f"Existing PNG has changed: {target}")
    else:
        with atomic_writer(target) as temp:
            temp.write(content)
    return target


@serialized
def init_catalogs(args):
    project(args.project)
    paths = [catalog_path(args.project, kind) for kind in KINDS]
    require(all(not path.exists() for path in paths), "Catalogs already exist")
    for path in paths:
        write_json(path, {"format_version": 1, "entries": {}})


def state_references(root, kind, ident, entry, state, production=False):
    refs = [reference(root, kind, ident, entry, state, view) for view in entry["states"][state]["profiles"]]
    require(len({ref["sha256"] for ref in refs}) == len(refs), f"{ident}/{state} root views require distinct PNGs")
    if production:
        pixels = {inspect_png((root / ref["file"]).read_bytes()) for ref in refs}
        require(len(pixels) == len(refs), f"{ident}/{state} root views require distinct decoded images")
    return refs


def check_catalogs(args):
    entries_by_kind = catalogs(args.project)
    production = project(args.project).get("scene_format_version") == 3
    if production:
        from .continuity import validate_production_catalog
        validate_production_catalog(entries_by_kind)
    for kind, entries in entries_by_kind.items():
        for ident, entry in entries.items():
            for state in entry["states"]:
                state_references(args.project, kind, ident, entry, state, production)
    print("Catalog entries and reviewed root profiles are current.")


def root_profile(project_root, kind, ident, state, view):
    entries = catalogs(project_root)[kind]
    require(ident in entries and state in entries[ident]["states"], f"Unknown root reference state {ident}/{state}")
    entry = entries[ident]
    require(view in entry["states"][state]["profiles"], f"Unknown root reference view {ident}/{state}/{view}")
    return entry


def profile_definition(root, kind, ident, state_id, view):
    entry = root_profile(root, kind, ident, state_id, view)
    definition = state_definition(entry, state_id)
    definition["view"] = view
    state = definition["state"]
    definition["state"] = {key: value for key, value in state.items() if key != "profiles"}
    definition["profile"] = state["profiles"][view]
    definition["state_id"] = state_id
    return definition


def profile_brief(args):
    emit(profile_definition(args.project, args.kind, args.id, args.state, args.view))


@serialized
def register_reference(args):
    entry = root_profile(args.project, args.kind, args.id, args.state, args.view)
    require(prose(args.reviewer) and prose(args.evidence), "Root reference requires a reviewer and visual evidence")
    content = args.file.read_bytes()
    validate_png(content)
    production = project(args.project).get("scene_format_version") == 3
    if production:
        from .continuity import validate_production_catalog
        validate_production_catalog({args.kind: {args.id: entry}})
        pixels = inspect_png(content)
    sha = sha256(content)
    for other in entry["states"][args.state]["profiles"]:
        path = reference_record(args.project, args.kind, args.id, args.state, other)
        if other != args.view and path.is_file():
            other_sha = load(path).get("png_sha256")
            require(other_sha != sha, f"Root profiles {other} and {args.view} require distinct PNGs")
            if production and isinstance(other_sha, str) and re.fullmatch("[0-9a-f]{64}", other_sha):
                previous_png = args.project / "root-assets" / "png" / f"{other_sha}.png"
                require(inspect_png(previous_png.read_bytes()) != pixels,
                        f"Root profiles {other} and {args.view} have identical decoded pixels")
    publish_png(args.project / "root-assets" / "png", content)
    record = {"definition_sha256": fingerprint(state_definition(entry, args.state)), "png_sha256": sha,
              "reviewer": args.reviewer, "evidence": args.evidence}
    if production:
        from .attempts import add_review_seconds, record_profile_review
        record["pixel_sha256"] = pixels
        add_review_seconds(args, record)
    write_json(reference_record(args.project, args.kind, args.id, args.state, args.view), record)
    if production:
        record_profile_review(args, record)


@serialized
def import_entry(args):
    source = catalogs(args.source)
    destination = catalogs(args.project)
    kind, ident = args.kind, args.id
    require(ident in source[kind], f"No prior entry {ident}")
    require(all(ident not in entries for entries in destination.values()), f"Entry already exists: {ident}")
    entry = source[kind][ident]
    destination[kind][ident] = entry
    updated = {"format_version": 1, "entries": destination[kind]}
    validate_catalog(updated, kind)
    # Validate every reference before publishing any metadata in the new story.
    records = []
    for state, definition in entry["states"].items():
        for view in definition["profiles"]:
            record = reference_record(args.source, kind, ident, state, view)
            if record.exists():
                ref = reference(args.source, kind, ident, entry, state, view)
                records.append((state, view, load(record), (args.source / ref["file"]).read_bytes()))
    for state, view, record, content in records:
        require(sha256(content) == record["png_sha256"], "Prior reference changed during import")
        publish_png(args.project / "root-assets" / "png", content)
        write_json(reference_record(args.project, kind, ident, state, view), record)
    write_json(catalog_path(args.project, kind), updated)


def register(subparsers):
    project_command(subparsers, "init-catalogs", "Start both story-local catalogs", init_catalogs)
    project_command(subparsers, "check-catalogs", "Verify all declared root profiles", check_catalogs)
    for name, help_text, handler in (
        ("profile-brief", "Show the art brief for one catalog profile", profile_brief),
        ("register-reference", "Approve and store a root profile PNG", register_reference),
    ):
        p = project_command(subparsers, name, help_text, handler)
        p.add_argument("kind", choices=KINDS)
        p.add_argument("id")
        p.add_argument("state")
        p.add_argument("view")
        if name == "register-reference":
            p.add_argument("file", type=Path)
            p.add_argument("--reviewer", required=True)
            p.add_argument("--evidence", required=True)
            p.add_argument("--review-seconds", type=float)

    p = project_command(subparsers, "import-catalog-entry", "Copy a prior entry and its approved PNGs", import_entry)
    p.add_argument("source", type=Path)
    p.add_argument("kind", choices=KINDS)
    p.add_argument("id")
