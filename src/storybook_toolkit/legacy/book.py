# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Scene-plan (scenes.json) books: layout preflight and the PDF render of a registered asset set."""

import contextlib
from io import StringIO
import json
from pathlib import Path

from ..render import (COVER_BOXES, FONT, artwork_boxes, book_metadata, check_titles, render_book,
                      typeset)
from ..store import ProjectError, emit, fingerprint, load, project_command, require, sha256, write_json
from . import scenes


def prepare_text(root, plan, font_path):
    adaptation = load(root / 'adapted-story.json')
    blocks = [(page['id'], [(adaptation['passages'][i]['text'], adaptation['passages'][i]['annotations'])
                            for i in page['passages']]) for page in plan['pages']]
    typeset_pages = typeset(blocks, font_path,
                            overflow="Page {page}: text overflow ({height} pt; maximum under {limit} pt)")
    prepared = [(page, lines, height) for page, (lines, height, _) in zip(plan['pages'], typeset_pages)]
    return adaptation, prepared


def pagination_key(plan):
    return fingerprint({
        "adaptation_sha256": plan["adaptation_sha256"],
        "pages": [(page["id"], page["passages"]) for page in plan["pages"]],
        "covers": {role: page["id"] for role, page in plan.get("covers", {}).items()},
    })


def layout_preflight(args):
    root = args.project
    plan = scenes.validated_plan(root)
    metadata = book_metadata(args.metadata)
    font_path = args.font or FONT
    font_hash = sha256(font_path.read_bytes())
    check_titles(metadata, font_path)
    if plan["format_version"] >= 2:
        require(not any(metadata.get(key) for key in ("cover_image", "back_image")),
                "Use staged covers for a version 2 or later plan")
    _, prepared = prepare_text(root, plan, font_path)
    require(sha256(font_path.read_bytes()) == font_hash, "Font changed during preflight")
    pages = {
        page["id"]: {
            kind: {"target_pt": list(box[2:]), "reading_box_pt": list(box),
                   "duplex_back_box_pt": list(artwork_boxes(height, True)[kind])}
            for kind, box in artwork_boxes(height).items()
        }
        for page, _, height in prepared
    }
    for role, page in plan.get("covers", {}).items():
        box = list(COVER_BOXES[role])
        pages[page["id"]] = {"illustration": {
            "target_pt": box[2:], "reading_box_pt": box, "duplex_back_box_pt": box,
        }}
    record = {"format_version": 1, "pagination_sha256": pagination_key(plan),
              "metadata_sha256": fingerprint(metadata), "font_sha256": font_hash, "pages": pages}
    write_json(root / "layout.json", record)
    emit(record)


def approved_layout(root, plan):
    layout = load(root / "layout.json")
    require(isinstance(layout, dict) and layout.get("format_version") == 1
            and layout.get("pagination_sha256") == pagination_key(plan),
            "Layout preflight is stale. Run layout-preflight for the current pagination.")
    return layout


def render(args):
    root, out = args.project, args.output
    plan = scenes.validated_plan(root)
    with contextlib.redirect_stdout(StringIO()):
        assets, missing = scenes.check_assets(args, plan)
    if missing:
        raise ProjectError('Missing assets: ' + ', '.join(missing))
    metadata = book_metadata(args.metadata)
    font_path = args.font or FONT
    if plan["format_version"] == 3:
        layout = approved_layout(root, plan)
        require(layout["metadata_sha256"] == fingerprint(metadata) and layout["font_sha256"] == sha256(font_path.read_bytes()),
                "Metadata or font changed. Run layout-preflight again before rendering.")
    adaptation, prepared = prepare_text(root, plan, font_path)
    cover_art = {}
    for role, key in (('front', 'cover_image'), ('back', 'back_image')):
        if plan['format_version'] >= 2:
            if metadata.get(key):
                raise ProjectError(f'Use a staged {role} cover in scenes.json for a version 2 or later plan')
            cover = plan.get('covers', {}).get(role)
            if cover:
                cover_art[role] = assets[(cover['id'], 'illustration')]
        elif metadata.get(key):
            path = args.metadata.parent / metadata[key]
            if not path.is_file():
                raise ProjectError(f'Missing {key}: {metadata[key]}')
            cover_art[role] = path
    if out.exists():
        raise ProjectError(f'Output directory already exists: {out}; choose a new directory')
    out.mkdir(parents=True)
    # Preserve exact approved text, annotations, source links, and page ordering.
    (out / 'reviewed-text.json').write_text(json.dumps({'adaptation': adaptation, 'pages': [{'id': p['id'], 'passages': p['passages']} for p in plan['pages']]}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    render_book(out, metadata, font_path, prepared, assets, cover_art)
    print(f'Rendered reading, regular, printer-safe and bound print PDFs and reviewed-text.json in {out}; visual and physical proof review remains required.')


def register_preflight(subparsers):
    p = project_command(subparsers, "layout-preflight", "Verify typography and report artwork slots before generation",
                        layout_preflight)
    p.add_argument("metadata", type=Path)
    p.add_argument("--font", type=Path)


def register(subparsers):
    p = subparsers.add_parser("render", help="Render reviewed assets to reading, regular and printer-safe PDFs")
    p.add_argument("project", type=Path)
    p.add_argument("metadata", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--font", type=Path, help="Optional shaped TrueType font")
    p.set_defaults(func=render)
