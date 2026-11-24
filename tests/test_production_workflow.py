"""Regressions for lost attempts, mutable sets, false visual passes, and late layout errors."""

from copy import deepcopy
import json

from PIL import Image

from storybook_toolkit import catalog, render

from support import approve_set, observed, pass_checks, picture, run, state, write


def promote(root, plan, work):
    config = json.loads((root / "project.json").read_text())
    config["scene_format_version"] = 3
    write(root / "project.json", config)
    plan["format_version"] = 3
    for index, page in enumerate(plan["pages"]):
        placement = page["characters"]["pip"]
        page["colouring_placements"] = {"pip": {
            "view": "front", "position": "Centered", "action": placement["action"], "visible_legs": 4,
        }}
        page["beats"] = [f"beat-{index}"]
    ledger = {"adaptation_sha256": plan["adaptation_sha256"], "beats": {
        "beat-0": {"passage": 0, "source_passages": [0], "description": "Pip enters.",
                   "check": "Pip faces into the open doorway."},
        "beat-1": {"passage": 1, "source_passages": [1], "description": "Pip returns after brushing.",
                   "correction": "Pip leads the action.", "check": "The brushed Pip faces into the yard.", "subjects": ["pip"]},
    }}
    write(root / "beats.json", ledger)
    plan["pages"][1]["mechanisms"] = {"hoist": {
        "description": "The hall cord passes over the guide.",
        "path": ["hall.anchor-ring", "hall.guide", "hall.free-end"],
    }}
    entries = catalog.catalogs(root)
    character = entries["characters"]["pip"]
    character["state_fields"] = ["coat"]
    hall = entries["props"]["hall"]
    hall["state_fields"] = ["doors"]
    hall["anchors"] = {"anchor-ring": "Ring on the anchor", "guide": "Guide ring at the beam", "free-end": "Tail on the ground"}
    for kind, definitions in entries.items():
        write(catalog.catalog_path(root, kind), {"format_version": 1, "entries": definitions})
    # Move outdated fixture records aside, as a migration would.
    (root / "root-assets").rename(root / "archived-root-assets")
    offset = 10
    for kind, entries_by_id in entries.items():
        for ident, entry in entries_by_id.items():
            for state, definition in entry["states"].items():
                for view in definition["profiles"]:
                    offset += 5
                    file = picture(work / "profile.png", offset)
                    run("register-reference", root, kind, ident, state, view, file,
                        "--reviewer", "Fixture reviewer", "--evidence", "Distinct synthetic asset.")
    write(root / "scenes.json", plan)
    metadata = write(work / "metadata.json", {"title": "Pip et la salle"})
    return metadata


def review(root, page, kind, candidate, scratch, *, existing=False, wrong_route=False, wrong_comparison=False):
    args = (root, page, kind, candidate)
    checklist = json.loads(run("image-checklist", *args).stdout)
    record = observed(checklist, checklist["image_sha256"], kind)
    record["checks"] = pass_checks(checklist["checks"])
    if page == "p1":
        record["subjects"]["pip"]["facts"]["coat"] = "curly"
    if kind == "colouring":
        record["subjects"]["pip"].update(view="front", visible_legs=4)
    record["continuity"] = {
        item["page"]: {"sha256": item["sha256"] if not wrong_comparison else "wrong",
                       "result": "pass", "evidence": "Shared subject remains recognizable."}
        for item in checklist["comparison_images"]
    }
    if checklist["mechanisms"]:
        path = ["hall.anchor-ring", "hall.guide", "hall.free-end"]
        record["mechanisms"] = {"hoist": {"path": path[::-1] if wrong_route else path,
                                         "evidence": "The cord travels from anchor to guide to free end."}}
    return run("review-image", *args, write(scratch, record), *(["--import-existing"] if existing else []),
               ok=not (wrong_route or wrong_comparison))


