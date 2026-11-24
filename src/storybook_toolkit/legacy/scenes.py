"""Local scene handoffs; image creation is deliberately external."""
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

from ..sources import check_adaptation, project
from ..image_quality import validate_png  # noqa: F401  (former home)
from ..store import ProjectError, emit, fingerprint, identifier, load, project_file, prose, serialized, write_json


def series_manifest(root):
    """Format 1 scene plans name entities from a series manifest kept with the private project.

    The manifest is the project's ``series-manifest.json`` or the file named by ``STORYBOOK_SERIES_MANIFEST``.
    The toolkit ships none: series characters and references belong to their owner.
    """
    override = os.environ.get('STORYBOOK_SERIES_MANIFEST')
    path = Path(override).expanduser() if override else Path(root) / 'series-manifest.json'
    if not path.is_file():
        raise ProjectError('Format 1 scene plans need a series manifest: add series-manifest.json to the project '
                           'or set STORYBOOK_SERIES_MANIFEST to its path')
    return path, load(path)


def reference_root(manifest_path, manifest):
    override = os.environ.get('STORYBOOK_REFERENCE_DIR')
    if override:
        root = Path(override).expanduser()
        if not root.is_absolute():
            raise ProjectError('STORYBOOK_REFERENCE_DIR must be an absolute directory')
        return root
    relative = (manifest.get('local_reference_root') or {}).get('relative_to_manifest')
    return (manifest_path.parent / relative).resolve() if relative else None


def digest(content):
    return hashlib.sha256(content).hexdigest()


def validated_plan(root):
    data = project(root)
    check_adaptation(SimpleNamespace(project=root, quiet=True))
    plan = load(root / 'scenes.json')
    if not isinstance(plan, dict) or plan.get('format_version') not in (1, 2, 3) or plan.get('adaptation_sha256') != data['adapted_story']['sha256']:
        raise ProjectError('Scene plan must identify the current adaptation SHA-256')
    minimum = data.get('scene_format_version', 1)
    if plan['format_version'] < minimum:
        raise ProjectError(f'This project requires scene plan format_version {minimum} or later')
    pages = plan.get('pages')
    adaptation = load(root / 'adapted-story.json')
    if not isinstance(pages, list) or not pages:
        raise ProjectError('Scene plan needs at least one page')
    legacy = plan['format_version'] == 1
    entities = None  # loaded only when a format-1 page names series entities
    ids = set()
    passage_order = []
    requests = {'scene': set(), 'colouring': set()}
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get('id'), str) or not page['id'].strip() or page['id'] in ids:
            raise ProjectError('Each page needs a unique nonempty id')
        ids.add(page['id'])
        indices = page.get('passages')
        if not isinstance(indices, list) or not indices or any(type(i) is not int or not 0 <= i < len(adaptation['passages']) for i in indices):
            raise ProjectError('Each page needs valid zero-based adapted passage indexes')
        passage_order.extend(indices)
        for key in ('scene', 'colouring'):
            if not isinstance(page.get(key), str) or not page[key].strip():
                raise ProjectError(f'Each page requires an English {key} request')
            normalized = ' '.join(page[key].split()).casefold()
            if normalized in requests[key]:
                raise ProjectError(f'Each page requires a distinct {key} request')
            requests[key].add(normalized)
        if not legacy:
            if not identifier(page['id']):
                raise ProjectError('Staged page ids must use lowercase letters, digits, hyphens or underscores')
            continue
        refs = page.get('entities')
        if refs and entities is None and isinstance(refs, list):
            entities = {e['id'] for e in series_manifest(root)[1]['entities']}
        if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in entities for ref in refs):
            raise ProjectError('Each page needs an entities array of entity IDs from the series manifest (or an empty array)')
        brief = page.get('visual_brief', {})
        fields = {'action', 'characters', 'composition', 'preserve', 'checks'}
        if not isinstance(brief, dict) or any(key not in fields or not isinstance(value, str) or not value.strip() for key, value in brief.items()):
            raise ProjectError('visual_brief must contain only nonempty action, characters, composition, preserve or checks strings')
    if passage_order != list(range(len(adaptation['passages']))):
        raise ProjectError('Scene pages must cover every adapted passage exactly once and in order')
    if not legacy:
        covers = plan.get('covers', {})
        if not isinstance(covers, dict) or not covers.keys() <= {'front', 'back'}:
            raise ProjectError('Covers must be a front/back object')
        for cover in covers.values():
            if (not isinstance(cover, dict) or not identifier(cover.get('id'))
                    or cover['id'] in ids or not prose(cover.get('scene'))
                    or {'passages', 'colouring', 'colouring_subjects', 'colouring_placements', 'beats'} & cover.keys()):
                raise ProjectError('Each staged cover needs a unique id and an illustration request')
            ids.add(cover['id'])
        from .staging import validate_staging
        validate_staging(root, plan)
    if plan['format_version'] == 3:
        from .continuity import beat_ledger
        beat_ledger(root, plan, adaptation)
    return plan


