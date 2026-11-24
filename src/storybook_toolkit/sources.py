"""Commands for preparing human-reviewed story sources: transcripts, the reviewed story and its adaptation."""

import difflib
import hashlib
import json
from pathlib import Path
from shlex import quote
import sys
from tempfile import TemporaryDirectory

from .languages import MODULES, get_module
from .store import ProjectError, atomic_writer, load, project_file, require, write_json


WORKSPACE_SOURCE = "source-review"
WORKSPACE_EDITION = "book-edition"
WORKSPACE_GUIDE = """# Story project files

| Path | What to look for |
| --- | --- |
| `inputs/` | Original transcripts, story and adaptation review files, edition plan and book metadata. |
| `source-review/project.json` | Source registry and current approvals. |
| `source-review/transcripts/` | Registered transcript copies. |
| `source-review/reviewed-story.json`, `source-review/adapted-story.json` | Saved English source and French adaptation. |
| `source-review/*-catalog.json`, `source-review/root-assets/` | Character and prop catalogs and their reviewed references. |
| `book-edition/edition.json` | Current page plan and artwork assignments, created at edition import. |
| `book-edition/content/`, `book-edition/revisions/` | Stored input and artwork files keyed by hash, plus saved copies of the edition plan. |
| `book-edition/artwork-preparation/` | Optional local cast sheets, set layouts and other art prepared before assignment. |
| `book-edition/edition-reviews.json`, `book-edition/generation-runs/` | Edition review decisions and provider attempts, when recorded. |
| `outputs/previews/`, `outputs/final/` | A dated directory per build with PDFs, reviewed text and the proof report. |

Use `storybook edition check PATH/to/book-edition` to see current artwork and
layout status. Build with `storybook edition build PATH/to/book-edition` and add
`--final` when ready. Keep agent working notes and reports in the checkout's
ignored `reports/` directory.
"""


def save(path, data):
    write_json(path, data)


def project(root):
    data = load(project_file(root, "project.json"))
    if not isinstance(data, dict) or data.get("format_version") != 1:
        raise ProjectError("Unsupported or invalid project format version")
    entries = data.get("transcripts")
    if not isinstance(entries, list) or any(
        not isinstance(entry, dict)
        or any(not isinstance(entry.get(key), str) or not entry[key] for key in ("id", "file", "original_name", "sha256"))
        for entry in entries
    ) or len({entry["id"] for entry in entries}) != len(entries):
        raise ProjectError("Invalid project transcript registry in project.json")
    return data


def init_source(root):
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ProjectError("Project directory must be empty")
    (root / "transcripts").mkdir()
    save(root / "project.json", {"format_version": 1, "scene_format_version": 3, "transcripts": [], "reviewed_story": None})


def init(args):
    root = args.project
    if getattr(args, "workspace", False):
        example = root.parent / f"{root.name or 'story'}-new"
        occupied = (f"Choose a new story workspace directory. {root} already exists. "
                    f"For example: storybook init {quote(str(example))} --workspace")
        require(not (root.exists() or root.is_symlink()), occupied)
        root.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=root.parent, prefix=".storybook-init-") as temp:
            stage = Path(temp) / "workspace"
            stage.mkdir(mode=0o700)
            (stage / "inputs").mkdir()
            (stage / "outputs" / "previews").mkdir(parents=True)
            (stage / "outputs" / "final").mkdir()
            init_source(stage / WORKSPACE_SOURCE)
            (stage / "README.md").write_text(WORKSPACE_GUIDE, encoding="utf-8")
            require(not (root.exists() or root.is_symlink()), occupied)
            stage.rename(root)
    else:
        init_source(root)
    print(f"Initialized {root}")


def register_transcript(args):
    root = args.project
    data = project(root)
    try:
        content = args.file.read_bytes()
        content.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProjectError(f"Cannot read UTF-8 transcript {args.file}: {exc}") from exc
    digest = hashlib.sha256(content).hexdigest()
    matches = [t["id"] for t in data["transcripts"] if t["sha256"] == digest]
    ident = f"T{len(data['transcripts']) + 1:04d}"
    target = project_file(root, Path("transcripts") / (ident + ".txt"))
    if target.exists() or target.is_symlink():
        raise ProjectError(f"Refusing to overwrite {target}")
    with atomic_writer(target) as file:
        file.write(content)
    data["transcripts"].append({"id": ident, "file": f"transcripts/{ident}.txt", "original_name": args.file.name, "sha256": digest})
    # New evidence requires a fresh human review.
    data["reviewed_story"] = None
    data["adapted_story"] = None
    save(root / "project.json", data)
    print(f"Registered {ident}" + (f"; exact byte duplicate of {', '.join(matches)}" if matches else ""))


