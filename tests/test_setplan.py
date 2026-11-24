"""Set plans: one 3D plan per set, rendered locally per page camera, with derived wording, checks and scores."""

import json

import pytest
from PIL import Image

from storybook_toolkit import setplan
from storybook_toolkit.store import ProjectError
from support import run

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
