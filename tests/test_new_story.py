"""Exercise a fresh series with no series manifest or farm-specific entities."""

from copy import deepcopy
import json
from pathlib import Path

from storybook_toolkit import catalog
from support import approve_set, pass_checks, picture as fixture_picture, png, revise, run, state, write


def new_story(root, work, *, counted_parts):
    english = [
        "Marine the bee hovers beside Lumen, the little tracked rover.",
        "Lumen turns the hatch latch so Marine can fly into the greenhouse.",
    ]
    french = [
        "Marine, la petite abeille, vole près du rover Lumen.",
        "Lumen tourne le loquet. Marine entre dans la serre.",
    ]
    run("init", root)
    config = json.loads((root / "project.json").read_text())
    config["scene_format_version"] = 2
    write(root / "project.json", config)
    transcript = work / "bees-and-robots.txt"
    transcript.write_text("\n".join(english), encoding="utf-8")
    run("register", root, transcript)
    draft = work / "draft.json"
    run("review", root, write(draft, {
        "format_version": 1, "human_reviewed": True, "reviewer": "Integration fixture",
        "passages": [
            {"text": text, "sources": [{"transcript_id": "T0001", "location": f"line {i}"}], "uncertainty": ""}
            for i, text in enumerate(english, 1)
        ],
    }))
    project = root / "project.json"
    source_sha = json.loads(project.read_text())["reviewed_story"]["sha256"]
    run("approve-adaptation", root, write(draft, {
        "format_version": 1, "human_approved": True, "reviewer": "Integration fixture",
        "language": "fr-CE1", "source_sha256": source_sha,
        "passages": [{"text": text, "source_passages": [i], "annotations": []} for i, text in enumerate(french)],
    }))
    adaptation_sha = json.loads(project.read_text())["adapted_story"]["sha256"]
    run("init-catalogs", root)
    saf = {
        "name": "Marine", "description": "A honey bee with three dark bands across the abdomen.",
        "facts": {"abdomen": "three dark bands"}, "states": {"flying": state("Wings spread in flight.")},
    }
    lumen = {
        "name": "Lumen", "description": "A small cylindrical rover with a circular lens and tank treads.",
        "facts": {"chassis": "cylindrical"},
        "states": {"ready": state("The lens is dark.", **{"lens-display": "dark"}),
                   "lit": state("The lens shows a diagonal stripe.", **{"lens-display": "diagonal stripe"})},
    }
    hatch = {
        "name": "Greenhouse hatch", "description": "A round hatch with two hinge pins and one round latch.",
        "facts": {"frame": "round"}, "states": {"shut": state("Hatch closed.", door="closed"),
                                               "open": state("Hatch swung open.", door="open")},
    }
    if counted_parts:
        saf.update(form="bee", parts={"legs": 6, "wings": 4, "antennae": 2})
        lumen.update(form="tracked rover", parts={"treads": 2, "grippers": 2})
        hatch.update(parts={"hinge-pins": 2, "latches": 1})
    else:
        saf.update(species="bee", legs=6)
        lumen.update(species="rover", legs=0)
    catalogs = {"characters": {"marine": saf, "lumen": lumen}, "props": {"hatch": hatch}}
    for kind, entries in catalogs.items():
        write(catalog.catalog_path(root, kind), {"format_version": 1, "entries": entries})
    index = 0
    for kind, entries in catalogs.items():
        for ident, entry in entries.items():
            for condition, definition in entry["states"].items():
                for view in definition["profiles"]:
                    index += 1
                    fixture = work / "profile.png"
                    fixture.write_bytes(png(index))
                    run("register-reference", root, kind, ident, condition, view, fixture,
                        "--reviewer", "Integration fixture", "--evidence", "Synthetic profile for the CLI test.")
    run("check-catalogs", root)

    bee = {"state": "flying", "view": "side", "position": "Hovering to the left of the hatch",
           "action": "Waits for the hatch to open."}
    rover = {"state": "ready", "view": "front", "position": "Beside the hatch",
             "action": "Reaches toward the latch."}
    door = {"state": "shut", "view": "front", "position": "At the rear of the greenhouse",
            "use": "Separates Marine from the greenhouse."}
    if counted_parts:
        bee.update(visible_parts={"legs": 6, "wings": 2, "antennae": 2},
                   occluded_parts={"wings": "The near wings overlap the far pair."})
        rover.update(visible_parts={"treads": 2, "grippers": 2})
        door.update(visible_parts={"hinge-pins": 2, "latches": 1})
    else:
        bee.update(visible_legs=6)
        rover.update(visible_legs=0)

    first = {
        "id": "arrival", "passages": [0], "scene": "Marine hovers beside Lumen and the closed hatch.",
        "colouring": "A front view of Marine in flight.", "colouring_subjects": ["marine"],
        "set": {"location": "Greenhouse", "layout": "A round hatch under the glass roof.",
                "lighting": "Late sunlight through the glass.", "camera": "Eye level above the walkway."},
        "characters": {"marine": bee, "lumen": rover}, "props": {"hatch": door},
        "checks": {"way-in": "The hatch is closed behind Lumen."},
    }
    if counted_parts:
        first["colouring_placements"] = {"marine": {
            "view": "front", "position": "Centered in a full silhouette", "action": "Hovers with wings spread.",
            "visible_parts": {"legs": 6, "wings": 4, "antennae": 2},
        }}
    second = deepcopy(first)
    second.update(id="opening", passages=[1], scene="Lumen opens the hatch for Marine.",
                  colouring="Marine flies forward, ready to enter.",
                  checks={"way-in": "The open hatch leaves a clear flight path."})
    second["characters"]["marine"]["action"] = "Flies toward the opening."
    second["characters"]["lumen"].update(
        state="lit", action="Turns the latch with the right gripper.",
        state_change="Lumen's lens lights up as it turns the latch.")
    second["props"]["hatch"].update(
        state="open", use="Reveals the passage into the greenhouse.",
        state_change="Lumen turns the latch and opens the hatch.")
    plan = {"format_version": 2, "adaptation_sha256": adaptation_sha, "pages": [first, second]}
    write(root / "scenes.json", plan)
    return plan