def handoff(args):
    plan = validated_plan(args.project)
    if plan.get('format_version', 1) >= 2:
        from .staging import generation_packet, page_contract
        page = getattr(args, 'page', None)
        kind = getattr(args, 'kind', None)
        if not page or not kind:
            raise ProjectError('Staged handoff requires --page PAGE and --kind KIND')
        packet = generation_packet(args.project, page_contract(args.project, page, plan), kind)
        emit(packet)
        return
    if any(page['entities'] for page in plan['pages']):
        manifest_path, manifest = series_manifest(args.project)
        root = reference_root(manifest_path, manifest)
    else:
        manifest, root = {'entities': [], 'references': []}, None
    entities = {e['id']: e for e in manifest['entities']}
    references = {r['id']: r for r in manifest['references']}
    for page in plan['pages']:
        print(f"\nPage {page['id']} (adapted passages {page['passages']})")
        print(f"Story illustration: {page['scene']}")
        print(f"Fresh small colouring graphic: {page['colouring']}")
        brief = page.get('visual_brief', {})
        for label, key in [('Visible action', 'action'), ('Character and state', 'characters'), ('Composition and props', 'composition'), ('Must preserve', 'preserve'), ('Acceptance checks', 'checks')]:
            if key in brief:
                print(f"{label}: {brief[key]}")
        seen = set()
        for ident in page['entities']:
            entity = entities[ident]
            print(f"Continuity — {entity['name']}: {entity['visible_in_v10']} {entity['uncertainty']}")
            for ref in entity['reference_ids']:
                if ref in seen:
                    continue
                seen.add(ref)
                item = references[ref]
                path = root / item['path'] if root else None
                print(f"  {ref}: {item['use']} " + (f"[{path}]" if path and path.is_file() else '[MISSING]'))
        if any(not root or not (root / references[ref]['path']).is_file() for ref in seen):
            print('Visual continuity review PENDING: supply the local library and set STORYBOOK_REFERENCE_DIR to its absolute directory, then rerun handoff.')
        elif seen:
            print('Visual continuity review PENDING: a human must inspect the references and resulting art.')
    print('\nBefore generation, reconcile the scene and visual brief with references and current story state; see skills/storybook-image/SKILL.md. Create assets externally; register PNGs with register-asset and run check-assets. Human review of story relevance, fresh colouring art and continuity is required.')


def all_pages(plan):
    covers = plan.get('covers', {}) if plan.get('format_version', 1) >= 2 else {}
    return [*plan['pages'], *covers.values()]


def image_kinds(plan, page_id):
    if plan.get('format_version', 1) >= 2 and any(page['id'] == page_id for page in plan.get('covers', {}).values()):
        return ('illustration',)
    return ('illustration', 'colouring')


def asset_contract(root, plan, page):
    from .staging import page_contract
    if plan.get('format_version', 1) >= 2:
        contract = page_contract(root, page, plan)
        return fingerprint(contract), contract
    return digest((root / 'scenes.json').read_bytes()), None


def register_asset(args):
    plan = validated_plan(args.project)
    if args.page not in {p['id'] for p in all_pages(plan)} or args.kind not in image_kinds(plan, args.page):
        raise ProjectError('Unknown page or image kind for that page')
    content = args.file.read_bytes()
    validate_png(content)
    registry_path = args.project / 'assets.json'
    registry = load(registry_path) if registry_path.exists() else {'format_version': 1, 'assets': []}
    if registry.get('format_version') != 1 or not isinstance(registry.get('assets'), list):
        raise ProjectError('Invalid asset registry')
    if any(not isinstance(a, dict) for a in registry['assets']):
        raise ProjectError('Invalid asset registry entry')
    plan_hash, contract = asset_contract(args.project, plan, args.page)
    if plan['format_version'] == 1 and any(a.get('plan_sha256') != plan_hash or a.get('adaptation_sha256') != plan['adaptation_sha256'] for a in registry['assets']):
        raise ProjectError('Scene plan changed; archive the stale asset registry before registering assets')
    existing = [a for a in registry['assets'] if (a.get('page'), a.get('kind')) == (args.page, args.kind)]
    if existing and not getattr(args, 'replace', False):
        raise ProjectError('Asset already registered for this page and kind; use --replace for a reviewed replacement')
    for item in existing:
        registry['assets'].remove(item)
    sha = digest(content)
    if any(a.get('sha256') == sha for a in registry['assets']):
        raise ProjectError('Each page and kind needs a distinct asset file')
    from ..catalog import publish_png
    production = plan["format_version"] == 3
    pixels = None
    if production:
        from ..image_quality import inspect_png
        pixels = inspect_png(content, contract["layout"][args.kind]["target_pt"])
        require_distinct_pixels(pixels, registry["assets"])
    if contract is not None:
        from .visual_review import approved_image
        approved_image(args.project, contract, args.kind, sha, plan, registry["assets"])
    target = publish_png(project_file(args.project, 'assets'), content)
    registry['assets'].append({'page': args.page, 'kind': args.kind, 'file': 'assets/' + target.name, 'sha256': sha, 'adaptation_sha256': plan['adaptation_sha256'], 'plan_sha256': plan_hash})
    if production:
        registry["assets"][-1]["pixel_sha256"] = pixels
    write_json(registry_path, registry)
    status = 'visual review remains pending' if contract is None else 'recorded visual review passed'
    print(f'Registered {args.kind} for {args.page}; {status}.')


