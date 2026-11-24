# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""The README quickstart example builds a reading preview from its files, offline."""

import json
from pathlib import Path

from support import run

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "pip-and-the-kite"


def test_quickstart_example_builds_a_reading_preview(tmp_path):
    workspace = tmp_path / "pip"
    source, edition = workspace / "source-review", workspace / "book-edition"
    run("init", workspace, "--workspace")
    assert (workspace / "inputs").is_dir()
    assert (workspace / "outputs" / "final").is_dir()
    assert "book-edition/generation-runs/" in (workspace / "README.md").read_text(encoding="utf-8")
    assert "Choose a new" in run("init", workspace, "--workspace", ok=False).stderr
    run("register", source, EXAMPLE / "transcript.txt")
    run("review", source, EXAMPLE / "reviewed-story.json")
    # french.json names the reviewed story's hash; a changed transcript or review file must be re-hashed.
    run("approve-adaptation", source, EXAMPLE / "french.json")
    run("init-catalogs", source)
    run("edition", "import", edition, source, EXAMPLE / "edition-index.json", EXAMPLE / "metadata.json")
    check = json.loads(run("edition", "check", edition).stdout)
    assert len(check["slots"]) == 6 and all("missing assignment" in s["issues"] for s in check["slots"])
    build = json.loads(run("edition", "build", edition, "--mode", "reading").stdout)
    output = Path(build["output"])
    assert output.parent == workspace / "outputs" / "previews"
    assert output.name.endswith(build["revision"][:8])
    next_build = json.loads(run("edition", "build", edition, "--mode", "reading").stdout)
    assert Path(next_build["output"]).parent == output.parent and next_build["output"] != str(output)
    assert {path.name for path in output.iterdir()} == {"reading.pdf", "reviewed-text.json", "proof-report.json"}
    assert build["build"] == "preview" and build["open_slots"] == 6
    pdf = output / "reading.pdf"
    assert pdf.read_bytes().startswith(b"%PDF") and pdf.read_bytes().count(b"/Type /Page") >= 4
