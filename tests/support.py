"""Builders shared by the test modules: the CLI runner, fixture files and the two fixture projects.

Fixtures that cache these builders live in conftest.py; test modules import helpers from here, never from
each other.
"""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import struct
from types import SimpleNamespace
import zlib

from PIL import Image, ImageDraw, PngImagePlugin

from storybook_toolkit import catalog, cli


def run(*args, ok=True):
    """Run one storybook command in this process, as the console script would, and capture its output."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = cli.main([str(arg) for arg in args])
        except SystemExit as exc:  # argparse usage errors and --version
            code = exc.code if isinstance(exc.code, int) else 1
    result = SimpleNamespace(stdout=stdout.getvalue(), stderr=stderr.getvalue(), returncode=code)
    assert (result.returncode == 0) == ok, result.stderr
    return result


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def state(description, **facts):
    return {"description": description, "facts": facts,
            "profiles": {"front": "Straight from the front.", "side": "Full left profile."}}


def png(value):
    def chunk(name, payload):
        return struct.pack('>I', len(payload)) + name + payload + struct.pack('>I', zlib.crc32(name + payload))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(bytes([0, value, 0, 0]))) + chunk(b'IEND', b'')


def picture(file, offset, comment=None):
    img = Image.new("RGB", (1060, 680), "white")
    ImageDraw.Draw(img).rectangle((offset, 20, offset + 350, 400), fill="red")
    metadata = PngImagePlugin.PngInfo()
    if comment:
        metadata.add_text("Comment", comment)
    img.save(file, format="PNG", pnginfo=metadata)
    return file


def pass_checks(keys):
    return {key: {"result": "pass", "evidence": "Fixture observation for " + key} for key in keys}


def approve_set(root, page):
    packet = json.loads(run("set-preflight", root, page).stdout)
    record = {"reviewer": "Set reviewer", "contract_sha256": packet["contract_sha256"],
              "checks": pass_checks(packet["checks"])}
    run("review-set", root, page, write(root / "director.json", record))
    return packet


def observed(packet, sha, kind):
    subjects = {"pip": {"view": "side", "visible_legs": 3, "facts": {"badge": "striped at shoulder", "coat": "smooth"},
                         "evidence": "The badge is visible alongside three paws."}}
    checks = ["anatomy", "identity", "visible_action", "page_ready"]
    if kind == "illustration":
        subjects["hall"] = {"view": "front", "facts": {"door-design": "crossed doors", "floor": "straw",
                            "doors": "open", "colour-trim": "cream"},
                            "evidence": "Crossed panels stand aside, revealing straw behind the threshold."}
        checks += ["set_continuity", "threshold"]
    else:
        checks += ["simple_line_art"]
    return {"contract_sha256": packet["contract_sha256"], "image_sha256": sha, "kind": kind,
            "reviewer": "Independent reviewer", "checks": pass_checks(checks), "subjects": subjects, "extras": []}


def revise(root, path, *operations, world=None, ok=True, editor="Fixture editor",
           reason="Exercise an edition revision"):
    """Apply one revision envelope to the edition at its current revision."""
    from storybook_toolkit.edition import load_edition

    envelope = {"revision": load_edition(root)["revision"], "editor": editor, "reason": reason,
                "operations": list(operations)}
    if world is not None:
        envelope["world"] = world
    return run("edition", "revise", root, write(path, envelope), ok=ok)


def build_story(tmp_path):
    """A format-2 story with one mouse, one hall and two pages; returns (root, plan)."""
    root = tmp_path / "story"
    run("init", root)
    config = json.loads((root / "project.json").read_text())
    config["scene_format_version"] = 2
    write(root / "project.json", config)
    transcript = tmp_path / "source.txt"
    transcript.write_text("Pip enters the hall. She steps back out after brushing.", encoding="utf-8")
    run("register", root, transcript)
    draft = tmp_path / "draft.json"
    run("review", root, write(draft, {
        "format_version": 1, "reviewer": "fixture", "human_reviewed": True,
        "passages": [{"text": text, "sources": [{"transcript_id": "T0001", "location": "line 1"}],
                      "uncertainty": ""} for text in ("Pip enters the hall.", "She steps back out after brushing.")],
    }))
    source_sha = json.loads((root / "project.json").read_text())["reviewed_story"]["sha256"]
    run("approve-adaptation", root, write(draft, {
        "format_version": 1, "language": "test-xx", "source_sha256": source_sha, "human_approved": True,
        "reviewer": "fixture",
        "passages": [{"text": text, "source_passages": [i], "annotations": []}
                     for i, text in enumerate(("One", "Two"))],
    }))
    approved_sha = json.loads((root / "project.json").read_text())["adapted_story"]["sha256"]
    run("init-catalogs", root)
    actors = {
        "pip": {"name": "Pip", "species": "mouse", "legs": 4, "description": "A mouse with a striped shoulder badge.",
                 "facts": {"badge": "striped at shoulder"},
                 "states": {"unbrushed": state("Full curly fur.", coat="curly"), "brushed": state("Smooth brushed coat.", coat="smooth")}},
    }
    props = {
        "hall": {"name": "Hall", "description": "A timber hall with crossed doors.",
                 "facts": {"door-design": "crossed doors", "floor": "straw", "colour-trim": "cream"},
                 "states": {"open": state("Both doors are pinned open.", doors="open"),
                            "closed": state("The crossed double doors are shut.", doors="closed")}},
    }
    value = 0
    for kind, entries in (("characters", actors), ("props", props)):
        write(catalog.catalog_path(root, kind), {"format_version": 1, "entries": entries})
    for kind, entries in (("characters", actors), ("props", props)):
        for ident, entry in entries.items():
            for condition, definition in entry["states"].items():
                for view in definition["profiles"]:
                    value += 1
                    picture = tmp_path / "ref.png"
                    picture.write_bytes(png(value))
                    run("register-reference", root, kind, ident, condition, view, picture,
                        "--reviewer", "fixture", "--evidence", "Fixture reference checked.")
    run("check-catalogs", root)
    hall = {"state": "open", "view": "front", "position": "Upstage", "use": "Frames the threshold."}
    pages = []
    for i, action in enumerate(("Pip enters.", "Pip returns.")):
        character = {"state": "unbrushed" if i == 0 else "brushed", "view": "side", "position": "At the threshold",
                 "action": action, "visible_legs": 3, "occlusion": "Far hindleg aligns behind the near hindleg."}
        if i:
            character["state_change"] = "Pip brushes her coat between pages."
        pages.append({
            "id": f"p{i + 1}", "passages": [i], "scene": action, "colouring": f"Outline {action}",
            "set": {"location": "Summer yard", "layout": "Straw behind the threshold.",
                    "lighting": "Warm daylight", "camera": "From the yard, eye level."},
            "characters": {"pip": character}, "props": {"hall": dict(hall)},
            "checks": {"threshold": "Pip faces in the direction called for by the beat."},
            "colouring_subjects": ["pip"],
        })
    plan = {"format_version": 2, "adaptation_sha256": approved_sha, "pages": pages}
    write(root / "scenes.json", plan)
    return root, plan


def build_delivery_edition(work):
    """Two conflicting transcripts, two views, and one tracked item of ticket."""
    legacy, root = work / "delivery-source", work / "delivery-edition"
    run("init", legacy)
    for i, wording in enumerate(("ticket", "powder"), 1):
        file = work / f"delivery-{i}.txt"
        file.write_text(f"Marine picks up {wording}.\nShe flies to the rover and hands it over.\n")
        run("register", legacy, file)
    assert "powder" in run("compare", legacy).stdout
    rows = [
        ("Marine picks up ticket.", "Transcript 2 says powder; the narrator confirmed ticket."),
        ("She flies to Lumen and hands it over.", ""),
    ]
    source = {"format_version": 1, "human_reviewed": True, "reviewer": "Fixture editor",
              "passages": [{"text": text, "uncertainty": uncertainty, "sources": [
                  {"transcript_id": f"T{i:04}", "location": f"line {j}"} for i in (1, 2)]}
                  for j, (text, uncertainty) in enumerate(rows, 1)]}
    run("review", legacy, write(work / "source.json", source))
    saved = json.loads((legacy / "project.json").read_text())
    french = ["Marine prend le ticket. Elle vole vers Lumen.", "Elle donne le ticket à Lumen."]
    run("approve-adaptation", legacy, write(work / "language.json", {
        "format_version": 1, "human_approved": True, "reviewer": "Fixture editor",
        "language": "fr-CE1", "source_sha256": saved["reviewed_story"]["sha256"],
        "passages": [{"text": text, "source_passages": [i], "annotations": []} for i, text in enumerate(french)],
    }))
    run("init-catalogs", legacy)
    entity = {"name": "Marine", "description": "A bee with striped abdomen and four wings.",
              "species": "bee", "legs": 6, "facts": {"abdomen": "striped"},
              "states": {"flying": state("Flying.")}}
    catalog_file = legacy / "character-catalog.json"
    write(catalog_file, {"format_version": 1, "entries": {"marine": entity}})
    reference = work / "bee.png"
    picture(reference, 188)
    run("register-reference", legacy, "characters", "marine", "flying", "front", reference,
        "--reviewer", "Fixture reviewer", "--evidence", "Synthetic front view")
    picture(reference, 189)
    run("register-reference", legacy, "characters", "marine", "flying", "side", reference,
        "--reviewer", "Fixture reviewer", "--evidence", "Synthetic side view")
    # Exercise standard catalog transfer before the edition snapshots the source-driven project.
    prior = work / "imported-catalog"
    run("init", prior)
    run("init-catalogs", prior)
    run("import-catalog-entry", prior, legacy, "characters", "marine")
    assert "marine" in (prior / "character-catalog.json").read_text()
    other = {**entity, "name": "Lumen", "species": "rover", "legs": 0}
    write(catalog_file, {"format_version": 1, "entries": {"marine": entity, "lumen": other}})
    views = {"front": "characters/marine/flying/front", "side": "characters/marine/flying/side"}

    def art(name, idx, view=None):
        file = f"{name}.png"
        picture(legacy / file, idx)
        return {"file": file, "reason": "Synthetic fixture candidate", "disposition": "reuse",
                "brief": {"description": name, "references": [views[view]] if view else []}}

    spec = {
        "events": [
            {"id": "pickup", "actor": "marine", "speaker": "Narrator", "action": "Pick up ticket", "source_passages": [0]},
            {"id": "fly", "actor": "marine", "speaker": "Narrator", "action": "Fly across the greenhouse", "source_passages": [0, 1]},
            {"id": "handoff", "actor": "marine", "speaker": "Narrator", "action": "Deliver ticket to Lumen", "source_passages": [1]},
        ],
        "covers": {role: {"id": role, "role": role, "art": {"illustration": art(role, 130 + i)}}
                   for i, role in enumerate(("front", "back"))},
        "pages": [
            {"id": "outbound", "text": french[0], "annotations": [], "events": ["pickup", "fly"],
             "art": {"illustration": art("south-greenhouse", 132, "front"), "colouring": art("ticket-basket", 133)}},
            {"id": "delivery", "text": french[1], "annotations": [], "events": ["handoff"],
             "art": {"illustration": art("north-greenhouse", 134, "side"), "colouring": art("rover-treads", 135)}},
        ],
        "world": {"format_version": 1, "zones": {"bench": "Greenhouse south bench", "bay": "Greenhouse north bay"},
                  "connections": [["bench", "bay"]], "initial_occupancy": {"marine": "bench", "lumen": "bay"},
                  "initial_custody": {"ticket": "bench"},
                  "scenes": [
                      {"id": "outbound", "visible_zones": [], "visibility": {},
                       "transfers": [{"item": "ticket", "from": "bench", "to": "marine", "reason": "Marine loads the ticket."}]},
                      {"id": "delivery", "visible_zones": [], "visibility": {},
                       "events": [{"character": "marine", "from": "bench", "to": "bay", "reason": "Marine arrives at Lumen."}],
                       "transfers": [{"item": "ticket", "from": "marine", "to": "lumen", "reason": "Marine delivers the load."}],
                       "required_custody": {"ticket": "lumen"}},
                  ]},
        "generation": {"model": "gemini-nano-banana-2.1", "max_submissions": 1,
                       "slots": ["outbound/illustration", "delivery/illustration"]},
    }
    meta = write(work / "delivery-metadata.json", {"title": "La livraison de Marine"})
    path = write(work / "delivery-index.json", spec)
    run("edition", "import", root, legacy, path, meta)
    return legacy, root, spec, meta


def stub_http(monkeypatch, answers):
    """Replace the Gemini adapter's network opener; each answer is a JSON payload or an exception to raise.
    Returns the list of requests the adapter made."""
    from storybook_toolkit.providers import gemini_http

    requests = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class Opener:
        def open(self, request, timeout=None):
            requests.append(request)
            answer = answers.pop(0)
            if isinstance(answer, BaseException):
                raise answer
            return Response(json.dumps(answer).encode())

    monkeypatch.setattr(gemini_http, "build_opener", lambda *handlers: Opener())
    return requests