def test_production_gates_and_journal(story, tmp_path):
    root, plan = story
    metadata = promote(root, plan, tmp_path)
    path = root / "scenes.json"
    assert "layout.json" in run("set-preflight", root, "p1", ok=False).stderr

    invalid = deepcopy(plan)
    invalid["pages"][0]["beats"] = []
    write(path, invalid)
    assert "ordered beats" in run("layout-preflight", root, metadata, ok=False).stderr
    invalid = deepcopy(plan)
    invalid["pages"][1]["mechanisms"]["hoist"]["path"][1] = "hall.missing-hook"
    write(path, invalid)
    assert "staged catalog anchors" in run("layout-preflight", root, metadata, ok=False).stderr

    write(path, plan)
    props_path = root / "prop-catalog.json"
    props = json.loads(props_path.read_text())
    invalid_props = deepcopy(props)
    invalid_props["entries"]["hall"]["states"]["open"]["facts"]["door-design"] = "missing"
    write(props_path, invalid_props)
    assert "permanent facts" in run("layout-preflight", root, metadata, ok=False).stderr
    write(props_path, props)
    layout = json.loads(run("layout-preflight", root, metadata).stdout)
    assert layout["pages"]["p1"]["illustration"]["target_pt"] == list(render.artwork_boxes(24)["illustration"][2:])
    for page in ("p1", "p2"):
        approve_set(root, page)
    packet = json.loads(run("scene-handoff", root, "--page", "p2", "--kind", "illustration").stdout)
    assert "hall.guide" in packet["prompt"] and "artwork slot" in packet["prompt"]
    assert "beat-beat-1" in packet["expected"]["checks"]
    assert "Pip leads the action" in packet["prompt"]

    settings = write(tmp_path / "settings.json", {"provider": "fixture", "model": "test", "seed": 5, "max_image_inputs": 2})
    specification = write(tmp_path / "cases.json", {"label": "Production regression", "cases": [
        {"page": "p1", "kind": "illustration"}, {"page": "p2", "kind": "illustration"},
    ]})
    run("benchmark-start", root, "pilot", specification)
    scratch = tmp_path / "review.json"

    def start(page, *args):
        reply = run("attempt-start", root, "pilot", page, "illustration", settings, *args)
        return json.loads(reply.stdout)["attempt"]

    def finish(ident, *args):
        return json.loads(run("attempt-finish", root, "pilot", ident, *args).stdout)

    lost = start("p1")
    run("attempt-start", root, "pilot", "p1", "illustration", settings, ok=False)
    assert finish(lost, "--error", "Provider transfer failed")["status"] == "failed"
    first = start("p1")
    blank = tmp_path / "blank.png"
    Image.new("RGBA", (1060, 680), (1, 2, 3, 0)).save(blank)
    reply = finish(first, "--file", blank)
    assert "blank" in reply["error"] and (root / reply["received_file"]).read_bytes() == blank.read_bytes()
    assert "undersized" in run("image-checklist", root, "p1", "illustration",
                              write_tiny(tmp_path / "tiny.png"), ok=False).stderr

    first = start("p1")
    intake = root / "generation-runs" / "pilot" / "intake" / first
    picture(intake, 100)
    assert finish(first, "--resume")["status"] == "captured"
    candidate1 = root / finish(first, "--resume")["file"]
    review(root, "p1", "illustration", candidate1, scratch)
    run("register-asset", root, "p1", "illustration", candidate1)

    duplicate = picture(tmp_path / "metadata-reencode.png", 100, "different bytes")
    assert "duplicate" in finish(start("p2"), "--file", duplicate)["error"]
    template = finish(start("p2"), "--file", picture(tmp_path / "page2.png", 200))
    candidate2 = root / template["file"]
    assert "mechanisms/hoist" in review(root, "p2", "illustration", candidate2, scratch, wrong_route=True).stderr
    edit = tmp_path / "edit.txt"
    edit.write_text("Connect the cord to the anchor while preserving the rest.", encoding="utf-8")
    blocked = run("attempt-start", root, "pilot", "p2", "illustration", settings,
                  "--parent", template["attempt"], "--edit-prompt", edit, ok=False)
    assert "needs 3" in blocked.stderr
    write(settings, {"provider": "fixture", "model": "test", "max_image_inputs": 3})
    repaired = finish(start("p2", "--parent", template["attempt"], "--edit-prompt", edit),
                      "--file", picture(tmp_path / "page2-edit.png", 230))
    assert repaired["parent"]["image_sha256"] == template["image_sha256"]
    assert repaired["provider_payload"]["input_images"] == [
        template["file"], *(ref["file"] for ref in repaired["references"]),
    ]
    assert "Edit image 1" in repaired["provider_payload"]["prompt"]
    assert "Reference 2 shows Pip" in repaired["provider_payload"]["prompt"]
    assert "Reference 3 shows Hall" in repaired["provider_payload"]["prompt"]
    candidate2 = root / repaired["file"]
    assert "current registered image" in review(root, "p2", "illustration", candidate2,
                                                scratch, wrong_comparison=True).stderr
    review(root, "p2", "illustration", candidate2, scratch)
    run("register-asset", root, "p2", "illustration", candidate2)
    report = json.loads(run("benchmark-report", root, "pilot").stdout)
    assert (report["total_attempts"], report["first_pass_cases"], report["passed_cases"]) == (6, 0, 2)
    assert report["cases"]["p2/illustration"]["first_pass_attempt"] == 3

    # A metadata-only edit is still a duplicate at registration, even for imported artwork.
    review(root, "p1", "colouring", duplicate, scratch, existing=True)
    assert "decoded artwork" in run("register-asset", root, "p1", "colouring", duplicate, ok=False).stderr
    for page, offset in (("p1", 300), ("p2", 350)):
        colouring = picture(tmp_path / f"{page}-outline.png", offset)
        review(root, page, "colouring", colouring, scratch, existing=True)
        run("register-asset", root, page, "colouring", colouring)
    run("render", root, metadata, tmp_path / "book")
    assert (tmp_path / "book" / "reading.pdf").exists()

    # Replacing earlier artwork invalidates a review that cited its old hash.
    replacement = picture(tmp_path / "new-p1.png", 400)
    review(root, "p1", "illustration", replacement, scratch, existing=True)
    run("register-asset", root, "p1", "illustration", replacement, "--replace")
    assert "current registered image" in run("check-assets", root, ok=False).stderr
    assert json.loads(run("benchmark-report", root, "pilot").stdout) == report