def test_existing_schema_accepts_an_unrelated_world(tmp_path, monkeypatch):
    monkeypatch.delenv("STORYBOOK_REFERENCE_DIR", raising=False)
    root = tmp_path / "old-schema"
    new_story(root, tmp_path, counted_parts=False)
    approve_set(root, "arrival")
    packet = json.loads(run("scene-handoff", root, "--page", "arrival", "--kind", "illustration").stdout)
    assert set(packet["expected"]["subjects"]) == {"marine", "lumen", "hatch"}
    assert packet["expected"]["subjects"]["marine"]["visible_legs"] == 6
    assert packet["expected"]["subjects"]["lumen"]["visible_legs"] == 0
    assert {ref["subject"] for ref in packet["references"]} == {"marine", "lumen", "hatch"}


def observed_parts(packet, sha, kind, page):
    first = page == "arrival"
    bee = {
        "view": "front" if kind == "colouring" else "side",
        "visible_parts": {"legs": 6, "wings": 4 if kind == "colouring" else 2, "antennae": 2},
        "facts": {"abdomen": "three dark bands"},
        "evidence": "Six legs and two antennae; the wing overlap matches the view.",
    }
    subjects = {"marine": bee}
    if kind == "illustration":
        subjects.update(
            lumen={
                "view": "front", "visible_parts": {"treads": 2, "grippers": 2},
                "facts": {"chassis": "cylindrical", "lens-display": "dark" if first else "diagonal stripe"},
                "evidence": "Two treads flank the cylinder, with a gripper on each side.",
            },
            hatch={
                "view": "front", "visible_parts": {"hinge-pins": 2, "latches": 1},
                "facts": {"frame": "round", "door": "closed" if first else "open"},
                "evidence": "The round frame has a single latch and two hinge pins.",
            },
        )
    return {
        "contract_sha256": packet["contract_sha256"], "image_sha256": sha, "kind": kind,
        "reviewer": "Independent fixture", "checks": pass_checks(packet["expected"]["checks"]),
        "subjects": subjects, "extras": [],
    }


