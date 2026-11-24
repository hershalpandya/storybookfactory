# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Project storage primitives: atomic writes, JSON round trip, the write lock, fingerprints and the import graph."""

import ast
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from storybook_toolkit import store
from storybook_toolkit.store import ProjectError

PACKAGE = Path(store.__file__).parent


def test_atomic_writer_keeps_previous_content_when_the_write_fails(tmp_path):
    target = tmp_path / "data.json"
    target.write_text("old", encoding="utf-8")
    with pytest.raises(RuntimeError, match="interrupted"):
        with store.atomic_writer(target, "w", encoding="utf-8") as file:
            file.write("partial")
            raise RuntimeError("interrupted")
    assert target.read_text(encoding="utf-8") == "old"
    assert [path.name for path in tmp_path.iterdir()] == ["data.json"]


def test_write_json_round_trips_unicode_with_trailing_newline(tmp_path):
    value = {"titre": "Été", "pages": [1, 2]}
    store.write_json(tmp_path / "a" / "data.json", value)
    raw = (tmp_path / "a" / "data.json").read_text(encoding="utf-8")
    assert raw.endswith("}\n") and "Été" in raw
    assert store.load(tmp_path / "a" / "data.json") == value


def test_serialized_refuses_a_second_writer_while_the_lock_is_held(tmp_path, monkeypatch):
    calls = []
    handler = store.serialized(lambda args: calls.append(args) or "done")
    holder = sqlite3.connect(tmp_path / ".storybook-write-lock.sqlite")
    holder.execute("BEGIN IMMEDIATE")
    real_connect = sqlite3.connect
    monkeypatch.setattr(sqlite3, "connect", lambda path, timeout: real_connect(path, timeout=0))
    try:
        with pytest.raises(ProjectError, match="Cannot acquire project write lock"):
            handler(SimpleNamespace(project=tmp_path))
    finally:
        holder.close()
    assert calls == []
    assert handler(SimpleNamespace(project=tmp_path)) == "done"


def test_fingerprint_ignores_key_order_but_not_values():
    assert store.fingerprint({"a": 1, "b": [2]}) == store.fingerprint({"b": [2], "a": 1})
    assert store.fingerprint({"a": 1}) != store.fingerprint({"a": 2})


def test_store_depends_on_nothing_in_the_package_and_every_module_imports_alone():
    tree = ast.parse((PACKAGE / "store.py").read_text(encoding="utf-8"))
    relative = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level]
    assert relative == []
    modules = sorted("storybook_toolkit." + ".".join(path.relative_to(PACKAGE).with_suffix("").parts)
                     for path in PACKAGE.rglob("*.py") if path.name not in ("__init__.py", "__main__.py"))
    script = ("import importlib, sys\n"
              "for name in sys.argv[1:]:\n"
              "    for loaded in [m for m in sys.modules if m.startswith('storybook_toolkit')]:\n"
              "        del sys.modules[loaded]\n"
              "    importlib.import_module(name)\n")
    result = subprocess.run([sys.executable, "-c", script, *modules], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_edition_reaches_the_scene_plan_workflow_only_through_export_for_edition():
    legacy = {"legacy", "scenes", "staging", "continuity", "visual_review", "attempts"}
    found = []
    for path in sorted((PACKAGE / "edition").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")
                names = [alias.name for alias in node.names]
                if legacy & set(module) or (not node.module and legacy & set(names)):
                    found.append((path.name, node.module, names))
    assert found == [("importer.py", "legacy", ["export_for_edition"])]