def require_distinct_pixels(pixels, assets):
    if any(item.get("pixel_sha256") == pixels for item in assets):
        raise ProjectError("Each page and kind needs distinct decoded artwork")


def check_assets(args, plan=None):
    if plan is None:
        plan = validated_plan(args.project)
    path = args.project / 'assets.json'
    registry = load(path) if path.exists() else {'format_version': 1, 'assets': []}
    if registry.get('format_version') != 1 or not isinstance(registry.get('assets'), list):
        raise ProjectError('Invalid asset registry')
    entries = {}
    hashes = set()
    for item in registry['assets']:
        if not isinstance(item, dict) or item.get('page') not in {p['id'] for p in all_pages(plan)} or item.get('kind') not in image_kinds(plan, item['page']):
            raise ProjectError('Invalid asset registry entry')
        key = (item['page'], item['kind'])
        if key in entries:
            raise ProjectError('Duplicate asset registry entry')
        sha = item.get('sha256')
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            raise ProjectError('Invalid asset hash')
        if sha in hashes:
            raise ProjectError('Each page and kind needs a distinct asset file')
        hashes.add(sha)
        entries[key] = item
    verified = {}
    seen_pixels = set()
    missing = []
    for page in all_pages(plan):
        current, contract = None, None
        for kind in image_kinds(plan, page['id']):
            item = entries.get((page['id'], kind))
            if not item:
                print(f"{page['id']} {kind}: PENDING — obtain and register a PNG")
                missing.append(f"{page['id']} {kind}")
                continue
            sha = item.get('sha256')
            if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha) or item.get('file') != f'assets/{sha}.png':
                raise ProjectError('Invalid asset path or hash')
            if current is None:
                current, contract = asset_contract(args.project, plan, page['id'])
            if item.get('plan_sha256') != current or item.get('adaptation_sha256') != plan['adaptation_sha256']:
                raise ProjectError(f"{page['id']} {kind}: scene plan changed; review and re-register asset")
            asset_path = project_file(args.project, item['file'])
            try:
                content = asset_path.read_bytes()
            except OSError as exc:
                raise ProjectError(f"{page['id']} {kind}: cannot read registered asset {item['file']}: {exc}") from exc
            if digest(content) != sha:
                raise ProjectError(f"{page['id']} {kind}: asset changed since registration")
            validate_png(content)
            if plan.get("format_version") == 3:
                from ..image_quality import inspect_png
                pixels = inspect_png(content, contract["layout"][kind]["target_pt"])
                if item.get("pixel_sha256") != pixels or pixels in seen_pixels:
                    raise ProjectError(f"{page['id']} {kind}: invalid or duplicate decoded artwork")
                seen_pixels.add(pixels)
            verified[(page['id'], kind)] = asset_path
            if contract is not None:
                from .visual_review import approved_image
                approved_image(args.project, contract, kind, sha, plan, registry['assets'])
                print(f"{page['id']} {kind}: registered; recorded visual review passed")
            else:
                print(f"{page['id']} {kind}: registered; human visual review PENDING")
    if missing:
        print('Missing assets remain pending; rerun after registration.')
    return verified, missing


def register(subparsers):
    p = subparsers.add_parser("scene-handoff", help="Show English scene requests and local continuity references")
    p.add_argument("project", type=Path)
    p.add_argument("--page")
    p.add_argument("--kind", choices=("illustration", "colouring"))
    p.set_defaults(func=handoff)
    p = subparsers.add_parser("register-asset", help="Register a supplied PNG for a page")
    p.add_argument("project", type=Path)
    p.add_argument("page")
    p.add_argument("kind", choices=("illustration", "colouring"))
    p.add_argument("file", type=Path)
    p.add_argument("--replace", action="store_true", help="Replace a page asset after review")
    p.set_defaults(func=serialized(register_asset))
    p = subparsers.add_parser("check-assets", help="Check pending and registered page assets")
    p.add_argument("project", type=Path)
    p.set_defaults(func=check_assets)
