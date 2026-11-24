# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Edition revision operations that the end-to-end delivery test does not reach."""

from copy import deepcopy
import json

import pytest

from storybook_toolkit.edition import load_edition
from support import revise


def plain_world(root, scene_ids):
    """The fixture world without custody, so page order is free to change."""
    world = deepcopy(load_edition(root)["world"])
    world["initial_custody"] = {}
    world["scenes"] = [{"id": scene, "visible_zones": [], "visibility": {}} for scene in scene_ids]
    return world


def edit(root, tmp_path, *operations, ok=True, world=None):
    return revise(root, tmp_path / "op.json", *operations, ok=ok, world=world)


def test_layout_option_reopens_text_layout_and_checks_its_value(delivery, tmp_path):
    _, root, _, _ = delivery
    assert "true or false" in edit(root, tmp_path, {"op": "layout", "keep_french_punctuation": "yes"},
                                   ok=False).stderr
    report = json.loads(edit(root, tmp_path, {"op": "layout", "keep_french_punctuation": True}).stdout)
    assert report["text_layout_reopened"] and report["visual_changes"] == []
    assert load_edition(root)["layout"]["keep_french_punctuation"] is True


def test_reorder_moves_pages_and_events_together(delivery, tmp_path):
    _, root, _, _ = delivery
    assert "each story page once" in edit(root, tmp_path, {"op": "reorder", "pages": ["delivery"]},
                                          ok=False).stderr
    assert "every event" in edit(root, tmp_path, {"op": "reorder", "pages": ["delivery", "outbound"],
                                                  "event_order": ["handoff"]}, ok=False).stderr
    edit(root, tmp_path, {"op": "reorder", "pages": ["delivery", "outbound"],
                          "event_order": ["handoff", "pickup", "fly"]},
         world=plain_world(root, ["delivery", "outbound"]))
    manifest = load_edition(root)
    assert [page["id"] for page in manifest["pages"]] == ["delivery", "outbound"]
    assert [event["id"] for event in manifest["events"]] == ["handoff", "pickup", "fly"]


def test_merge_joins_the_next_page_and_reopens_its_art(delivery, tmp_path):
    _, root, _, _ = delivery
    briefs = {kind: {"description": f"Merged {kind}", "references": []} for kind in ("illustration", "colouring")}
    merge = {"op": "merge", "page": "delivery", "with": "outbound", "text": "Elle donne le ticket.",
             "annotations": [], "briefs": briefs}
    assert "next story page" in edit(root, tmp_path, merge, ok=False).stderr
    merge.update(page="outbound", **{"with": "delivery"}, text="Marine prend le ticket et le donne à Lumen.")
    edit(root, tmp_path, merge, world=plain_world(root, ["outbound"]))
    (page,) = load_edition(root)["pages"]
    assert page["id"] == "outbound" and page["events"] == ["pickup", "fly", "handoff"]
    assert {kind: item["disposition"] for kind, item in page["art"].items()} == \
        {"illustration": "unresolved", "colouring": "unresolved"}
    assert not any("image" in item for item in page["art"].values())


def test_unassign_reopens_one_slot_with_a_reason(delivery, tmp_path):
    _, root, _, _ = delivery
    unassign = {"op": "unassign", "page": "delivery", "kind": "colouring"}
    assert "Explain why" in edit(root, tmp_path, unassign, ok=False).stderr
    report = json.loads(edit(root, tmp_path, {**unassign, "reason": "Redraw the treads"}).stdout)
    assert [change["slot"] for change in report["visual_changes"]] == ["delivery/colouring"]
    art = load_edition(root)["pages"][1]["art"]
    assert "image" not in art["colouring"] and art["colouring"]["disposition"] == "unresolved"
    assert "image" in art["illustration"]


def test_unknown_operation_is_refused(delivery, tmp_path):
    _, root, _, _ = delivery
    assert "Unknown revision operation teleport" in edit(
        root, tmp_path, {"op": "teleport", "page": "outbound"}, ok=False).stderr


@pytest.mark.parametrize("field,value,error", [
    ("max_inputs", 15, "max_inputs must be 1 to 14"),
    ("drift_max", 0.5, "drift_max is a share of pixels"),
    ("strict_references", "yes", "strict_references is true or false"),
    ("max_failures_per_slot", 6, "max_failures_per_slot must be 1 to 5"),
    ("checks", ["text", "anatomy"], "checks may list text and colouring"),
])
def test_generation_policy_rejects_out_of_range_options(delivery, tmp_path, field, value, error):
    _, root, _, _ = delivery
    policy = {"op": "generation", "model": "gemini-nano-banana-2.1", "max_submissions": 3,
              "slots": ["outbound/illustration"], field: value}
    assert error in edit(root, tmp_path, policy, ok=False).stderr


def test_every_revision_operation_is_documented():
    from pathlib import Path

    from storybook_toolkit.edition import OPERATIONS
    guide = (Path(__file__).resolve().parents[1] / "docs" / "EDITIONS.md").read_text(encoding="utf-8")
    assert [name for name in OPERATIONS if f"`{name}`" not in guide] == []


def test_operation_files_cannot_reach_outside_the_edition_or_the_operation_folder(delivery, tmp_path):
    """Security audit finding: a revision file from someone else must not pull arbitrary files into the edition."""
    from support import picture
    _, root, _, _ = delivery
    key = "characters/marine/flying/front"
    collaborator = tmp_path / "collaborator"
    collaborator.mkdir()
    private = tmp_path / "owner-pictures"
    private.mkdir()
    picture(private / "family.png", 201)
    before = load_edition(root)["roots"][key]["image"]
    for name in ("../owner-pictures/family.png", str(private / "family.png")):
        error = revise(root, collaborator / "op.json", {"op": "root", "root": key, "file": name, "evidence": "x"},
                       ok=False).stderr
        assert "Operation files must" in error
    assert load_edition(root)["roots"][key]["image"] == before
    (root / "ops").mkdir()
    (root / "sources").mkdir()
    picture(root / "sources" / "clean.png", 202)
    revise(root, root / "ops" / "op.json", {"op": "root", "root": key, "file": "../sources/clean.png",
                                            "evidence": "Clean crop kept with the edition"})
    assert load_edition(root)["roots"][key]["image"] != before
