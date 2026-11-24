"""CLI for plan v2: ab (drift gate), textspec, cast-sheet, sheets, scorecard, next, set-layout and set-score."""

from copy import deepcopy
import json
from pathlib import Path

from . import consistency, edition, setplan, textspec
from .edition.revise import apply_revision
from .edition.scene_layouts import declaration, plan_file
from .store import emit, load, project_file, require, serialized, sha256


def ab(args):
    regions = [consistency.parse_region(r) for r in args.region or []]
    result = consistency.drift(args.before, args.after, regions)
    result["limit"] = args.max
    result["accepted"] = result["outside_changed"] <= args.max
    emit(result)


def show_textspec(args):
    manifest = edition.load_edition(args.project)
    lexicon = textspec.project_lexicon(args.project)
    out = {}
    for page in manifest["pages"]:
        if args.page and page["id"] != args.page:
            continue
        brief = page["art"]["illustration"]["brief"]
        required = textspec.required_checks(page["text"], manifest.get("world"), brief.get("references", []), lexicon)
        out[page["id"]] = {"required": required, "missing": textspec.missing_checks(required, brief)}
    emit(out)


def make_cast_sheet(args):
    manifest = edition.load_edition(args.project)
    images = []
    for item in args.root:
        key, _, scale = item.partition("=")
        require(key in manifest["roots"], f"Unknown root {key}")
        images.append((edition.checked_path(args.project, manifest["roots"][key]["image"]), float(scale or 1)))
    require(not args.output.exists(), f"Output already exists: {args.output}")
    consistency.cast_sheet(images, args.output)
    emit({"output": str(args.output), "subjects": args.root})


def sheets(args):
    manifest = edition.load_edition(args.project, args.revision)
    require(not args.output.exists(), f"Output already exists: {args.output}")
    items = []
    for page in edition.pages(manifest):
        if page.get("role") == "back":
            continue
        item = page["art"].get(args.kind)
        if item is None:
            continue
        image = item.get("image")
        items.append((page["id"], edition.checked_path(args.project, image) if image else None))
    tile = (600, 402) if args.kind == "illustration" else (360, 264)
    consistency.contact_sheet(items, args.output, tile=tile, columns=4 if args.kind == "illustration" else 6)
    emit({"output": str(args.output), "slots": len(items)})


def scorecard(args):
    from .generation import journal
    manifest = edition.load_edition(args.project)
    assigned = [f"{p['id']}/{k}" for p in edition.pages(manifest) for k, item in p["art"].items()
                if item.get("image") and p.get("role") != "back"]
    issues = load(args.issues)["issues"] if args.issues else None
    emit(consistency.scorecard(journal(args.project)[1], assigned, issues))


def next_step(args):
    from .generation import journal
    manifest = edition.load_edition(args.project)
    packets = edition.compile_edition(args.project, manifest)
    emit(consistency.next_action(args.project, manifest, journal(args.project)[1],
                                         edition.active_reviews(args.project), packets))


def split_sheet(args):
    from .generation import journal
    attempt = journal(args.project)[1]["attempts"].get(args.attempt)
    require(attempt and attempt["status"] == "captured" and attempt.get("quality") == "pass",
            "Split only a captured sheet that passed review")
    require(not args.output.exists(), f"Output already exists: {args.output}")
    args.output.mkdir(parents=True)
    rows = [row.split(",") for row in args.rows]
    result = consistency.split_sheet(edition.checked_path(args.project, {"file": attempt["file"], "sha256": attempt["image_sha256"]}),
                                     rows, args.output)
    emit({"attempt": args.attempt, "pages": result})


def set_layout(args):
    if args.stage:
        return serialized(render_set_layout)(args)
    return render_set_layout(args)


