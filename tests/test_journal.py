"""Attempt journal transitions: pending -> captured or failed, once; duplicate pixels; pauses."""

import pytest

from storybook_toolkit import journal
from storybook_toolkit.store import ProjectError, load, write_json
from support import picture


@pytest.fixture
def pending(tmp_path):
    """A journal with two pending profile attempts in run 'r1'; yields (root, path)."""
    path = journal.run_path(tmp_path, "r1")
    path.parent.mkdir(parents=True)
    write_json(path, {"format_version": 1, "label": "fixture", "cases": {"c": {"packet": {"kind": "profile"}}},
                      "attempts": {ident: {"case": "c", "status": "pending", "started_at": 0.0}
                                   for ident in ("a1", "a2")}})
    return tmp_path, path


def test_capture_saves_intake_then_publishes_and_is_final(pending, tmp_path):
    root, path = pending
    result = journal.capture(root, "r1", "a1", file=picture(tmp_path / "out.png", 30))
    assert result["status"] == "captured" and (root / result["file"]).is_file()
    assert (path.parent / "intake" / "a1").read_bytes() == (tmp_path / "out.png").read_bytes()
    saved = load(path)["attempts"]["a1"]
    assert saved == {key: value for key, value in result.items() if key != "attempt"}
    before = path.read_bytes()
    assert journal.capture(root, "r1", "a1", error="late failure") == result
    assert path.read_bytes() == before


def test_capture_failure_and_duplicate_pixels(pending, tmp_path):
    root, path = pending
    assert journal.capture(root, "r1", "a1", error="Transfer failed")["status"] == "failed"
    with pytest.raises(ProjectError, match="cannot be empty"):
        journal.capture(root, "r1", "a2", error=" ")
    first = journal.capture(root, "r1", "a2", file=picture(tmp_path / "out.png", 30))
    assert first["status"] == "captured"
    record = load(path)
    record["attempts"]["a3"] = {"case": "c", "status": "pending", "started_at": 0.0}
    write_json(path, record)
    duplicate = journal.capture(root, "r1", "a3", file=picture(tmp_path / "copy.png", 30, comment="same pixels"))
    assert duplicate["status"] == "failed" and "duplicates" in duplicate["error"]


def test_resume_reads_the_saved_intake_after_an_interruption(pending, tmp_path):
    root, path = pending
    with pytest.raises(ProjectError, match="No saved provider response"):
        journal.capture(root, "r1", "a1", resume=True)
    intake = path.parent / "intake" / "a1"
    intake.parent.mkdir()
    intake.write_bytes(picture(tmp_path / "out.png", 40).read_bytes())
    with pytest.raises(ProjectError, match="Use --resume"):
        journal.capture(root, "r1", "a1", file=tmp_path / "out.png")
    assert journal.capture(root, "r1", "a1", resume=True)["status"] == "captured"


def test_pause_is_saved_before_the_error(pending):
    _, path = pending
    record = load(path)
    with pytest.raises(ProjectError, match="paused for p/illustration: budget"):
        journal.pause(path, record, "budget", "p/illustration", "a1")
    assert load(path)["paused"]["attempt"] == "a1"
    assert [p.parent.name for p in journal.journal_paths(path.parents[2], "r")] == ["r1"]
    assert list(journal.journal_paths(path.parents[2], "art-")) == []
