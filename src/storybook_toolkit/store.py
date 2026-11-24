"""Project storage primitives shared by every command module.

This module imports nothing from the package: errors, JSON I/O, atomic writes, hashing, the project write
lock, JSON output and the small value validators live here so that command modules depend on it and not on
each other.
"""

from contextlib import contextmanager
from functools import wraps
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from tempfile import NamedTemporaryFile


class ProjectError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ProjectError(message)


def project_file(root, relative):
    """Resolve a stored project reference within the project boundary."""
    relative = Path(relative)
    path = root / relative
    if relative.is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ProjectError(f"Project reference must stay within the project: {relative}")
    return path


def load(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError(f"Cannot read {path}: {exc}") from exc
    return data


@contextmanager
def atomic_writer(path, mode="wb", encoding=None):
    """Publish a completed file with a single rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, mode=mode, encoding=encoding, delete=False) as temp:
        temporary = Path(temp.name)
        try:
            yield temp
            temp.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def write_json(path, value):
    with atomic_writer(path, "w", encoding="utf-8") as temp:
        json.dump(value, temp, indent=2, ensure_ascii=False)
        temp.write("\n")


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(encoded.encode("utf-8"))


def serialized(handler):
    """Serialize CLI read/modify/write operations on one private project."""
    @wraps(handler)
    def locked(args):
        require(args.project.is_dir(), f"Missing story project {args.project}")
        database = sqlite3.connect(project_file(args.project, ".storybook-write-lock.sqlite"), timeout=10)
        try:
            database.execute("BEGIN IMMEDIATE")
            return handler(args)
        except sqlite3.Error as exc:
            raise ProjectError(f"Cannot acquire project write lock: {exc}") from exc
        finally:
            database.close()

    return locked


def emit(value):
    """Print a JSON report the way every command does."""
    print(json.dumps(value, ensure_ascii=False, indent=2))


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value) is not None


def prose(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value):
    return isinstance(value, dict) and all(identifier(key) and prose(item) for key, item in value.items())


def counts(value):
    return isinstance(value, dict) and all(
        identifier(key) and type(item) is int and item >= 0 for key, item in value.items()
    )


def project_command(subparsers, name, help_text, handler):
    """Add a subcommand whose first argument is the project directory."""
    command = subparsers.add_parser(name, help=help_text)
    command.add_argument("project", type=Path)
    command.set_defaults(func=handler)
    return command
