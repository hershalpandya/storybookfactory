# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
import json

from support import run


def test_reviewed_story_and_source_evidence(tmp_path):
    root = tmp_path / "project"
    first = tmp_path / "one.txt"
    second = tmp_path / "two.txt"
    first.write_text("A fox said bonjour to the moon.\nAside: tea?\n", encoding="utf-8")
    second.write_text("A fox said bonjour to the sun.\n", encoding="utf-8")
    run("init", root)
    run("register", root, first)
    run("register", root, second)
    assert "-A fox" in run("compare", root).stdout
    draft = tmp_path / "draft.json"
    story = {"format_version": 1, "human_reviewed": True, "reviewer": "Test reviewer", "passages": [{"text": "A fox said bonjour to the moon.", "sources": [{"transcript_id": "T0001", "location": "line 1"}, {"transcript_id": "T0002", "location": "line 1"}], "uncertainty": "T0001 says moon; T0002 says sun."}]}
    draft.write_text(json.dumps(story), encoding="utf-8")
    run("review", root, draft)
    assert json.loads((root / "reviewed-story.json").read_text()) == story
    assert json.loads((root / "project.json").read_text())["reviewed_story"]
    assert "duplicate" in run("register", root, first).stdout
    assert json.loads((root / "project.json").read_text())["reviewed_story"] is None
    assert "already exists" in run("review", root, draft, ok=False).stderr


def test_missing_and_unreviewed_inputs(tmp_path):
    root = tmp_path / "project"
    run("init", root)
    assert "at least two" in run("compare", root, ok=False).stderr
    run("register", root, tmp_path / "missing.txt", ok=False)
    source = tmp_path / "input.txt"
    source.write_text("Hello.\n")
    run("register", root, source)
    draft = tmp_path / "draft.json"
    draft.write_text(json.dumps({"format_version": 1, "human_reviewed": False, "reviewer": "Person", "passages": []}))
    assert "human_reviewed" in run("review", root, draft, ok=False).stderr
    (root / "transcripts" / "T0001.txt").unlink()
    assert "Cannot read transcript" in run("review", root, draft, ok=False).stderr


def test_resume_and_line_endings(tmp_path):
    root = tmp_path / "project"
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_bytes(b"One\nTwo")
    second.write_bytes(b"One\nThree")
    run("init", root)
    run("register", root, first)
    run("register", root, second)
    assert "-Two\n+Three" in run("compare", root).stdout
    second.write_bytes(b"One\nTwo\n")
    run("register", root, second)
    assert "Line content matches" in run("compare", root).stdout
    registry = json.loads((root / "project.json").read_text())
    registry["transcripts"] = [None]
    (root / "project.json").write_text(json.dumps(registry))
    error = run("compare", root, ok=False).stderr
    assert "Invalid project transcript registry" in error and "Traceback" not in error


def test_transcript_registry_cannot_escape_project(tmp_path):
    import hashlib

    root = tmp_path / "project"
    run("init", root)
    outside = tmp_path / "private.txt"
    content = b"Private text outside the project boundary"
    outside.write_bytes(content)
    conf = root / "project.json"
    data = json.loads(conf.read_text())
    data["transcripts"] = [
        {"id": f"T{index:04}", "file": name, "original_name": "fixture.txt",
         "sha256": hashlib.sha256(content).hexdigest()}
        for index, name in enumerate(("../private.txt", "transcripts/alias.txt"), 1)
    ]
    (root / "transcripts" / "alias.txt").symlink_to(outside)
    for entries in (data["transcripts"], list(reversed(data["transcripts"]))):
        conf.write_text(json.dumps({**data, "transcripts": entries}))
        result = run("compare", root, ok=False)
        assert "must stay within the project" in result.stderr
        assert content.decode() not in result.stdout

    (root / "transcripts").rename(root / "formerly-transcripts")
    external_dir = tmp_path / "elsewhere"
    external_dir.mkdir()
    (root / "transcripts").symlink_to(external_dir, target_is_directory=True)
    result = run("register", root, outside, ok=False)
    assert "must stay within the project" in result.stderr
    assert list(external_dir.iterdir()) == []
