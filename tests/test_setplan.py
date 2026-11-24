# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Set plans: one 3D plan per set, rendered locally per page camera, with derived wording, checks and scores."""

from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from storybook_toolkit import edition, gemini, setplan
from storybook_toolkit.store import ProjectError, load
from support import picture, revise, run, write

PLAN = {
    "objects": {
        "lawn": {"kind": "ground", "x": [-20, 20], "z": [0, 30], "colour": [120, 170, 80]},
        "shed": {"kind": "box", "x": -6, "z": 10, "width": 3, "depth": 3, "height": 2.5, "colour": [190, 60, 50],
                 "label": "the red shed", "fixture": True, "facts": "one small red shed on the west side"},
        "pond": {"kind": "box", "x": 0, "z": 12, "width": 4, "depth": 3, "height": 0.2, "colour": [60, 120, 200],
                 "label": "the pond", "fixture": True, "count": "exactly one pond"},
        "marker": {"kind": "group", "label": "the round marker", "fixture": True, "parts": [
            {"kind": "box", "x": 7, "z": 11, "width": 0.5, "depth": 0.5, "height": 3},
            {"kind": "sphere", "x": 7, "y": 4, "z": 11, "radius": 2, "colour": [60, 110, 50]},
        ]},
        "divider": {"kind": "polygon", "vertices": [[-10, 0, 0], [10, 0, 0], [10, 1, 0], [-10, 1, 0]],
                    "colour": [240, 240, 240], "describe": False, "visible_note": "A white divider runs along the front."},
    },
    "actors": {"pip": {"colour": [250, 250, 250], "width": 0.6, "height": 0.8, "label": "Pip",
                       "colour_name": "white"}},
    "shots": {
        "north": {"camera": {"pos": [0, 1.5, 1.5], "yaw": 0, "fov": 75}, "actors": {"pip": [2, 6]}},
        "south": {"camera": {"pos": [0, 1.5, 24], "yaw": 180, "fov": 75}, "actors": {"pip": [2, 6]}},
    },
}


def test_turning_the_camera_flips_the_derived_order(tmp_path):
    north = setplan.render(PLAN, PLAN["shots"]["north"], tmp_path / "north.png")
    south = setplan.render(PLAN, PLAN["shots"]["south"], tmp_path / "south.png")
    assert Image.open(tmp_path / "north.png").size == (setplan.W, setplan.H)
    assert {"shed", "pond", "marker", "pip"} <= set(north) and {"shed", "marker"} <= set(south)
    assert setplan.centre(north["shed"]["box"]) < setplan.centre(north["marker"]["box"])
    assert setplan.centre(south["shed"]["box"]) > setplan.centre(south["marker"]["box"])
    checks = setplan.checks(PLAN, north, PLAN["shots"]["north"]["actors"])
    assert checks["set-shed"].startswith("Present and matches the plan: one small red shed")
    assert checks["count-pond"] == "Exactly one pond."
    assert "order-shed-pond" in checks and checks["place-shed"].endswith("left third of the picture.")
    assert {"order-marker-pond", "order-pond-shed"} <= set(setplan.checks(PLAN, south, {}))
    text = setplan.describe(PLAN, north)
    assert text.startswith("Layout from this camera (left to right): the red shed in the left third")
    assert "divider" not in text
    south_text = setplan.describe(PLAN, south)
    assert south_text.endswith("A white divider runs along the front.") and "divider in the" not in south_text


def test_set_layout_checks_omit_fully_occluded_elements(tmp_path):
    screen = {"kind": "box", "x": 0, "z": 4, "width": 2, "depth": 1, "height": 2,
              "colour": [100, 100, 100]}
    marker = {"kind": "sphere", "x": 0, "y": 1, "z": 8, "radius": 0.4,
              "facts": "a round marker", "colour": [0, 100, 100]}
    plan = {"objects": {"screen": screen, "hidden-marker": marker,
                        "visible-marker": {**marker, "x": 2.8}},
            "shots": {"page": {"camera": {"pos": [0, 1, 0], "yaw": 0, "pitch": 0}}}}
    spec = tmp_path / "plan.json"
    spec.write_text(json.dumps(plan), encoding="utf-8")
    out = tmp_path / "layout"
    result = json.loads(run("edition", "set-layout", tmp_path, spec, "page", out).stdout)

    assert "hidden-marker" not in result["visible"]
    assert "set-hidden-marker" not in result["checks"]
    assert "hidden-marker" not in result["text"]
    assert "visible-marker" in result["visible"]
    assert "set-visible-marker" in result["checks"]


