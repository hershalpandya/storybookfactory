# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Exercise the checkout workflow export through the public CLI."""

from pathlib import Path

from support import run

REPOSITORY = Path(__file__).resolve().parents[1]


def test_export_preserves_product_guides_and_refuses_overwrite(tmp_path):
    target = tmp_path / "export"
    assert "skills/storybook/SKILL.md" in run("export-workflow", target).stdout
    for relative, source in (
        ("skills/storybook/SKILL.md", ".agents/skills/storybook/SKILL.md"),
        ("skills/storybook-image/SKILL.md", ".agents/skills/storybook-image/SKILL.md"),
        ("agent-instructions/codex.md", "agent-instructions/codex.md"),
        ("docs/EDITIONS.md", "docs/EDITIONS.md"),
    ):
        assert (target / relative).read_bytes() == (REPOSITORY / source).read_bytes()
    assert {path.name for path in (target / "skills").iterdir()} == {"storybook", "storybook-image"}

    marker = target / "keep"
    marker.write_text("user data", encoding="utf-8")
    assert "already exists" in run("export-workflow", target, ok=False).stderr
    assert marker.read_text(encoding="utf-8") == "user data"