def write_tiny(file):
    Image.new("RGB", (1, 1), "black").save(file)
    return file


def test_root_profile_attempt_before_scene_plan(tmp_path):
    root = tmp_path / "profiles"
    run("init", root)
    run("init-catalogs", root)
    write(root / "character-catalog.json", {"format_version": 1, "entries": {
        "bee": {"name": "Bee", "form": "honey bee", "parts": {"wings": 4},
                "description": "A bee with a round striped abdomen.",
                "facts": {}, "states": {"flying": state("In flight.")}},
    }})
    spec = write(tmp_path / "profile-cases.json", {"label": "Root preparation", "cases": [
        {"kind": "profile", "catalog": "characters", "id": "bee", "state": "flying", "view": "front"},
    ]})
    settings = write(tmp_path / "model.json", {"provider": "fixture", "model": "test"})
    run("benchmark-start", root, "references", spec)

    def capture(offset):
        attempt = json.loads(run("attempt-start", root, "references", "characters/bee/flying/front",
                                 "profile", settings).stdout)
        assert "round striped abdomen" in attempt["prompt"]
        result = run("attempt-finish", root, "references", attempt["attempt"], "--file",
                     picture(tmp_path / "profile.png", offset))
        return json.loads(result.stdout)

    rejected = capture(10)
    run("profile-reject", root, "references", rejected["attempt"], "--evidence", "Front view was wrong.",
        "--review-seconds", "12.5")
    approved = capture(70)
    run("register-reference", root, "characters", "bee", "flying", "front", root / approved["file"],
         "--reviewer", "Fixture reviewer", "--evidence", "Front profile depicts the planned subject.", "--review-seconds", "8")
    report = json.loads(run("benchmark-report", root, "references").stdout)
    assert report["cases"]["characters/bee/flying/front/profile"]["first_pass_attempt"] == 2
    assert report["total_attempts"] == 2
    assert (report["timed_reviews"], report["measured_review_seconds"]) == (2, 20.5)


def test_continuity_finds_nonadjacent_appearance(tmp_path):
    from storybook_toolkit.continuity import comparison_images

    png = picture(tmp_path / "asset.png", 10).read_bytes()
    sha = catalog.sha256(png)
    asset = tmp_path / "assets" / f"{sha}.png"
    asset.parent.mkdir()
    asset.write_bytes(png)
    plan = {"pages": [
        {"id": "lesson", "characters": {"teacher": {}}, "props": {}},
        {"id": "yard", "characters": {}, "props": {}},
        {"id": "test", "characters": {"teacher": {}}, "props": {}},
    ]}
    contract = {"page": "test", "illustration": "The teacher returns.", "roster": {"teacher": {}}}
    assets = [{"page": "lesson", "kind": "illustration", "sha256": sha,
               "file": asset.relative_to(tmp_path).as_posix()}]
    comparisons = comparison_images(tmp_path, plan, contract, "illustration", assets)
    assert comparisons == [{"page": "lesson", "sha256": sha, "file": assets[0]["file"], "subjects": ["teacher"]}]



def test_shared_profile_uses_one_attachment_per_png(monkeypatch, tmp_path):
    from storybook_toolkit import staging

    monkeypatch.setattr(staging, "approved_set", lambda root, contract: None)
    roster = {}
    for name, number in (("a", 1), ("b", 2), ("c", 3), ("d", 3), ("e", 4), ("f", 5), ("g", 5)):
        view = "side" if name in ("d", "g") else "front"
        roster[name] = {
            "kind": "props", "name": name.upper(), "description": "A prop.", "state_description": "Ready.",
            "blocking": {"view": view, "position": "At ground level", "use": "Part of the set"},
            "profile_description": "Ground view.", "visible_facts": {},
            "references": [{"view": view, "file": f"root-assets/png/{number}.png", "sha256": str(number)}],
        }
    contract = {"page": "crowd", "illustration": "Crowded set", "set": {}, "roster": roster, "checks": {}}
    packet = staging.generation_packet(tmp_path, contract, "illustration")
    assert [ref["sha256"] for ref in packet["references"]] == list("12345")
    assert packet["references"][2]["roles"] == [{"subject": "c", "view": "front"}, {"subject": "d", "view": "side"}]
    assert "Reference 3 shows D in the side view" in packet["prompt"]
    assert "Reference 5 shows G in the side view" in packet["prompt"]
    assert len(staging.generation_packet(tmp_path, contract, "illustration", legacy_references=True)["references"]) == 7