def test_plan_validation_and_unknown_actor(tmp_path):
    with pytest.raises(ProjectError, match="kind"):
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"objects": {"x": {"kind": "cloud"}}}))
        setplan.load_plan(bad)
    with pytest.raises(ProjectError, match="Unknown actor"):
        setplan.render(PLAN, {"camera": PLAN["shots"]["north"]["camera"], "actors": {"ghost": [0, 5]}},
                       tmp_path / "x.png")


def test_set_layout_command_composes_a_sheet_and_scores(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "sets").mkdir()
    (project / "sets" / "garden.json").write_text(json.dumps(PLAN))
    cast = tmp_path / "cast.png"
    Image.new("RGB", (300, 200), "white").save(cast)
    out = tmp_path / "north"
    result = json.loads(run("edition", "set-layout", project, "sets/garden.json", "north", out,
                            "--top", cast, "--top-role", "Top: the cast sheet.").stdout)
    assert (out / "layout.png").is_file() and (out / "sheet.png").is_file() and (out / "derived.json").is_file()
    assert result["role"].startswith("Top: the cast sheet. Bottom: a flat-colour 3D layout")
    assert "Pip = white" in result["role"]
    assert Image.open(out / "sheet.png").height > Image.open(out / "layout.png").height
    assert "already exists" in run("edition", "set-layout", project, "sets/garden.json", "north", out, ok=False).stderr
    assert "no shot" in run("edition", "set-layout", project, "sets/garden.json", "east", tmp_path / "e",
                            ok=False).stderr
    answers = {"img-A": {"a": {"answer": "yes"}, "b": {"answer": "no"}},
               "img-B": {"a": {"answer": "yes"}, "b": {"answer": "yes"}}}
    key = {"img-A": {"page": "north", "arm": "plain"}, "img-B": {"page": "north", "arm": "layout"}}
    (tmp_path / "answers.json").write_text(json.dumps(answers))
    (tmp_path / "key.json").write_text(json.dumps(key))
    report = json.loads(run("edition", "set-score", project, tmp_path / "answers.json", "--key",
                            tmp_path / "key.json").stdout)
    assert report["images"]["img-A"]["rate"] == 0.5 and report["arms"]["layout"]["rate"] == 1.0


@pytest.fixture
def recurring_edition(delivery):
    source, root, spec, _ = delivery
    operations = []
    for page in spec["pages"]:
        brief = page["art"]["illustration"]["brief"]
        del brief["standalone_reason"]
        brief.update(setting="garden", visual_checks={"action": "The ticket is held by its handle."})
        if page["id"] == "outbound":
            brief["comparison_references"] = [{"page": "delivery", "role": "Match the brushwork."}]
        operations.append({"op": "stage", "kind": "illustration", "page": page["id"], "brief": brief})
    revise(root, source / "recurring.json", *operations,
           {"op": "unassign", "kind": "illustration", "page": "outbound", "reason": "Generate a fresh scene"})
    plan = deepcopy(PLAN)
    plan["shots"] = {"outbound": plan["shots"]["north"], "delivery": plan["shots"]["south"]}
    (root / "set-plans").mkdir()
    plan_path = write(root / "set-plans" / "garden.json", plan)
    return root, plan_path


