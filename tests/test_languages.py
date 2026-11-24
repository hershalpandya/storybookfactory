import json

import pytest

from storybook_toolkit.sources import validate_adaptation
from storybook_toolkit.store import ProjectError
from support import run


@pytest.fixture
def reviewed(tmp_path):
    """A project with one registered transcript and a human-reviewed one-passage source; yields (root, digest)."""
    root = tmp_path / "project"
    source = tmp_path / "source.txt"
    source.write_text("Everyone is here.", encoding="utf-8")
    run("init", root)
    run("register", root, source)
    review = tmp_path / "review.json"
    review.write_text(json.dumps({"format_version": 1, "human_reviewed": True, "reviewer": "Reader", "passages": [
        {"text": "Everyone is here.", "sources": [{"transcript_id": "T0001", "location": "line 1"}],
         "uncertainty": ""}]}))
    run("review", root, review)
    return root, json.loads((root / "project.json").read_text())["reviewed_story"]["sha256"]


def adaptation(digest, language, *passages):
    return {"format_version": 1, "language": language, "source_sha256": digest, "human_approved": True,
            "reviewer": "Reader", "passages": list(passages)}


def test_adaptation_context_and_source_gate(reviewed, tmp_path):
    root, digest = reviewed
    draft = tmp_path / "adapt.json"
    story = adaptation(digest, "fr-CE1", {"text": "Les amis.", "source_passages": [0], "annotations": [
        {"kind": "liaison", "start": 2, "end": 3, "text": "s", "target": 4, "context_reviewed": False,
         "note": "Liaison in this phrase."}]})
    draft.write_text(json.dumps(story))
    assert "context review" in run("approve-adaptation", root, draft, ok=False).stderr
    story["passages"][0]["annotations"][0]["context_reviewed"] = True
    draft.write_text(json.dumps(story))
    run("approve-adaptation", root, draft)
    assert json.loads((root / "adapted-story.json").read_text()) == story
    assert json.loads((root / "project.json").read_text())["adapted_story"]
    run("register", root, tmp_path / "source.txt")
    assert json.loads((root / "project.json").read_text())["adapted_story"] is None


def test_module_selection_and_missing_source(tmp_path):
    assert "fixture only" in run("languages", "test-xx").stdout
    assert "not implemented" in run("languages", "unknown", ok=False).stderr
    root = tmp_path / "project"
    run("init", root)
    draft = tmp_path / "draft.json"
    draft.write_text('{}')
    assert "reviewed source" in run("approve-adaptation", root, draft, ok=False).stderr


def test_fixture_module_is_flagged_on_approval(reviewed, tmp_path):
    root, digest = reviewed
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps(adaptation(digest, "test-xx",
                                           {"text": "Synthetic text.", "source_passages": [0], "annotations": []})))
    assert "test fixture" in run("approve-adaptation", root, draft).stderr


def test_saved_approval_integrity_and_fixture_boundary(reviewed, tmp_path):
    root, digest = reviewed
    draft = tmp_path / "draft.json"
    story = adaptation(digest, "test-xx", {"text": "Synthetic text.", "source_passages": [0], "annotations": [
        {"kind": "silent", "start": 0, "end": 1, "text": "S", "context_reviewed": True, "note": "Example"}]})
    draft.write_text(json.dumps(story))
    assert "not supported" in run("approve-adaptation", root, draft, ok=False).stderr
    story["passages"][0]["annotations"] = []
    draft.write_text(json.dumps(story))
    run("approve-adaptation", root, draft)
    assert "not linguistic certification" in run("check-adaptation", root).stdout
    artifact = root / "adapted-story.json"
    original = artifact.read_bytes()
    artifact.write_bytes(original + b" ")
    assert "adaptation has changed" in run("check-adaptation", root, ok=False).stderr
    artifact.write_bytes(original)
    source_file = root / "reviewed-story.json"
    original_source = source_file.read_bytes()
    source_file.write_text("{}")
    assert "source story has changed" in run("check-adaptation", root, ok=False).stderr
    source_file.write_bytes(original_source)
    (root / "transcripts" / "T0001.txt").write_text("changed")
    assert "changed since registration" in run("check-adaptation", root, ok=False).stderr


def passage(text, *indexes, annotations=()):
    return {"text": text, "source_passages": list(indexes), "annotations": list(annotations)}


SILENT = {"kind": "silent", "start": 3, "end": 4, "text": "s", "context_reviewed": True,
          "note": "Silent before the noun phrase; the later final s is pronounced here."}


@pytest.mark.parametrize("passages,error", [
    ([passage("Premier.", 0)], "every reviewed source passage"),
    ([passage("Deuxième.", 1), passage("Premier.", 0)], "preserve reviewed source passage order"),
    ([passage("Both, but backward.", 1, 0)], "preserve reviewed source passage order"),
    ([passage("Premier A.", 0), passage("Premier B.", 0), passage("Deuxième.", 1)], None),
    ([passage("Premier.", 0), passage("Deuxième.", 1)], None),
    ([passage("Tous les amis.", 0, annotations=[SILENT]), passage("Deuxième.", 1)], None),
], ids=["omitted", "reordered", "backward-within-passage", "split", "complete", "reviewed-silent-letter"])
def test_validate_adaptation_coverage_and_order(passages, error):
    source = {"sha256": "source"}
    source_story = {"passages": [{"text": "First"}, {"text": "Second"}]}
    story = adaptation("source", "fr-CE1", *passages)
    if error:
        with pytest.raises(ProjectError, match=error):
            validate_adaptation(story, source, source_story)
    else:
        validate_adaptation(story, source, source_story)