def transcript(root, entry):
    path = project_file(root, entry["file"])
    try:
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ProjectError(f"Transcript {entry['id']} has changed since registration")
        return content.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ProjectError(f"Cannot read transcript {entry['id']}: {exc}") from exc


def compare(args):
    data = project(args.project)
    entries = data["transcripts"]
    if len(entries) < 2:
        raise ProjectError("Register at least two transcripts to compare")
    texts = [(entry, transcript(args.project, entry)) for entry in entries]
    for i, (a, left) in enumerate(texts):
        for b, right in texts[i + 1:]:
            print(f"{a['id']} vs {b['id']}: " + ("exact byte duplicate" if a["sha256"] == b["sha256"] else "different bytes"))
            if a["sha256"] != b["sha256"]:
                diff = list(difflib.unified_diff(left, right, fromfile=a["id"], tofile=b["id"], lineterm=""))
                if diff:
                    print("\n".join(diff))
                else:
                    print("Line content matches; bytes differ in line endings or final newline.")


def review(args):
    root = args.project
    data = project(root)
    entries = {entry["id"]: entry for entry in data["transcripts"]}
    if not entries:
        raise ProjectError("Register at least one transcript before review")
    for entry in entries.values():
        transcript(root, entry)
    story = load(args.story)
    if not isinstance(story, dict) or story.get("format_version") != 1:
        raise ProjectError("Story must be a version 1 JSON object")
    if not isinstance(story.get("reviewer"), str) or not story["reviewer"].strip() or story.get("human_reviewed") is not True:
        raise ProjectError("Story requires human_reviewed: true and a named human reviewer")
    passages = story.get("passages")
    if not isinstance(passages, list) or not passages:
        raise ProjectError("Story requires at least one passage")
    for passage in passages:
        if not isinstance(passage, dict) or not isinstance(passage.get("text"), str) or not passage["text"].strip():
            raise ProjectError("Each passage requires nonempty text")
        refs = passage.get("sources")
        if not isinstance(refs, list) or not refs:
            raise ProjectError("Each passage requires source references")
        for ref in refs:
            if not isinstance(ref, dict) or ref.get("transcript_id") not in entries or not isinstance(ref.get("location"), str) or not ref["location"].strip():
                raise ProjectError("Each source needs a registered transcript_id and nonempty location")
        if not isinstance(passage.get("uncertainty"), str):
            raise ProjectError("Each passage requires an uncertainty string (empty if none)")
    target = project_file(root, "reviewed-story.json")
    if target.exists():
        raise ProjectError("reviewed-story.json already exists; archive it before replacing it")
    save(target, story)
    data["reviewed_story"] = {"file": target.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    data["adapted_story"] = None
    save(root / "project.json", data)
    uncertain = sum(bool(passage["uncertainty"].strip()) for passage in passages)
    print(f"Saved human-reviewed story to {target}. Passages with recorded uncertainty: {uncertain}.")


def language_info(args):
    if args.language is None:
        for identifier, module in MODULES.items():
            print(f"{identifier}: {module['name']} ({module['status']})")
    else:
        print(json.dumps(get_module(args.language), ensure_ascii=False, indent=2))


def approve_adaptation(args):
    root = args.project
    data = project(root)
    source = data.get("reviewed_story")
    if not isinstance(source, dict) or source.get("file") != "reviewed-story.json":
        raise ProjectError("A current human-reviewed source story is required")
    source_path = project_file(root, source["file"])
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != source.get("sha256"):
        raise ProjectError("Reviewed source story has changed")
    for entry in data["transcripts"]:
        transcript(root, entry)
    source_story = load(source_path)
    if source_story.get("human_reviewed") is not True:
        raise ProjectError("Source story is not human-reviewed")
    story = load(args.story)
    validate_adaptation(story, source, source_story)
    target = project_file(root, "adapted-story.json")
    if target.exists():
        raise ProjectError("adapted-story.json already exists; archive it before replacing it")
    save(target, story)
    data["adapted_story"] = {"file": target.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "source_sha256": source["sha256"]}
    save(root / "project.json", data)
    print(f"Saved human-approved adaptation to {target}; review is not linguistic certification.")


def validate_adaptation(story, source, source_story):
    if not isinstance(story, dict) or story.get("format_version") != 1:
        raise ProjectError("Adaptation must be a version 1 JSON object")
    module = get_module(story.get("language"))
    if module["status"].startswith("test fixture"):
        print("Warning: selected module is a test fixture, not linguistic support.", file=sys.stderr)
    if story.get("source_sha256") != source["sha256"]:
        raise ProjectError("Adaptation must identify the current reviewed source SHA-256")
    if story.get("human_approved") is not True or not isinstance(story.get("reviewer"), str) or not story["reviewer"].strip():
        raise ProjectError("Adaptation requires human_approved: true and a named human reviewer")
    passages = story.get("passages")
    if not isinstance(passages, list) or not passages:
        raise ProjectError("Adaptation requires at least one passage")
    source_coverage = set()
    last_source_passage = -1
    for passage in passages:
        if not isinstance(passage, dict) or not isinstance(passage.get("text"), str) or not passage["text"].strip():
            raise ProjectError("Each adapted passage requires nonempty text")
        if not isinstance(passage.get("source_passages"), list) or not passage["source_passages"] or any(type(i) is not int or i < 0 or i >= len(source_story["passages"]) for i in passage["source_passages"]):
            raise ProjectError("Each adapted passage requires valid zero-based source_passages")
        ordered_indexes = [last_source_passage, *passage["source_passages"]]
        if any(right < left for left, right in zip(ordered_indexes, ordered_indexes[1:])):
            raise ProjectError("Adaptation must preserve reviewed source passage order")
        last_source_passage = passage["source_passages"][-1]
        source_coverage.update(passage["source_passages"])
        annotations = passage.get("annotations")
        if not isinstance(annotations, list):
            raise ProjectError("Each passage requires an annotations array, even when empty")
        for mark in annotations:
            if not isinstance(mark, dict) or mark.get("kind") not in module["annotation_kinds"]:
                raise ProjectError("Annotation kind is not supported by the selected language module")
            start, end = mark.get("start"), mark.get("end")
            text = passage["text"]
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or mark.get("text") != text[start:end]:
                raise ProjectError("Annotation span and text must match the passage")
            if mark["kind"] == "liaison":
                target = mark.get("target")
                if type(target) is not int or not end <= target < len(text) or not text[end:target].isspace() or not text[target].isalpha():
                    raise ProjectError("Liaison target must point to the next word after whitespace")
            if mark.get("context_reviewed") is not True or not isinstance(mark.get("note"), str) or not mark["note"].strip():
                raise ProjectError("Every annotation requires context review and a note")

    if source_coverage != set(range(len(source_story["passages"]))):
        raise ProjectError("Adaptation must reference every reviewed source passage")


def check_adaptation(args):
    root = args.project
    data = project(root)
    source = data.get("reviewed_story")
    pointer = data.get("adapted_story")
    if not isinstance(source, dict) or source.get("file") != "reviewed-story.json":
        raise ProjectError("A current human-reviewed source story is required")
    if not isinstance(pointer, dict) or pointer.get("file") != "adapted-story.json":
        raise ProjectError("A current approved adaptation is required")
    source_path = project_file(root, source["file"])
    if hashlib.sha256(source_path.read_bytes()).hexdigest() != source.get("sha256"):
        raise ProjectError("Reviewed source story has changed")
    if pointer.get("source_sha256") != source.get("sha256"):
        raise ProjectError("Adaptation source hash is stale")
    for entry in data["transcripts"]:
        transcript(root, entry)
    source_story = load(source_path)
    if not isinstance(source_story, dict) or source_story.get("human_reviewed") is not True:
        raise ProjectError("Source story is not human-reviewed")
    path = project_file(root, pointer["file"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != pointer.get("sha256"):
        raise ProjectError("Approved adaptation has changed")
    validate_adaptation(load(path), source, source_story)
    if not getattr(args, "quiet", False):
        print("Adaptation approval and hashes are current; review is not linguistic certification.")


def register(subparsers):
    p = subparsers.add_parser("init", help="Initialize an empty project directory")
    p.add_argument("project", type=Path)
    p.add_argument("--workspace", action="store_true",
                   help="Create a story workspace with inputs, source review and outputs")
    p.set_defaults(func=init)
    p = subparsers.add_parser("register", help="Copy an English UTF-8 transcript into a project")
    p.add_argument("project", type=Path)
    p.add_argument("file", type=Path)
    p.set_defaults(func=register_transcript)
    p = subparsers.add_parser("compare", help="Show exact duplicates and line differences")
    p.add_argument("project", type=Path)
    p.set_defaults(func=compare)
    p = subparsers.add_parser("review", help="Save a human-reviewed story JSON")
    p.add_argument("project", type=Path)
    p.add_argument("story", type=Path)
    p.set_defaults(func=review)
    p = subparsers.add_parser("languages", help="List modules or show language guidance")
    p.add_argument("language", nargs="?")
    p.set_defaults(func=language_info)
    p = subparsers.add_parser("approve-adaptation", help="Save a human-approved adapted story")
    p.add_argument("project", type=Path)
    p.add_argument("story", type=Path)
    p.set_defaults(func=approve_adaptation)
    p = subparsers.add_parser("check-adaptation", help="Verify saved adaptation approval and source integrity")
    p.add_argument("project", type=Path)
    p.set_defaults(func=check_adaptation)
