# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Revision operations: each operation is one function in OPERATIONS; revise applies them in order."""

from pathlib import Path
from copy import deepcopy

from ..journal import find_attempt
from ..store import ProjectError, emit, fingerprint, identifier, load, prose, require, serialized
from .manifest import KINDS, blob, checked_path, load_edition, page_by_id, picture
from .slots import changes, compile_edition, director_dependency, layout, publish


def unset_art(page, briefs, reason, keep=None):
    require(set(briefs) == set(KINDS), "Supply distinct illustration and colouring briefs")
    for kind, brief in briefs.items():
        prior = page["art"].get(kind, {})
        carried = {"image": prior["image"]} if kind in (keep or []) and "image" in prior else {}
        page["art"][kind] = {"brief": brief, "reason": reason, "disposition": "unresolved", **carried}


def split_page(edition, index, op):
    page = edition["pages"][index]
    left, right = op["parts"]
    require(left["id"] == page["id"] and right["id"] != left["id"], "A split must retain the first page ID and add a new ID")
    require(left["events"] + right["events"] == page["events"], "A split must retain the original event order")
    a, b = left["offset"], right["offset"]
    require(0 < a <= b < len(page["text"]) and not page["text"][a:b].strip(), "Split must preserve the wording")
    require(all(left["briefs"][kind] != right["briefs"][kind] for kind in KINDS),
            "Split pages need distinct visual and colouring briefs")
    require(not set(left.get("carry", [])) & set(right.get("carry", [])),
            "An old image can be carried forward to only one split slot")
    new_pages = []
    for part, start, end in ((left, 0, a), (right, b, len(page["text"]))):
        target = deepcopy(page)
        target.update(id=part["id"], events=part["events"], text=page["text"][start:end], annotations=[])
        for mark in page["annotations"]:
            final_offset = mark.get("target", mark["end"] - 1)
            require(not (mark["start"] < start <= final_offset or mark["start"] < end <= final_offset),
                    "Split would cut a pronunciation annotation")
            if start <= mark["start"] and final_offset < end:
                target["annotations"].append({k: v - start if k in ("start", "end", "target") else v
                                              for k, v in mark.items()})
        unset_art(target, part["briefs"], "Split beat needs visual review", part.get("carry"))
        new_pages.append(target)
    edition["pages"][index:index + 1] = new_pages


class Revision:
    """What every operation sees: the project root, the draft edition, the envelope and its directory."""

    def __init__(self, root, edition, spec, folder, *, render_layout):
        self.root, self.edition, self.spec, self.folder = root, edition, spec, folder
        self.render_layout = render_layout

    def file(self, name):
        """A file named by an operation: a relative path from the operation file that stays inside the edition
        directory or inside the operation file's own folder.

        Without this boundary a revision file received from someone else could pull any readable file (an
        absolute path, or ``../`` out of both folders) into content-addressed storage and, from there, into a
        provider request, where the stored hash no longer shows where it came from.
        """
        path = Path(name)
        require(not path.is_absolute(), f"Operation files must be relative paths: {name}")
        resolved = (self.folder / path).resolve()
        allowed = (Path(self.root).resolve(), Path(self.folder).resolve())
        require(any(resolved.is_relative_to(base) for base in allowed),
                f"Operation files must stay inside the edition or the operation file's folder: {name}")
        return self.folder / path


def op_layout(rev, op):
    require(type(op.get("keep_french_punctuation")) is bool, "Provide a true or false punctuation layout option")
    rev.edition["layout"]["keep_french_punctuation"] = op["keep_french_punctuation"]


def op_generation(rev, op):
    from ..generation import validate_policy  # generation imports edition
    rev.edition["generation"] = validate_policy(rev.root, rev.edition, op)


def op_missing_root(rev, op):
    # A reference-sheet definition: one clean subject (or a sheet of outlines) made from source crops.
    key, definition = op["key"], deepcopy(op["definition"])
    require(identifier(key) and prose(definition.get("description")), "A reference sheet needs a key and description")
    definition["sources"] = [{**blob(rev.root, rev.file(item["file"])), "role": item["role"]}
                             for item in definition.get("sources", [])]
    require(all(prose(item["role"]) for item in definition["sources"]), "Each source needs a role")
    rev.edition.setdefault("missing_roots", {})[key] = definition


def op_root(rev, op):
    roots = rev.edition["roots"]
    roots[op["root"]]["image"] = picture(rev.root, rev.file(op["file"]))
    require(prose(op.get("evidence")), "A replacement root needs review evidence")
    roots[op["root"]].update(visible_features=op["evidence"], reviewer=op.get("reviewer", rev.spec["editor"]))


def op_reorder(rev, op):
    edition = rev.edition
    order = op["pages"]
    require(set(order) == {p["id"] for p in edition["pages"]} and len(order) == len(edition["pages"]),
            "Reorder must include each story page once")
    edition["pages"] = [page_by_id(edition, page_id) for page_id in order]
    if op.get("event_order"):
        by_id = {event["id"]: event for event in edition["events"]}
        require(set(op["event_order"]) == set(by_id), "Reorder must retain every event")
        edition["events"] = [by_id[event] for event in op["event_order"]]


