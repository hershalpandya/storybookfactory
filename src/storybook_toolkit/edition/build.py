"""Edition commands that read a revision: check, review records, handoff packets and PDF builds."""

from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from .. import render
from ..image_quality import inspect_png
from ..sources import WORKSPACE_EDITION, WORKSPACE_SOURCE
from ..store import emit, load, project_file, require, serialized, sha256, write_json
from .manifest import checked_path, load_edition
from .reviews import record_review
from .slots import (art_dependency, compile_edition, director_dependency, inventory, layout, show_handoff,
                    text_dependency)


def check(args):
    edition = load_edition(args.project)
    compiled = compile_edition(args.project, edition)
    result = inventory(args.project, edition, compiled)
    result["layout"] = layout(args.project, edition)[2]
    emit(result)


@serialized
def approve(args):
    root = args.project
    edition = load_edition(root)
    require(args.revision == edition["revision"], "Edition changed since review; review the current revision")
    if args.slot == "owner-proof":
        require(args.role == "owner", "The owner records their proof decision")
        dependency = edition["revision"]
    elif args.slot == "text":
        require(args.role in ("independent-ai", "human", "owner"), "Invalid text review role")
        layout(root, edition)
        dependency = text_dependency(edition)
    elif args.slot.endswith("/profile"):
        require(args.role == "director", "A reference sheet call needs a director review")
        from ..generation import generation_packet, journal  # generation imports edition
        packet = generation_packet(root, edition, args.slot, journal(root)[1])
        dependency = packet["director_dependency"]
    else:
        require(args.role in ("visual", "director"), "Art needs a visual or director review role")
        packets = compile_edition(root, edition)
        require(args.slot in packets, "Unknown artwork slot")
        packet = packets[args.slot]
        if args.role == "visual":
            require(packet.get("image"), "A visual review needs an assigned image")
            checked_path(root, packet["image"])
        for ref in packet["references"]:
            checked_path(root, ref["image"])
        for comparison in packet["comparisons"]:
            checked_path(root, comparison)
        dependency = art_dependency(packet) if args.role == "visual" else director_dependency(packet)
    key = f"director:{args.slot}" if args.role == "director" else args.slot
    emit(record_review(root, key, dependency, args.reviewer, args.role, args.decision, args.evidence))


def reviewed_text(root, edition):
    original = load(checked_path(root, edition["source"]["review"]))
    events = []
    for event in edition["events"]:
        events.append({**event, "source_evidence": [original["passages"][i] for i in event["source_passages"]]})
    return {"revision": edition["revision"], "source": edition["source"],
            "adaptation": edition["adaptation"], "events": events,
            "pages": [{k: page[k] for k in ("id", "text", "annotations", "events")}
                      for page in edition["pages"]]}


def build(args):
    root = args.project
    revision = getattr(args, "revision", None)
    require(not (args.final and revision), "Historical revisions can be built as previews")
    edition = load_edition(root, revision)
    compiled = compile_edition(root, edition)
    report = inventory(root, edition, compiled)
    font_path, prepared, layout_report = layout(root, edition)
    if args.final:
        failures = [f"{row['slot']}: {', '.join(row['issues'])}" for row in report["slots"] if row["issues"]]
        require(not failures, "Final export blocked:\n" + "\n".join(failures))
        require(report["text_review"] and report["text_review"]["decision"] == "approved",
                "Final export needs a current text layout review")
    target = args.output
    if target is None:
        workspace = root
        if root.name == WORKSPACE_EDITION and (root.parent / WORKSPACE_SOURCE / "project.json").is_file():
            workspace = root.parent
        kind = "final" if args.final else "previews"
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S.%fZ")
        target = project_file(workspace, f"outputs/{kind}/{timestamp}-{edition['revision'][:8]}")
    require(not (target.exists() or target.is_symlink()), f"Output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=target.parent, prefix=".storybook-build-") as workspace:
        stage = Path(workspace) / "book"
        stage.mkdir()
        assets, cover_art = {}, {}
        for packet in compiled.values():
            page_id, kind = packet["slot"].split("/")
            row = next(row for row in report["slots"] if row["slot"] == packet["slot"])
            if not packet.get("image") or any(issue.startswith(("Missing", "Changed")) for issue in row["issues"]):
                path = stage / "missing-art.png"
                if not path.exists():
                    from PIL import ImageDraw
                    image = Image.new("RGB", (500, 320), "white")
                    draw = ImageDraw.Draw(image)
                    draw.rectangle((5, 5, 495, 315), outline="#a53232", width=3)
                    draw.text((24, 30), "Artwork required", fill="#a53232")
                    image.save(path)
            else:
                path = checked_path(root, packet["image"])
            if packet["role"]:
                cover_art[packet["role"]] = path
            else:
                assets[(page_id, kind)] = path
        render.render_book(stage, edition["metadata"], font_path, prepared, assets, cover_art,
                           ("reading",) if args.reading_only else tuple(args.mode or render.MODES))
        (stage / "missing-art.png").unlink(missing_ok=True)
        write_json(stage / "reviewed-text.json", reviewed_text(root, edition))
        write_json(stage / "proof-report.json", {**report, "layout": layout_report,
                                                  "build": "final" if args.final else "preview",
                                                  "physical_print": "pending", "sewn_proof": "pending"})
        stage.rename(target)
    emit({"revision": edition["revision"], "output": str(target),
          "build": "final" if args.final else "preview",
          "open_slots": sum(bool(row["issues"]) for row in report["slots"])})


def scene_handoff(args):
    """`storybook scene-handoff` on an edition directory: the compiled slot packets."""
    packets = show_handoff(args.project, args.page, args.kind)
    emit(packets[0] if args.page and args.kind else packets)


def image_checklist(args):
    """`storybook image-checklist` on an edition directory: the slot packet plus the candidate's digests."""
    packet = show_handoff(args.project, args.page, args.kind)[0]
    content = args.file.read_bytes()
    pixels = inspect_png(content, packet["reading_box_pt"][2:])
    emit({**packet, "image_sha256": sha256(content), "pixel_sha256": pixels,
          "observations_required": ["focal action", "identity and anatomy", "set and occupancy",
                                    "mechanisms and physical connections", "pose and slot legibility"]})
