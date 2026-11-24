"""Plan v2: text-derived checks, drift gate, colouring metrics, sheets, input budget, scorecard, next action."""

import json
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from storybook_toolkit.store import ProjectError
from support import picture as fixture_picture, revise as apply_revision, run, stub_http, write


def test_text_checks_follow_plurals_numbers_contacts_and_residents(tmp_path):
    from storybook_toolkit import textspec
    world = {"initial_occupancy": {"character-a": "interior", "character-b": "exterior"}}
    (tmp_path / "textspec.json").write_text(json.dumps({
        "words": {"salle": ["room", ["room"]], "rideaux": ["curtain", ["curtain-a", "curtain-b"]],
                  "cartes": ["card", ["card"]]},
        "plural_forms": ["rideaux"],
        "named": [["camille", "character-a"]],
        "contacts": [[r"\btouche le mur\b", "the character touches the wall"]],
        "occupied_zones": {"room": "interior"},
    }))
    lexicon = textspec.project_lexicon(tmp_path)
    text = "Camille touche le mur de la salle. Des rideaux entourent quatre cartes."
    assert textspec.required_checks(text, world) == {}
    checks = textspec.required_checks(text, world, lexicon=lexicon)
    assert "at least two" in checks["text-curtain"]
    assert "exactly 4" in checks["text-card"]
    assert "character-a" in checks["text-named-character-a"]
    assert "touches the wall" in checks["text-contact-1"]
    assert "character-a" in checks["text-room-residents"] and "character-b" not in checks["text-room-residents"]

    page = {"text": "Le jour se lève."}
    brief = {"references": ["props/room/day/front"]}
    assert set(textspec.slot_findings(page, brief, world, lexicon)) == {"text-room-residents"}
    brief["text_exemptions"] = {"text-room-residents": "The interior is outside the frame"}
    assert textspec.slot_findings(page, brief, world, lexicon) == {}


def canvas(path, colour="white", box=None, fill="red"):
    image = Image.new("RGB", (300, 200), colour)
    if box:
        ImageDraw.Draw(image).rectangle(box, fill=fill)
    image.save(path)
    return path


def test_drift_counts_only_changes_outside_the_target(tmp_path):
    from storybook_toolkit import consistency
    before = canvas(tmp_path / "a.png")
    inside = canvas(tmp_path / "b.png", box=(30, 30, 90, 90))
    outside = canvas(tmp_path / "c.png", box=(200, 120, 290, 190))
    target = [[0.05, 0.1, 0.35, 0.5]]
    within = consistency.drift(before, inside, target)
    assert within["outside_changed"] == 0 and within["inside_changed"] > 0
    assert consistency.drift(before, outside, target)["outside_changed"] > 0.05
    Image.new("RGB", (200, 200), "white").save(tmp_path / "square.png")
    with pytest.raises(ProjectError, match="aspect ratio"):
        consistency.drift(before, tmp_path / "square.png", target)
    with pytest.raises(ProjectError, match="fractions"):
        consistency.parse_region("0.5,0.1,0.2,0.9")
    result = json.loads(run("edition", "ab", tmp_path, before, outside, "--region", "0.05,0.1,0.35,0.5").stdout)
    assert result["accepted"] is False


def test_colouring_metrics_separate_outlines_from_shading(tmp_path):
    from storybook_toolkit import consistency
    line = Image.new("RGB", (1000, 750), "white")
    ImageDraw.Draw(line).ellipse((200, 150, 800, 600), outline="black", width=6)
    line.save(tmp_path / "line.png")
    shaded = line.copy()
    ImageDraw.Draw(shaded).rectangle((300, 250, 700, 500), fill=(128, 128, 128))
    shaded.save(tmp_path / "shaded.png")
    clean = consistency.colouring_metrics(tmp_path / "line.png")
    assert clean["grey_share"] < 0.005 and 4 <= clean["stroke_px"] <= 8
    assert consistency.colouring_metrics(tmp_path / "shaded.png")["grey_share"] > 0.05
    dense = line.copy()  # dense hatching (yarn, fur) is line work, not a grey fill
    for x in range(300, 700, 6):
        ImageDraw.Draw(dense).line((x, 250, x, 500), fill="black", width=2)
    dense.save(tmp_path / "dense.png")
    assert consistency.colouring_metrics(tmp_path / "dense.png")["grey_share"] < 0.02