def test_new_series_counted_parts_and_independent_colouring(tmp_path, monkeypatch):
    monkeypatch.delenv("STORYBOOK_REFERENCE_DIR", raising=False)
    root = tmp_path / "new-series"
    plan = new_story(root, tmp_path, counted_parts=True)
    plan_path = root / "scenes.json"

    invalid = deepcopy(plan)
    invalid["pages"][0]["characters"]["marine"]["visible_parts"]["wings"] = 5
    write(plan_path, invalid)
    assert "wings" in run("set-preflight", root, "arrival", ok=False).stderr

    invalid = deepcopy(plan)
    del invalid["pages"][0]["characters"]["marine"]["occluded_parts"]
    write(plan_path, invalid)
    assert "occlu" in run("set-preflight", root, "arrival", ok=False).stderr.lower()

    invalid = deepcopy(plan)
    invalid["pages"][0]["colouring_placements"]["marine"]["state"] = "flying"
    write(plan_path, invalid)
    assert "state" in run("set-preflight", root, "arrival", ok=False).stderr

    write(plan_path, plan)
    run_cases = []
    next_image = 100
    for page in ("arrival", "opening"):
        preflight = approve_set(root, page)
        for kind in ("illustration", "colouring"):
            packet = json.loads(run("scene-handoff", root, "--page", page, "--kind", kind).stdout)
            assert packet["contract_sha256"] == preflight["contract_sha256"]
            subjects = packet["expected"]["subjects"]
            if kind == "illustration":
                assert set(subjects) == {"marine", "lumen", "hatch"}
                assert subjects["lumen"]["visible_parts"] == {"treads": 2, "grippers": 2}
                assert subjects["hatch"]["visible_parts"] == {"hinge-pins": 2, "latches": 1}
                assert "near wings overlap" in packet["prompt"]
                assert "tracked rover" in packet["prompt"]
                assert "Visible legs: 0" not in packet["prompt"]
            else:
                assert list(subjects) == ["marine"]
                assert subjects["marine"]["view"] == "front"
                assert subjects["marine"]["visible_parts"]["wings"] == 4
                assert "near wings overlap" not in packet["prompt"]
                assert [ref["view"] for ref in packet["references"]] == ["front"]

            candidate = tmp_path / f"{page}-{kind}.png"
            candidate.write_bytes(png(next_image))
            next_image += 1
            args = (root, page, kind, candidate)
            checklist = json.loads(run("image-checklist", *args).stdout)
            assert checklist["subjects"]["marine"]["count_visible_parts"] == ["antennae", "legs", "wings"]
            observation_file = tmp_path / "observations.json"
            record = observed_parts(packet, checklist["image_sha256"], kind, page)
            attempts = []
            if page == "arrival" and kind == "illustration":
                rejected = tmp_path / "rejected.png"
                rejected.write_bytes(png(200))
                bad = deepcopy(record)
                bad["image_sha256"] = catalog.sha256(rejected.read_bytes())
                bad["subjects"]["marine"]["visible_parts"]["antennae"] = 3
                bad["subjects"]["lumen"]["visible_parts"]["treads"] = 1
                bad["subjects"]["hatch"]["visible_parts"]["latches"] = 2
                result = run("review-image", root, page, kind, rejected, write(observation_file, bad), ok=False)
                assert all(field in result.stderr for field in (
                    "marine/visible_parts/antennae", "lumen/visible_parts/treads", "hatch/visible_parts/latches",
                ))
                run("register-asset", root, page, kind, rejected, ok=False)
                attempts.append({"image_sha256": bad["image_sha256"]})
            run("review-image", *args, write(observation_file, record))
            run("register-asset", *args)
            attempts.append({"image_sha256": record["image_sha256"]})
            run_cases.append({
                "page": page, "kind": kind, "contract_sha256": packet["contract_sha256"], "attempts": attempts,
            })
    report_path = write(tmp_path / "run.json", {"label": "Unrelated-story fixture", "cases": run_cases})
    report = json.loads(run("benchmark-images", root, report_path, "--min-first-pass", "0.75").stdout)
    assert (report["first_pass_cases"], report["passed_cases"], report["total_attempts"]) == (3, 4, 5)
    run("check-assets", root)
    output = tmp_path / "book"
    run("render", root, write(tmp_path / "metadata.json", {"title": "Marine et Lumen"}), output)
    assert (output / "reading.pdf").read_bytes().startswith(b"%PDF")
    assert (output / "duplex-printer-safe.pdf").read_bytes().startswith(b"%PDF")
    assert json.loads((output / "reviewed-text.json").read_text())["adaptation"]["language"] == "fr-CE1"