def op_assign(rev, op, page):
    root, edition = rev.root, rev.edition
    item = page["art"][op["kind"]]
    require(not (op.get("attempt") and op.get("file")),
            "Choose one artwork source: a reviewed attempt or a file")
    if op.get("attempt"):
        if op.get("round"):
            from ..art_rounds import path_for  # art_rounds imports edition
            art_round = load(path_for(root, op["round"]))
            require(art_round.get("closed"), "Close the reviewed art round before promoting its output")
            attempted = find_attempt(art_round, op["attempt"])
        else:
            from ..generation import journal  # generation imports edition
            attempted = find_attempt(journal(root)[1], op["attempt"])
        present = compile_edition(root, edition)[f"{page['id']}/{op['kind']}"]
        require(attempted["status"] == "captured" and attempted.get("quality") == "pass"
                and attempted["director_dependency"] == director_dependency(present),
                "Assign only a passed generation attempt for the current scene")
        image = checked_path(root, {"file": attempted["file"], "sha256": attempted["image_sha256"]})
        item["image"] = picture(root, image)
    if op.get("file"):
        item["image"] = picture(root, rev.file(op["file"]))
    disposition = op.get("disposition", "reuse") if op.get("attempt") else op["disposition"]
    item.update(disposition=disposition, reason=op["reason"])


def op_unassign(rev, op, page):
    # Start a slot again from its brief in a new edition; the old image stays in content/.
    require(prose(op.get("reason")), "Explain why the artwork is unassigned")
    item = page["art"][op["kind"]]
    item.pop("image", None)
    item.pop("imported_from", None)
    item.update(disposition="unresolved", reason=op["reason"])


def op_stage(rev, op, page):
    require("comparison_pages" not in op["brief"],
            "Name neighbour art with comparison_references (page, kind, role), not comparison_pages")
    brief = deepcopy(op["brief"])
    layout_ref = brief.get("layout_reference")
    slot = page["art"][op["kind"]]
    if isinstance(layout_ref, dict) and "rendered" in layout_ref and not rev.render_layout:
        require(layout_ref == slot["brief"].get("layout_reference"),
                "Render and stage layout evidence with edition set-layout --stage")
    if isinstance(layout_ref, dict) and layout_ref.get("file") and not layout_ref.get("sha256"):
        brief["layout_reference"] = {**blob(rev.root, rev.file(layout_ref["file"])),
                                     **{k: layout_ref[k] for k in ("role", "rendered") if k in layout_ref}}
    slot["brief"] = brief


def op_text(rev, op, page):
    require(not page.get("role"), "Text operations apply to story pages")
    wording_changed = page["text"] != op["text"]
    page.update(text=op["text"], annotations=op["annotations"])
    if wording_changed:
        if op.get("briefs"):
            unset_art(page, op["briefs"], "Wording changes the scene", op.get("carry"))
        else:
            require(prose(op.get("editorial_reason")), "Explain why the wording edit leaves the picture unchanged")
    page.setdefault("edits", []).append({"reason": op.get("editorial_reason", "Reading annotations edited"),
                                         "reviewer": rev.spec["editor"]})


def op_split(rev, op, page):
    require(not page.get("role"), "Split or merge applies to story pages")
    split_page(rev.edition, rev.edition["pages"].index(page), op)


def op_merge(rev, op, page):
    require(not page.get("role"), "Split or merge applies to story pages")
    edition = rev.edition
    index = edition["pages"].index(page)
    other = page_by_id(edition, op["with"])
    require(edition["pages"][index + 1:index + 2] == [other], "Merge requires the next story page")
    page.update(events=page["events"] + other["events"], text=op["text"], annotations=op["annotations"])
    unset_art(page, op["briefs"], "Merged events need visual review", op.get("carry"))
    edition["pages"].pop(index + 1)


# Operations on the whole edition, then operations on one named page (op["page"] is resolved first).
EDITION_OPERATIONS = {"layout": op_layout, "generation": op_generation, "missing_root": op_missing_root,
                      "root": op_root, "reorder": op_reorder}
PAGE_OPERATIONS = {"assign": op_assign, "unassign": op_unassign, "stage": op_stage, "text": op_text,
                   "split": op_split, "merge": op_merge}
OPERATIONS = {**EDITION_OPERATIONS, **PAGE_OPERATIONS}


@serialized
def revise(args):
    root = args.project
    before = load_edition(root)
    emit(apply_revision(root, before, load(args.operation), args.operation.parent))


def apply_revision(root, before, spec, folder, *, render_layout=False):
    edition = deepcopy(before)
    require(spec["revision"] == before["revision"], "Edition changed since the operation was prepared")
    require(prose(spec.get("editor")) and prose(spec.get("reason")) and spec["operations"],
            "A revision needs a named editor, reason and operations")
    rev = Revision(root, edition, spec, folder, render_layout=render_layout)
    for op in spec["operations"]:
        action = op["op"]
        if action in EDITION_OPERATIONS:
            EDITION_OPERATIONS[action](rev, op)
            continue
        page = page_by_id(edition, op["page"])
        if action not in PAGE_OPERATIONS:
            raise ProjectError(f"Unknown revision operation {action}")
        PAGE_OPERATIONS[action](rev, op, page)
    if "world" in spec:
        edition["world"] = spec["world"]
    edition.setdefault("edits", []).append({"editor": spec["editor"], "reason": spec["reason"]})
    require(fingerprint(edition) != fingerprint(before), "This operation makes no edition change")
    layout(root, edition)
    result = publish(root, edition, before["revision"])
    return changes(root, before, result)
