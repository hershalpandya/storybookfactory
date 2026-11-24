# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""The public toolkit stays free of private story material.

The private directories are ignored by Git. The check rejects tracked files in those directories and
scans staged files and working copies for personal paths, email addresses and local private terms.
"""

import os
import re
import subprocess
import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIP = {"uv.lock", "src/storybook_toolkit/fonts/Marelle2-Regular.ttf", "src/storybook_toolkit/fonts/LICENSE"}
PRIVATE_DIRS = ("projects/", "reports/", "local-references/")
GENERIC = [r"/users/[a-z]", r"/home/[a-z]", r"[a-z0-9._%+-]+@(?!anthropic\.com)[a-z0-9-]+\.[a-z]{2,}"]


def fold(text):
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def git(root, *command):
    return subprocess.run(["git", *command], cwd=root, capture_output=True, check=True).stdout


def index_entries(root):
    for row in git(root, "ls-files", "--stage", "-z").split(b"\0")[:-1]:
        metadata, name = row.split(b"\t", 1)
        mode, object_id, _ = metadata.split()
        yield os.fsdecode(name), mode, object_id.decode("ascii")


def public_files(root, tracked):
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")[:-1]
    working = {os.fsdecode(name) for name in untracked}
    for name, mode, object_id in tracked:
        if name.startswith(PRIVATE_DIRS) or name in SKIP or mode == b"160000":
            continue
        working.add(name)
        yield name, "index", git(root, "cat-file", "blob", object_id)
    for name in sorted(working):
        path = root / name
        if name.startswith(PRIVATE_DIRS) or name in SKIP or not path.is_file() or path.is_symlink():
            continue
        yield name, "working tree", path.read_bytes()


def private_patterns(root):
    terms = root / "reports" / "private-terms.txt"
    if not terms.is_file():
        return []
    return [line.strip() for line in terms.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def check_public_tree(root):
    try:
        tracked = list(index_entries(root))
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a Git checkout")
    private_paths = sorted({name for name, _, _ in tracked if name.startswith(PRIVATE_DIRS)})
    assert not private_paths, "Private directories contain tracked files:\n" + "\n".join(private_paths)

    patterns = [re.compile(p) for p in GENERIC + private_patterns(root)]
    found = []
    for name, location, content in public_files(root, tracked):
        try:
            text = fold(content.decode("utf-8"))
        except UnicodeDecodeError:
            continue
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                found.append(f"{name} ({location}): {match.group(0)!r}")
    assert not found, "Private material in public files:\n" + "\n".join(found)


def test_public_files_carry_no_private_material():
    check_public_tree(ROOT)


def test_privacy_scan_sees_index_when_worktree_differs(tmp_path, monkeypatch):
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)
    git(tmp_path, "init", "-q")
    note = tmp_path / "note.md"
    # Assemble the fixture address so the repository scan does not flag this test's source.
    address = "reviewer" + "@" + "example.org"
    note.write_text(address, encoding="utf-8")
    git(tmp_path, "add", note.name)
    note.write_text("Public draft", encoding="utf-8")
    with pytest.raises(AssertionError, match=r"note\.md \(index\)"):
        check_public_tree(tmp_path)

    git(tmp_path, "add", note.name)
    check_public_tree(tmp_path)
    note.write_text(address, encoding="utf-8")
    with pytest.raises(AssertionError, match=r"note\.md \(working tree\)"):
        check_public_tree(tmp_path)