def test_fresh_gemini_scene_requires_the_current_rendered_layout(recurring_edition, tmp_path, capsys):
    root, plan = recurring_edition
    slot = "outbound/illustration"
    args = SimpleNamespace(project=root, slot=slot, parent=None, edit=None, dry_run=False)

    class Provider:
        def __init__(self):
            self.calls = []

        def present(self):
            return True

        def send(self, project, packet):
            self.calls.append(packet)
            return picture(tmp_path / "candidate.png", 209).read_bytes(), "fixture-image", {}

    provider = Provider()
    with pytest.raises(ProjectError, match="missing rendered layout.*--stage"):
        gemini.dispatch(args, provider)
    assert not gemini.journal(root)[0].exists()
    info = json.loads(run("edition", "next", root).stdout)
    assert info["action"] == "prepare-layout" and "set-plans/garden.json" in info["detail"]

    def stage(output):
        return json.loads(run("edition", "set-layout", root, "set-plans/garden.json", "outbound",
                              root / output, "--stage").stdout)

    stage("first-layout")
    handoff = json.loads(run("scene-handoff", root, "--page", "outbound", "--kind", "illustration").stdout)
    ref = handoff["brief"]["layout_reference"]
    assert {"action", "count-pond", "order-shed-pond"} <= handoff["brief"]["visual_checks"].keys()
    dry = json.loads(run("edition", "gemini", root, slot, "--dry-run").stdout)
    assert any(ref["sha256"] == item["sha256"] for item in dry["ordered_inputs"])
    assert "Layout from this camera" in dry["prompt"]
    assert not any("neighbour" in warning for warning in dry["warnings"])

    updated = load(plan)
    updated["shots"]["outbound"]["camera"]["yaw"] = 5
    write(plan, updated)
    with pytest.raises(ProjectError, match="stale rendered layout.*--stage"):
        gemini.dispatch(args, provider)
    assert not gemini.journal(root)[0].exists() and not provider.calls
    stage("second-layout")
    revision = edition.load_edition(root)["revision"]
    run("edition", "review", root, slot, "--revision", revision, "--role", "director",
        "--reviewer", "Fixture director", "--decision", "approved", "--evidence", "Camera and roster checked.")
    attempt = gemini.dispatch(args, provider)
    capsys.readouterr()
    assert attempt["status"] == "captured" and len(provider.calls) == 1
    assert "Layout from this camera" in provider.calls[0]["prompt"]
    run("edition", "gemini-quality", root, attempt["attempt"], "pass", "--reviewer", "Fixture reviewer",
        "--seconds", 1, "--evidence", "Fixture landmarks and handle checked.")
    revise(root, tmp_path / "assign.json", {"op": "assign", "kind": "illustration", "page": "outbound",
                                          "attempt": attempt["attempt"], "reason": "Reviewed fixture"})
    run("edition", "review", root, slot, "--revision", edition.load_edition(root)["revision"], "--role", "visual",
        "--reviewer", "Fixture reviewer", "--decision", "approved", "--evidence", "Assigned pixels checked.")
    report = json.loads(run("edition", "check", root).stdout)
    row = next(row for row in report["slots"] if row["slot"] == slot)
    assert row["issues"] == [] and row["disposition"] == "reuse"
    assert "delivery/illustration" in report["generation_layout_blockers"]


def test_manual_reservation_requires_the_staged_asset_not_a_comparison(recurring_edition, tmp_path):
    root, _ = recurring_edition
    slot = "outbound/illustration"
    run("edition", "set-layout", root, "set-plans/garden.json", "outbound", tmp_path / "layout", "--stage")
    brief = json.loads(run("scene-handoff", root, "--page", "outbound", "--kind", "illustration").stdout)
    run("edition", "art-round", root, "fixture", write(tmp_path / "round.json", {
        "provider": "Fixture operator", "objective": "Show the ticket pickup", "slots": [slot], "limit": 1,
    }))
    shot = {"prompt": "Show the ticket pickup in this camera view.", "inputs": brief["comparisons"]}
    path = tmp_path / "shot.json"
    error = run("edition", "art-start", root, "fixture", slot, write(path, shot), ok=False).stderr
    assert "attach the staged rendered layout" in error
    reference = brief["brief"]["layout_reference"]
    shot["inputs"].append({key: reference[key] for key in ("file", "sha256", "role")})
    reserved = json.loads(run("edition", "art-start", root, "fixture", slot, write(path, shot)).stdout)
    assert reserved["attempt"] and reserved["inputs"][-1]["sha256"] == reference["sha256"]
    assert {"count-pond", "action"} <= reserved["checks"].keys()
