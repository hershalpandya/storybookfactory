"""The public toolkit stays free of private story material.

The private directories are ignored by Git. The check rejects tracked files in those directories and
scans the public files for personal paths, email addresses and any locally configured private terms.
"""

import re
import subprocess
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TERMS = ROOT / "reports" / "private-terms.txt"
SKIP = {"uv.lock", "src/storybook_toolkit/fonts/Marelle2-Regular.ttf", "src/storybook_toolkit/fonts/LICENSE"}
PRIVATE_DIRS = ("projects/", "reports/", "local-references/")
GENERIC = [r"/users/[a-z]", r"/home/[a-z]", r"[a-z0-9._%+-]+@(?!anthropic\.com)[a-z0-9-]+\.[a-z]{2,}"]


def fold(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def git_files(*options):
    out = subprocess.run(["git", "ls-files", "-z", *options], cwd=ROOT, capture_output=True, check=True).stdout
    return out.decode().split("\0")[:-1]


def public_files():
    for name in git_files("--cached", "--others", "--exclude-standard"):
        path = ROOT / name
        if name.startswith(PRIVATE_DIRS) or name in SKIP or not path.is_file() or path.is_symlink():
            continue
        yield name, path


def private_patterns():
    if not TERMS.is_file():
        return []
    return [line.strip() for line in TERMS.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def test_public_files_carry_no_private_material():
    try:
        tracked = git_files("--cached")
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a Git checkout")
    private_paths = [name for name in tracked if name.startswith(PRIVATE_DIRS)]
    assert not private_paths, "Private directories contain tracked files:\n" + "\n".join(private_paths)

    patterns = [re.compile(p) for p in GENERIC + private_patterns()]
    found = []
    for name, path in public_files():
        try:
            text = fold(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                found.append(f"{name}: {match.group(0)!r}")
    assert not found, "Private material in public files:\n" + "\n".join(found)
