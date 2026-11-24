# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""The edition manifest store: content-addressed blobs, pictures, pages and immutable revisions."""

from pathlib import Path

from PIL import Image

from ..store import ProjectError, atomic_writer, fingerprint, load, project_file, require, sha256

KINDS = ("illustration", "colouring")
ROLES = ("front", "back")
DISPOSITIONS = ("reuse", "edit", "new", "unresolved")
MANIFEST = "edition.json"


def local(root, name):
    return project_file(root, name)


def blob(root, path):
    data = path.read_bytes()
    digest = sha256(data)
    target = Path("content") / (digest + path.suffix.lower())
    stored = local(root, target)
    if not stored.exists():
        with atomic_writer(stored) as file:
            file.write(data)
    require(sha256(stored.read_bytes()) == digest, f"Invalid stored content: {target}")
    return {"file": target.as_posix(), "sha256": digest}


def checked_path(root, record):
    path = local(root, record["file"])
    require(path.is_file(), f"Missing file: {record['file']}")
    require(sha256(path.read_bytes()) == record["sha256"], f"Changed content: {record['file']}")
    return path


def picture(root, path):
    record = blob(root, path)
    with Image.open(root / record["file"]) as image:
        pixels = image.convert("RGBA")
        record.update(pixel_sha256=sha256(str(pixels.size).encode() + pixels.tobytes()),
                      dimensions=list(pixels.size))
    return record


def pages(edition):
    return [edition["covers"]["front"], *edition["pages"], edition["covers"]["back"]]


def page_by_id(edition, page_id):
    for page in pages(edition):
        if page["id"] == page_id:
            return page
    raise ProjectError(f"Unknown page {page_id}")


def load_edition(root, revision=None):
    require(revision is None or (len(revision) == 64 and all(c in "0123456789abcdef" for c in revision)), "Invalid revision digest")
    edition = load(root / (MANIFEST if revision is None else f"revisions/{revision}.json"))
    require(edition.get("format_version") == 1, "Unsupported edition format")
    digest = edition.pop("revision")
    require(digest == fingerprint(edition) and (revision is None or digest == revision),
            "Edition manifest digest mismatch")
    edition["revision"] = digest
    return edition