def test_versioned_delivery_edition(delivery, tmp_path):
    from storybook_toolkit.edition import load_edition

    legacy, root, spec, meta = delivery
    revision = load_edition(root)["revision"]
    path = tmp_path / "delivery-index.json"
    assert json.loads(run("edition", "import", root, legacy, path, meta).stdout)["revision"] == revision
    assert load_edition(root)["source"]["human_reviewed"]
    handoff = json.loads(run("scene-handoff", root, "--page", "delivery", "--kind", "illustration").stdout)
    assert handoff["world"]["custody_after"] == {"ticket": "lumen"}
    invalid = deepcopy(spec)
    invalid["world"]["scenes"][1]["transfers"] = []
    assert "must be with lumen" in run("edition", "import", tmp_path / "incomplete", legacy,
        write(tmp_path / "broken.json", invalid), meta, ok=False).stderr
    invalid["world"]["scenes"][1]["transfers"] = spec["world"]["scenes"][1]["transfers"] * 2
    assert "current holder" in run("edition", "import", tmp_path / "twice", legacy,
        write(tmp_path / "broken.json", invalid), meta, ok=False).stderr
    operations = tmp_path / "operations.json"

    def edit(*changes, world=None):
        return json.loads(revise(root, operations, *changes, world=world).stdout)

    def review(slot, role):
        run("edition", "review", root, slot, "--revision", load_edition(root)["revision"],
            "--role", role, "--reviewer", "Fixture reviewer", "--decision", "approved",
            "--evidence", "Synthetic test review")

    for page in ("front", "back", "outbound", "delivery"):
        review(page + "/illustration", "visual")
        if page in ("outbound", "delivery"):
            review(page + "/colouring", "visual")
    review("text", "human")
    report = edit({"op": "text", "page": "delivery", "text": spec["pages"][1]["text"],
                     "annotations": [{"kind": "silent", "start": 3, "end": 4, "text": "e"}]})
    assert report["text_layout_reopened"] and report["visual_changes"] == []
    assert "layout review" in run("edition", "build", root, tmp_path / "stale", "--final", ok=False).stderr
    review("text", "independent-ai")
    result = json.loads(run("edition", "build", root, "--final").stdout)
    output = Path(result["output"])
    assert output.parent == root / "outputs" / "final"
    assert (output / "duplex-printer-safe.pdf").is_file()
    reviewed = json.loads((output / "reviewed-text.json").read_text())
    assert "powder" in reviewed["events"][0]["source_evidence"][0]["uncertainty"]
    reused = json.loads(run("edition", "gemini", root, "outbound/illustration").stdout)
    assert reused == {"result": "reused", "slot": "outbound/illustration", "calls": 0}
    replacement = tmp_path / "replacement.png"
    fixture_picture(replacement, 199)
    result = edit({"op": "root", "root": "characters/marine/flying/front", "file": replacement.name,
                     "evidence": "Replaced the front reference"})
    assert [i["slot"] for i in result["visual_changes"]] == ["outbound/illustration"]
    assert "visual approval" in run("edition", "build", root, tmp_path / "stale-art", "--final", ok=False).stderr

    def briefs(action):
        return {kind: {"description": f"{action} {kind}", "references": []}
                for kind in ("illustration", "colouring")}

    moved = deepcopy(spec["world"])
    delivery = moved["scenes"][1]
    moved["scenes"].insert(1, {"id": "crossing", "visible_zones": [], "visibility": {},
                               "events": delivery.pop("events")})
    changed = edit({"op": "split", "page": "outbound", "parts": [
        {"id": "outbound", "events": ["pickup"], "offset": 23, "briefs": briefs("Pick up"),
         "carry": ["colouring"]},
        {"id": "crossing", "events": ["fly"], "offset": 24, "briefs": briefs("Fly to Lumen")},
    ]}, {"op": "text", "page": "delivery", "text": "Elle remet le ticket à Lumen.", "annotations": [],
        "editorial_reason": "Synonymous wording for the same delivery action"}, world=moved)
    assert changed["text_layout_reopened"]
    assert {p["id"] for p in load_edition(root)["pages"]} == {"outbound", "crossing", "delivery"}

    duplicate = tmp_path / "duplicate.png"
    duplicate.write_bytes((legacy / "north-greenhouse.png").read_bytes())
    edit({"op": "assign", "page": "crossing", "kind": "illustration", "file": duplicate.name,
            "disposition": "new", "reason": "Temporary artwork"})
    failed = run("edition", "build", root, tmp_path / "temporary", "--final", ok=False)
    assert "duplicate pixels" in failed.stderr and "new artwork" in failed.stderr
    run("edition", "build", root, tmp_path / "preview", "--reading-only")
    run("edition", "build", root, tmp_path / "bound", "--mode", "duplex-bound")
    assert sorted(p.name for p in (tmp_path / "bound").glob("*.pdf")) == ["duplex-bound.pdf"]
    result = run("edition", "build", root, tmp_path / "historical", "--reading-only", "--revision", revision)
    assert json.loads(result.stdout)["revision"] == revision
    assert load_edition(root)["revision"] != revision