def render_set_layout(args):
    """Render one page's shot of a set plan locally and derive its layout sentence and checks."""
    plan_path = args.plan if args.plan.is_absolute() else args.project / args.plan
    before = edition.load_edition(args.project) if args.stage else None
    if before:
        page = edition.page_by_id(before, args.page)
        require(not page.get("role"), "Stage layouts for story illustrations")
        setting = declaration(page["art"]["illustration"]["brief"])
        require(setting is not None, "Declare a recurring setting before staging its layout")
        source = plan_file(setting)
        require(plan_path.resolve() == project_file(args.project, source).resolve(),
                f"Use the shared set plan at {source}")
        plan_digest = sha256(plan_path.read_bytes())
        private = before["covers"]["back"]["art"]["illustration"].get("image", {}).get("sha256")
        require(not args.top or len(args.top) == len(args.top_role or []),
                "Label each staged top image with --top-role")
        for top in args.top or []:
            require(top.resolve().is_relative_to(args.project.resolve()),
                    "Staged top images must be inside the edition")
            require(sha256(top.read_bytes()) != private, "The private back cover is excluded from layout sheets")
    plan = setplan.load_plan(plan_path)
    shot = plan.get("shots", {}).get(args.page)
    require(shot, f"The set plan has no shot for {args.page}")
    require(not args.output.exists(), f"Output already exists: {args.output}")
    require(len(args.top_role or []) in (0, len(args.top or [])), "Give one --top-role per --top image, or none")
    args.output.mkdir(parents=True)
    layout = args.output / "layout.png"
    visible = setplan.render(plan, shot, layout)
    actors = [actor for actor in shot.get("actors", {}) if actor in visible]
    result = {"page": args.page, "plan": str(plan_path), "layout": str(layout), "visible": visible,
              "text": setplan.describe(plan, visible), "checks": setplan.checks(plan, visible, actors)}
    if args.top:
        sheet = setplan.compose(layout, args.top, args.output / "sheet.png")
        result["sheet"] = str(sheet)
    result["role"] = setplan.layout_role(plan, actors, args.top_role or [])
    (args.output / "derived.json").write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    if before:
        result["staged"] = stage_layout(args, before, source, plan_digest, result)
    emit(result)


def stage_layout(args, before, plan, plan_digest, result):
    root = args.project
    edition.checked_path(root, {"file": plan, "sha256": plan_digest})
    brief = deepcopy(edition.page_by_id(before, args.page)["art"]["illustration"]["brief"])
    asset = Path(result.get("sheet", result["layout"]))
    brief["layout_reference"] = {
        "file": asset.name, "role": result["role"],
        "rendered": {"plan": plan, "plan_sha256": plan_digest, "page": args.page,
                     "text": result["text"], "checks": result["checks"]},
    }
    # Normalize older briefs that predate the named comparison references.
    legacy = brief.pop("comparison_pages", [])
    if legacy:
        brief.setdefault("comparison_references", []).extend(
            {"page": page, "kind": "illustration",
             "role": f"Neighbour page {page}: use its illustration style and preserve the identity of recurring elements"}
            for page in legacy if page != args.page)
    spec = {"revision": before["revision"], "editor": "storybook set-layout", "reason": f"Render {args.page} from {plan}",
            "operations": [{"op": "stage", "kind": "illustration", "page": args.page, "brief": brief}]}
    return apply_revision(root, before, spec, asset.parent, render_layout=True)


def set_score(args):
    """Agreement with the set plan: the share of derived checks a reviewer answered yes, per image and arm."""
    emit(setplan.score(load(args.answers), load(args.key) if args.key else None))


def register(add):
    """Add this module's commands under `storybook edition` through edition.register's helper."""
    parser = add("ab", ab)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--region", action="append", help="Target region x0,y0,x1,y1 as fractions (repeatable)")
    parser.add_argument("--max", type=float, default=0.01)
    parser = add("textspec", show_textspec)
    parser.add_argument("--page")
    parser = add("cast-sheet", make_cast_sheet)
    parser.add_argument("output", type=Path)
    parser.add_argument("--root", action="append", required=True, help="Root key, optionally key=relative-height")
    parser = add("sheets", sheets)
    parser.add_argument("output", type=Path)
    parser.add_argument("--kind", choices=edition.KINDS, default="illustration")
    parser.add_argument("--revision")
    parser = add("scorecard", scorecard)
    parser.add_argument("--issues", type=Path, help="Issue ledger JSON with an issues list")
    add("next", next_step)
    parser = add("split-sheet", split_sheet)
    parser.add_argument("attempt", help="A passed colouring-sheet attempt")
    parser.add_argument("output", type=Path, help="New directory for one PNG per subject")
    parser.add_argument("--rows", action="append", required=True, help="Comma-separated names for one grid row, top first")
    parser = add("set-layout", set_layout)
    parser.add_argument("plan", type=Path, help="Set plan JSON (relative to the project or absolute)")
    parser.add_argument("page", help="Page ID with a shot in the plan")
    parser.add_argument("output", type=Path, help="New directory for layout.png, sheet.png and derived.json")
    parser.add_argument("--stage", action="store_true", help="Stage the rendered layout and checks in a new revision")
    parser.add_argument("--top", type=Path, action="append", help="Image for the sheet's top band (repeatable)")
    parser.add_argument("--top-role", action="append", help="Role sentence for each --top image, in order")
    parser = add("set-score", set_score)
    parser.add_argument("answers", type=Path, help="Reviewer answers: {image: {check: {answer: yes|no|unclear}}}")
    parser.add_argument("--key", type=Path, help="Optional {image: {page, arm}} key for per-arm rates")
