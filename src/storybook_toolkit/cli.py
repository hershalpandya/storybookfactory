"""Command-line wiring for the storybook toolkit: one parser, every module's commands, one exit code.

Each command module exposes ``register(subparsers)``; edition.register returns the helper through which
generation, v2_commands and art_rounds add their ``storybook edition`` subcommands.
"""

import argparse
from pathlib import Path
import shutil
import sys

from . import __version__
from . import art_rounds, catalog, edition, generation, legacy, provider, sources, v2_commands
# Re-exported for callers of the earlier single-module CLI.
from .sources import (approve_adaptation, check_adaptation, compare, init, language_info, project,
                      register_transcript as register, review, save, transcript, validate_adaptation)
from .store import ProjectError, load, project_file

# Product skills and guides copied from the checkout by export-workflow.
EXPORTED_SKILLS = ("storybook", "storybook-image")
WORKFLOW_DOCS = ("PROJECT-FORMAT.md", "LANGUAGE-MODULES.md", "SCENE-ASSETS.md", "PACKAGE-QUALITY.md",
                 "BOOK-RENDERING.md", "BOOK-STANDARD.md", "WORLD-TIMELINE.md", "EDITIONS.md", "PROVIDERS.md")


def export_workflow(args):
    """Copy the product workflow from the checkout into a new directory."""
    target = args.directory
    if target.exists():
        raise ProjectError(f"Export directory already exists: {target}; choose a new path")

    checkout = Path(__file__).resolve().parents[2]
    guides = [checkout / "docs" / name for name in WORKFLOW_DOCS]
    skills = [checkout / ".agents/skills" / name for name in EXPORTED_SKILLS]
    instructions = checkout / "agent-instructions"
    if not (all(path.is_file() for path in guides) and
            all((path / "SKILL.md").is_file() for path in skills) and instructions.is_dir()):
        raise ProjectError("Workflow files unavailable; run from a Storybook Factory checkout")

    target.mkdir(parents=True)
    for skill in skills:
        shutil.copytree(skill, target / "skills" / skill.name)
    shutil.copytree(instructions, target / "agent-instructions")
    (target / "docs").mkdir()
    for guide in guides:
        shutil.copyfile(guide, target / "docs" / guide.name)
    print(f"Exported workflow to {target}; start with skills/storybook/SKILL.md")


def for_project(check, edition_handler, scene_handler):
    """Route a command to the edition handler when PROJECT holds edition.json (tested with Path.<check>)."""
    def handler(args):
        if getattr(args.project / "edition.json", check)():
            return edition_handler(args)
        return scene_handler(args)
    return handler


def build_parser():
    parser = argparse.ArgumentParser(prog="storybook", description="Prepare human-reviewed storybook sources.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("export-workflow", help="Export agent instructions from a checkout to a new directory",
                       description="Run from a Storybook Factory checkout or a synced, unpacked source archive.")
    p.add_argument("directory", type=Path)
    p.set_defaults(func=export_workflow)
    sources.register(sub)
    catalog.register(sub)
    legacy.register(sub)
    # On an edition directory, scene-handoff and image-checklist read the edition instead of a scene plan.
    for name, check, edition_handler in (("scene-handoff", "exists", edition.scene_handoff),
                                         ("image-checklist", "is_file", edition.image_checklist)):
        command = sub.choices[name]
        command.set_defaults(func=for_project(check, edition_handler, command.get_default("func")))
    add = edition.register(sub)
    for module in (generation, v2_commands, art_rounds):
        module.register(add)
    provider.register(sub)
    return parser


def main(argv=None):
    """Run one command and return its exit code; argparse usage errors still exit with status 2."""
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ProjectError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