def test_cast_and_contact_sheets(tmp_path):
    from storybook_toolkit import consistency
    a = canvas(tmp_path / "a.png", box=(100, 50, 200, 190), fill="blue")
    b = canvas(tmp_path / "b.png", box=(10, 10, 60, 100), fill="green")
    sheet = consistency.cast_sheet([(a, 1.0), (b, 0.5)], tmp_path / "cast.png", height=200, gap=10)
    with Image.open(sheet) as image:
        assert image.height == 220 and image.getpixel((5, 5)) == (255, 255, 255)
    consistency.contact_sheet([("p1", a), ("p2", None), ("p3", b)], tmp_path / "sheet.png", tile=(100, 70),
                              columns=2)
    with Image.open(tmp_path / "sheet.png") as image:
        sheet = image.convert("RGB")
    assert sheet.size == (200, 2 * (70 + 26))  # two columns of tiles, each row with a label strip
    assert sheet.getpixel((150, 35)) == (255, 255, 255)  # the missing slot stays blank inside its frame
    assert sheet.getpixel((50, 35)) != (255, 255, 255)  # the first slot holds its thumbnail


def revise(root, tmp_path, *operations):
    return json.loads(apply_revision(root, tmp_path / "op.json", *operations, reason="Exercise plan v2").stdout)


