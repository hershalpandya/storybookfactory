"""The `storybook edition` command group."""

from pathlib import Path

from .. import render
from .build import approve, build, check
from .importer import initialise
from .revise import revise


def register(subparsers):
    """Add `storybook edition`; returns the helper that gemini, v2_commands and art_rounds register through."""
    command = subparsers.add_parser("edition", help="Import and build a versioned storybook edition")
    commands = command.add_subparsers(dest="edition_command", required=True)

    def add(name, callback):
        parser = commands.add_parser(name)
        parser.add_argument("project", type=Path)
        parser.set_defaults(func=callback)
        return parser

    parser = add("import", initialise)
    parser.add_argument("source", type=Path)
    parser.add_argument("specification", type=Path)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--font", type=Path)
    add("check", check)
    parser = add("build", build)
    parser.add_argument("output", type=Path, nargs="?",
                        help="New output directory; defaults to a dated folder under outputs")
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--reading-only", action="store_true")
    parser.add_argument("--mode", action="append", choices=render.MODES,
                        help="Render only this PDF (repeatable); default renders every mode")
    parser.add_argument("--revision", help="Build a preview from a saved revision")
    parser = add("revise", revise)
    parser.add_argument("operation", type=Path)
    parser = add("review", approve)
    parser.add_argument("slot")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--decision", choices=("approved", "rejected"), required=True)
    parser.add_argument("--evidence", required=True)
    return add
