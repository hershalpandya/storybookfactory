"""The command-line surface: entry points and the public command names."""

from importlib import metadata
import re
import subprocess
import sys
from pathlib import Path

from support import run

TOP = ["export-workflow", "init", "register", "compare", "review", "languages", "approve-adaptation",
       "check-adaptation", "init-catalogs", "check-catalogs", "profile-brief", "register-reference",
       "import-catalog-entry", "set-preflight", "review-set", "image-checklist", "review-image", "benchmark-images",
       "benchmark-start", "attempt-start", "attempt-finish", "profile-reject", "benchmark-report", "scene-handoff",
       "register-asset", "check-assets", "layout-preflight", "check-world", "render", "edition", "provider"]
EDITION = ["import", "check", "build", "revise", "review", "gemini", "gemini-probe", "gemini-quality",
           "gemini-report", "gemini-readback", "gemini-resume", "ab", "textspec", "cast-sheet", "sheets", "scorecard",
           "next", "split-sheet", "set-layout", "set-score", "art-round", "art-start", "art-capture", "art-review",
           "art-status", "art-close"]
PROVIDER = ["status", "set-key", "choose"]


def commands(*prefix):
    usage = run(*prefix, "--help").stdout
    return re.search(r"\{([^}]*)\}", usage).group(1).split(",")


def test_public_command_names_are_stable():
    assert commands() == TOP
    assert commands("edition") == EDITION
    assert commands("provider") == PROVIDER


def test_module_and_console_script_entry_points(tmp_path):
    module = subprocess.run([sys.executable, "-m", "storybook_toolkit", "--version"], capture_output=True, text=True)
    assert module.returncode == 0 and module.stdout == f"storybook {metadata.version('storybook-toolkit')}\n"
    script = Path(sys.executable).with_name("storybook")
    installed = subprocess.run([str(script), "--help"], capture_output=True, text=True)
    assert installed.returncode == 0 and "export-workflow" in installed.stdout
    failed = subprocess.run([str(script), "check-adaptation", str(tmp_path / "missing")], capture_output=True,
                            text=True)
    assert failed.returncode == 1 and failed.stderr.startswith("error: ")
    usage = subprocess.run([str(script), "no-such-command"], capture_output=True, text=True)
    assert usage.returncode == 2