def test_v2_policy_text_checks_input_budget_layout_reference_and_drift_gate(delivery, tmp_path, monkeypatch):
    from storybook_toolkit import edition, gemini
    _, root, _, _ = delivery
    slot = "outbound/illustration"
    revise(root, tmp_path, {"op": "generation", "model": gemini.MODEL, "max_submissions": 5,
                            "slots": [slot], "max_inputs": 2, "drift_max": 0.01,
                            "strict_references": True, "checks": ["text", "colouring"],
                            "max_failures_per_slot": 2})
    manifest = edition.load_edition(root)
    assert manifest["generation"]["max_inputs"] == 2 and manifest["generation"]["checks"] == ["colouring", "text"]
    def text_issues():
        report = json.loads(run("edition", "check", root).stdout)
        return {row["slot"]: i for row in report["slots"] for i in row["issues"] if "text check" in i}

    # Vocabulary checks apply only after the project declares matching terms.
    assert text_issues() == {}
    (root / "textspec.json").write_text(json.dumps({"words": {"ticket": ["ticket", ["ticket"]]}}))
    assert text_issues() == {page + "/illustration": "text check missing: text-ticket"
                             for page in ("outbound", "delivery")}
    (root / "textspec.json").unlink()
    page = manifest["pages"][0]
    brief = dict(page["art"]["illustration"]["brief"])
    layout = canvas(tmp_path / "layout.png", box=(10, 10, 100, 100))
    brief["layout_reference"] = {"file": layout.name, "role": "Cast and placement guide"}
    revise(root, tmp_path, {"op": "stage", "page": page["id"], "kind": "illustration", "brief": brief})
    manifest = edition.load_edition(root)
    staged = manifest["pages"][0]["art"]["illustration"]["brief"]["layout_reference"]
    assert staged["sha256"] and staged["role"] == "Cast and placement guide"
    packet = gemini.generation_packet(root, manifest, slot, gemini.journal(root)[1])
    assert packet["ordered_inputs"][-1]["roles"] == ["Cast and placement guide"]
    assert "layout_reference" not in packet["prompt"]
    brief["references"] = ["characters/marine/flying/front", "characters/marine/flying/side"]
    revise(root, tmp_path, {"op": "stage", "page": page["id"], "kind": "illustration", "brief": brief})
    with pytest.raises(ProjectError, match="input budget of 2"):
        gemini.generation_packet(root, edition.load_edition(root), slot, gemini.journal(root)[1])
    brief.pop("references")
    revise(root, tmp_path, {"op": "stage", "page": page["id"], "kind": "illustration", "brief": brief})

    # An edit of assigned art must declare its region, and pixels outside it must not move.
    manifest = edition.load_edition(root)
    run("edition", "review", root, slot, "--revision", manifest["revision"], "--role", "director",
        "--reviewer", "Fixture director", "--decision", "approved", "--evidence", "Synthetic signoff")
    monkeypatch.setenv("GEMINI_API_KEY", "fixture")
    parent = edition.checked_path(root, manifest["pages"][0]["art"]["illustration"]["image"])
    edited = tmp_path / "edited.png"

    class Fake:
        source = None
        model_version = "fixture-model-001"

        def present(self):
            return True

        def send(self, project, packet):
            return edited.read_bytes(), "id", {}

    args = SimpleNamespace(project=root, slot=slot, parent="assigned", edit="Recolour the bee", dry_run=False)
    with pytest.raises(ProjectError, match="--region"):
        gemini.dispatch(args, Fake())
    with Image.open(parent) as image:
        moved = image.convert("RGB")
    ImageDraw.Draw(moved).rectangle((0, 0, moved.width, moved.height // 2), fill="black")
    moved.save(edited)
    args.region = ["0.0,0.8,0.1,1.0"]
    captured = gemini.dispatch(args, Fake())
    record = gemini.journal(root)[1]
    assert record["attempts"][captured["attempt"]]["model_version"] == "fixture-model-001"
    result = run("edition", "gemini-quality", root, captured["attempt"], "pass", "--reviewer", "Fixture",
                 "--seconds", "5", "--evidence", "Looks right", ok=False)
    assert "Drift gate" in result.stderr
    drift = gemini.journal(root)[1]["attempts"][captured["attempt"]]["drift"]
    assert drift["rejected"] and drift["outside_changed"] > 0.3
    nxt = json.loads(run("edition", "next", root).stdout)
    assert nxt["action"] == "review-capture" and nxt["attempt"] == captured["attempt"]
    run("edition", "gemini-quality", root, captured["attempt"], "unusable", "--reviewer", "Fixture",
        "--seconds", "5", "--evidence", "Drift outside the target")
    assert not gemini.journal(root)[1].get("paused")  # one failure on the slot does not escalate yet
    card = json.loads(run("edition", "scorecard", root).stdout)
    assert card["submissions"] == 1 and card["drift_rejects"] == 1
    assert card["model_versions"] == ["fixture-model-001"]


def test_profile_sheet_from_source_crops_needs_director_review(delivery, tmp_path):
    from storybook_toolkit import edition, gemini
    _, root, _, _ = delivery
    crop = fixture_picture(tmp_path / "crop.png", 210)
    revise(root, tmp_path, {"op": "missing_root", "key": "clean-marine", "definition": {
        "description": "Marine alone on white", "prompt": "Isolate the bee on plain white.",
        "aspect_ratio": "3:2", "image_size": "2K",
        "sources": [{"file": crop.name, "role": "Source crop: isolate this bee"}]}})
    revise(root, tmp_path, {"op": "generation", "model": gemini.MODEL, "max_submissions": 3,
                            "slots": ["clean-marine/profile"]})
    manifest = edition.load_edition(root)
    packet = gemini.generation_packet(root, manifest, "clean-marine/profile", gemini.journal(root)[1])
    assert packet["aspect_ratio"] == "3:2" and packet["image_size"] == "2K"
    assert packet["prompt"].startswith("Isolate the bee")
    assert packet["ordered_inputs"][0]["roles"] == ["Source crop: isolate this bee"]
    run("edition", "review", root, "clean-marine/profile", "--revision", manifest["revision"], "--role", "director",
        "--reviewer", "Fixture director", "--decision", "approved", "--evidence", "Crop shows one bee")
    assert edition.review_for(edition.active_reviews(root), "director:clean-marine/profile",
                              packet["director_dependency"])


def test_provider_choice_is_explicit_and_status_explains_next_steps(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    status = json.loads(run("provider", "status", tmp_path).stdout)
    assert status["choice"] is None and "choose" in status["next"]
    assert status["gemini_api_steps"] and status["subscription_steps"]
    assert "Name the subscription tool" in run("provider", "choose", tmp_path, "subscription", "--owner", "Owner",
                                               ok=False).stderr
    run("provider", "choose", tmp_path, "subscription", "--tool", "codex", "--owner", "Owner")
    status = json.loads(run("provider", "status", tmp_path).stdout)
    assert status["choice"]["tool"] == "codex" and "art-round" in " ".join(status["subscription_steps"])


def test_split_sheet_cuts_one_page_per_subject_and_drops_specks(tmp_path):
    from storybook_toolkit import consistency
    sheet = Image.new("RGB", (1200, 800), "white")
    draw = ImageDraw.Draw(sheet)
    for x0, y0 in ((60, 60), (460, 60), (860, 60), (160, 460), (660, 460)):
        draw.ellipse((x0, y0, x0 + 260, y0 + 260), outline="black", width=6)
        draw.ellipse((x0 + 110, y0 + 110, x0 + 140, y0 + 140), fill="black")  # an eye inside the outline
    draw.rectangle((1150, 760, 1156, 766), fill="black")  # a stray speck
    sheet.save(tmp_path / "sheet.png")
    out = tmp_path / "pages"
    out.mkdir()
    result = consistency.split_sheet(tmp_path / "sheet.png", [["a", "b", "c"], ["d", "e"]], out)
    assert sorted(result) == ["a", "b", "c", "d", "e"]
    assert result["a"]["sheet_box"][0] < result["b"]["sheet_box"][0] < result["c"]["sheet_box"][0]
    assert result["d"]["sheet_box"][1] > result["a"]["sheet_box"][1]
    with Image.open(out / "e.png") as page:
        assert page.size == (1466, 1073)
        centre = page.convert("L").crop((683, 486, 783, 586))
        assert min(centre.get_flattened_data()) < 60  # the eye inside the outline survives despeckling


def test_readback_recovers_an_interrupted_submission_and_agent_resume_is_not_an_owner_touch(tmp_path, monkeypatch):
    from io import BytesIO
    from storybook_toolkit import consistency, gemini
    path, record = gemini.journal(tmp_path)
    record["attempts"]["a1"] = {"slot": "p1/illustration", "kind": "illustration", "case": "c", "status": "pending",
                                "provider_id": "v1_abc"}
    record["paused"] = {"reason": "interrupted", "slot": "p1/illustration", "attempt": "a1", "at": 0}
    gemini.write_json(path, record)
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "JPEG")
    from base64 import b64encode

    stored = {"id": "v1_abc", "status": "completed", "model": "fixture", "usage": {"total_output_tokens": 10},
              "steps": [{"type": "model_output", "content": [{"type": "image",
                                                               "data": b64encode(buffer.getvalue()).decode()}]}]}
    requests = stub_http(monkeypatch, [stored])
    monkeypatch.setenv("GEMINI_API_KEY", "fixture")
    gemini.recover(SimpleNamespace(project=tmp_path))
    assert [request.full_url.rsplit("/", 1)[-1] for request in requests] == ["v1_abc"]
    assert (path.parent / "intake" / "a1").is_file()
    assert gemini.journal(tmp_path)[1]["attempts"]["a1"]["model_version"] == "fixture"
    gemini.resume(SimpleNamespace(project=tmp_path, owner="Agent", evidence="Read back by id", reconcile=None,
                                  resubmission=None, resubmit=None, agent=True))
    card = consistency.scorecard(gemini.journal(tmp_path)[1], [])
    assert card["agent_recoveries"] == 1 and card["owner_resumptions"] == 0