def test_gemini_stop_gate_uses_only_the_selected_provider(delivery, tmp_path, monkeypatch):
    import io
    from contextlib import redirect_stdout
    from types import SimpleNamespace

    import pytest
    from storybook_toolkit import edition, gemini
    from storybook_toolkit.store import ProjectError, load

    _, root, _, _ = delivery
    manifest = edition.load_edition(root)
    slot = "outbound/illustration"
    run("edition", "review", root, slot, "--revision", manifest["revision"],
        "--role", "director", "--reviewer", "Fixture director", "--decision", "approved",
        "--evidence", "Synthetic staging signoff")
    args = SimpleNamespace(project=root, slot=slot, parent=None, edit=None, dry_run=False)
    path, _ = gemini.journal(root)
    monkeypatch.setenv("GEMINI_API_KEY", "fixture_secret_never_journaled")

    class Fake:
        def __init__(self, answer, available=True):
            self.answer = answer
            self.available = available
            self.calls = []

        def present(self):
            return self.available

        def send(self, project, packet):
            journal = load(path)
            assert list(journal["attempts"].values())[-1]["status"] == "pending"
            self.calls.append(packet)
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer, "fake-image-id", {"total_tokens": 100}

    fallback_calls = []
    monkeypatch.setattr(gemini.Gemini, "send", lambda *_args: fallback_calls.append(1))
    failures = [
        (Fake(b"", available=False), "missing or inaccessible", 0),
        (Fake(gemini.ProviderStop("Gemini HTTP 401: authentication rejected")), "authentication", 1),
        (Fake(gemini.ProviderStop("Gemini HTTP 404: selected model unavailable")), "unavailable", 1),
        (Fake(gemini.ProviderStop("Ambiguous timeout", ambiguous=True)), "timeout", 1),
        (Fake(b"broken pixels"), "unusable", 1),
    ]
    for provider, reason, count in failures:
        path.unlink(missing_ok=True)
        with pytest.raises(ProjectError, match=reason):
            gemini.dispatch(args, provider)
        saved = load(path)
        assert saved["paused"]["slot"] == slot and len(saved["attempts"]) == count
        assert "fixture_secret" not in path.read_text()
        with pytest.raises(ProjectError, match="paused"):
            gemini.dispatch(args, provider)
        assert len(provider.calls) == count

    path.unlink()
    args.dry_run = True
    dry_run = io.StringIO()
    sequence = Fake(fixture_picture(tmp_path / "generated.png", 201).read_bytes())
    with redirect_stdout(dry_run):
        gemini.dispatch(args, sequence)
    packet = json.loads(dry_run.getvalue())
    assert packet["budget"]["max_submissions"] == 1 and packet["ordered_inputs"]
    assert sequence.calls == [] and not path.exists()
    args.dry_run = False
    captured = gemini.dispatch(args, sequence)
    assert captured["status"] == "captured" and captured["provider_id"] == "fake-image-id"
    gemini.dispatch(args, sequence)
    assert len(sequence.calls) == 1 and not fallback_calls
    assert "fixture_secret" not in path.read_text()

    run("edition", "gemini-quality", root, captured["attempt"], "pass",
        "--reviewer", "Fixture reviewer", "--seconds", "1", "--evidence", "Synthetic pass")
    reviewed = json.loads(run("edition", "gemini-report", root).stdout)
    assert reviewed["submissions"] == reviewed["first_submission_passes"] == reviewed["first_delivered_image_passes"] == 1
    assert reviewed["review_seconds"] == 1 and reviewed["cost_usd"] is None
    operations = {"revision": edition.load_edition(root)["revision"], "editor": "Fixture editor",
                  "reason": "Promote captured and reviewed fixture art", "operations": [
                      {"op": "assign", "page": "outbound", "kind": "illustration", "attempt": captured["attempt"],
                       "disposition": "reuse", "reason": "Synthetic result passed quality review"}]}
    run("edition", "revise", root, write(tmp_path / "promote.json", operations))
    assert edition.load_edition(root)["pages"][0]["art"]["illustration"]["image"]["sha256"] == captured["image_sha256"]



    _, root, spec, _ = delivery
    slot = "outbound/illustration"
    brief = spec["pages"][0]["art"]["illustration"]["brief"]
    brief["visual_checks"] = {"identity": "The bee keeps three dark abdominal bands.",
                              "setting": "The greenhouse bench is visible at the left."}

    def edit(*operations, ok=True):
        return revise(root, tmp_path / "external-revision.json", *operations, ok=ok,
                      reason="Exercise the reviewed external artwork workflow")

    edit({"op": "stage", "page": "outbound", "kind": "illustration", "brief": brief})
    plan = write(tmp_path / "external-plan.json", {
        "provider": "Fixture operator", "objective": "Prove continuity checks across a targeted edit",
        "slots": [slot, "delivery/illustration"], "limit": 2,
    })
    shot = write(tmp_path / "external-shot.json", {
        "prompt": "Show the ticket pickup from the bench", "inputs": [],
        "checks": {"contact": "Both gripping feet touch the ticket bundle.",
                   "scale": "The bundle spans no more than the width of the front legs."},
    })

    def command(name, *args, ok=True):
        return run("edition", name, root, *args, ok=ok)

    command("art-round", "first", plan)
    dry = json.loads(command("art-start", "first", slot, shot, "--dry-run").stdout)
    assert "attempt" not in dry and set(dry["checks"]) == {"identity", "setting", "contact", "scale"}
    first = json.loads(command("art-start", "first", slot, shot).stdout)
    first_id = first["attempt"]
    state_report = json.loads(command("art-status", "first", "--attempt", first_id).stdout)
    assert not state_report["can_reserve"]
    assert state_report["attempts"][0]["next_action"] == "reconcile-provider"
    assert state_report["unstarted_slots"] == ["delivery/illustration"]
    assert "Capture and review" in command("art-start", "first", slot, shot, ok=False).stderr

    result_path = fixture_picture(tmp_path / "external-candidate.png", 207)
    first = json.loads(command("art-capture", "first", first_id, "--file", result_path).stdout)
    state_report = json.loads(command("art-status", "first").stdout)
    assert state_report["attempts"][0]["next_action"] == "review-candidate"
    assert state_report["attempts"][0]["image_sha256"] == first["image_sha256"]
    assert state_report["attempts"][0]["comparisons"]

    observations = {"reviewer": "Fixture visual reviewer",
                    "criteria": {key: {"decision": "pass", "evidence": expected}
                                 for key, expected in dry["checks"].items()}}
    localized = deepcopy(observations)
    localized["criteria"]["contact"].update(decision="uncertain", evidence="Near foot hides the contact.")
    localized["criteria"]["scale"].update(decision="fail", evidence="Bundle too wide between the feet.")
    localized["repair"] = {"region": "Front feet and ticket bundle", "criteria": ["contact", "scale"],
                           "instruction": "Narrow the bundle and show both contact points"}
    review_path = tmp_path / "external-observations.json"
    report = json.loads(command("art-review", "first", first_id, write(review_path, localized)).stdout)
    assert report["quality"] == "localized"
    command("art-close", "first", "--lessons", "Keep identity and location checks on the next view.")

    command("art-round", "second", plan)
    retry = {"prompt": "Correct contact and scale at the front feet",
             "inputs": [{"file": first["file"], "sha256": first["image_sha256"], "role": "Edit parent"}],
             "edit_parent": {"round": "first", "attempt": first_id}}
    invalid = {**retry, "checks": {"identity": "Any number of dark bands is fine."}}
    assert "Cannot replace frozen visual check" in command(
        "art-start", "second", slot, write(shot, invalid), ok=False).stderr
    result = json.loads(command("art-start", "second", slot, write(shot, retry)).stdout)
    second_id = result["attempt"]
    assert result["checks"] == dry["checks"]
    command("art-capture", "second", second_id, "--file", fixture_picture(tmp_path / "second.png", 212))
    incorrect = deepcopy(observations)
    incorrect["criteria"].pop("identity")
    assert "every frozen criterion" in command(
        "art-review", "second", second_id, write(review_path, incorrect), ok=False).stderr
    command("art-review", "second", second_id, write(review_path, localized))
    assert "revise the brief" in command("art-start", "second", slot, shot, ok=False).stderr
    observations["reviewer"] = "Fixture adjudicator"
    command("art-review", "second", second_id, write(review_path, observations))
    command("art-close", "second", "--lessons", "Both contact points are visible in the final candidate.")
    state_report = json.loads(command("art-status", "second").stdout)
    assert state_report["attempts"][0]["next_action"] == "assign-reviewed-candidate"
    assignment = {"op": "assign", "page": "outbound", "kind": "illustration", "round": "second",
                  "attempt": second_id, "disposition": "reuse", "reason": "Fixture pixel review passed"}
    assert "Choose one artwork source" in edit({**assignment, "file": result_path.name}, ok=False).stderr
    edit(assignment)
    assert json.loads(command("art-status", "second").stdout)["assigned_slots"] == [slot]


def test_generation_policy_revision_sets_gemini_budget(delivery, tmp_path):
    from storybook_toolkit.edition import load_edition

    _, root, _, _ = delivery

    def edit(op, ok=True):
        return revise(root, tmp_path / "generation.json", op, ok=ok, editor="Fixture owner",
                      reason="Open the next Gemini round")

    policy = {"op": "generation", "model": "gemini-nano-banana-2.1", "max_submissions": 3,
              "slots": ["delivery/illustration", "delivery/colouring"]}
    edit(policy)
    assert load_edition(root)["generation"] == {k: v for k, v in policy.items() if k != "op"}
    assert "supported Gemini model" in edit({**policy, "model": "other-model"}, ok=False).stderr
    assert "Unknown generation slot" in edit({**policy, "slots": ["nowhere/illustration"]}, ok=False).stderr
    covers = load_edition(root)["covers"]
    edit({**policy, "slots": [covers["front"]["id"] + "/illustration"]})
    assert "back cover" in edit({**policy, "slots": [covers["back"]["id"] + "/illustration"]}, ok=False).stderr
    assert "lifetime ceiling" in edit({**policy, "max_submissions": 0}, ok=False).stderr


def test_legacy_comparison_pages_attach_neighbour_art(delivery, tmp_path):
    from storybook_toolkit import edition
    _, root, _, _ = delivery
    manifest = edition.load_edition(root)
    first, second = manifest["pages"][0], manifest["pages"][1]
    first["art"]["illustration"]["brief"]["comparison_pages"] = [first["id"], second["id"]]
    packet = edition.compile_edition(root, manifest)[f"{first['id']}/illustration"]
    assert [c["sha256"] for c in packet["comparisons"]] == [second["art"]["illustration"]["image"]["sha256"]]
    assert first["id"] not in packet["comparisons"][0]["role"]


def test_gemini_can_edit_the_assigned_art_of_a_slot(delivery, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from storybook_toolkit import edition, gemini
    _, root, _, _ = delivery
    manifest = edition.load_edition(root)
    slot = "outbound/illustration"
    run("edition", "review", root, slot, "--revision", manifest["revision"], "--role", "director",
        "--reviewer", "Fixture director", "--decision", "approved", "--evidence", "Synthetic signoff")
    monkeypatch.setenv("GEMINI_API_KEY", "fixture")
    sent = []

    class Fake:
        source = None
        def present(self):
            return True
        def send(self, project, packet):
            sent.append(packet)
            return fixture_picture(tmp_path / "edited.png", 203).read_bytes(), "id", {}

    args = SimpleNamespace(project=root, slot=slot, parent="assigned", edit="Recolour the horse", dry_run=False)
    captured = gemini.dispatch(args, Fake())
    current = manifest["pages"][0]["art"]["illustration"]["image"]["sha256"]
    assert sent[0]["ordered_inputs"][0]["sha256"] == current
    assert sent[0]["ordered_inputs"][0]["roles"][0].startswith("Edit parent")
    assert captured["parent"] == "assigned:" + current
    assert len(sent[0]["ordered_inputs"]) == 1
