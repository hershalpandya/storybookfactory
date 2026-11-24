# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Validate a declared set occupancy timeline before staging illustrations.

This checks editorial declarations, not generated pixels. A visual review is
still needed to confirm the image actually depicts the declared occupants.
"""
import json
from pathlib import Path

from .store import identifier, load, prose, require


def validate_world(world, catalog_ids, expected_scene_ids=None):
    require(isinstance(world, dict) and world.get('format_version') == 1,
            'World needs format_version 1')
    zones = world.get('zones')
    require(isinstance(zones, dict) and zones and all(identifier(k) and prose(v) for k, v in zones.items()),
            'World needs named zones with descriptions')
    links = world.get('connections')
    require(isinstance(links, list), 'World needs zone connections')
    edges = set()
    for pair in links:
        require(isinstance(pair, list) and len(pair) == 2 and all(x in zones for x in pair)
                and pair[0] != pair[1], 'Each connection must join two distinct known zones')
        edge = frozenset(pair)
        require(edge not in edges, 'Duplicate world connection')
        edges.add(edge)
    occupants = world.get('initial_occupancy')
    require(isinstance(occupants, dict) and occupants, 'World needs initial occupancy')
    require(all(identifier(k) and k in catalog_ids and v in zones for k, v in occupants.items()),
            'Initial occupants must be catalog characters in known zones')
    occupants = dict(occupants)
    objects = dict(world.get('initial_custody', {}))
    allowed_holders = set(occupants) | set(zones)
    require(all(identifier(item) and holder in allowed_holders for item, holder in objects.items()),
            'Initial custody requires a named object and a known holder')
    scenes = world.get('scenes')
    require(isinstance(scenes, list) and scenes, 'World needs ordered scenes')
    seen = set()
    result = []
    for scene in scenes:
        require(isinstance(scene, dict) and identifier(scene.get('id')) and scene['id'] not in seen,
                'Each world scene needs a unique ID')
        seen.add(scene['id'])
        before = dict(occupants)
        custody_before = dict(objects)
        events = scene.get('events', [])
        require(isinstance(events, list), f"{scene['id']}: events must be a list")
        for event in events:
            require(isinstance(event, dict), f"{scene['id']}: invalid event")
            actor, origin, destination = event.get('character'), event.get('from'), event.get('to')
            require(actor in occupants and occupants[actor] == origin and destination in zones
                    and frozenset((origin, destination)) in edges and prose(event.get('reason')),
                    f"{scene['id']}: event must move a present catalog character along a known connection with a reason")
            occupants[actor] = destination
        for transfer in scene.get('transfers', []):
            item, origin, recipient = (transfer[key] for key in ('item', 'from', 'to'))
            require(item in objects and objects[item] == origin and recipient in allowed_holders
                    and recipient != origin and prose(transfer.get('reason')),
                    f"{scene['id']}: {item} must be transferred by its current holder")
            origin_zone = occupants.get(origin, origin)
            target_zone = occupants.get(recipient, recipient)
            require(origin_zone == target_zone, f"{scene['id']}: {item} transfer requires the same zone")
            objects[item] = recipient
        for item, expected_holder in scene.get('required_custody', {}).items():
            require(objects.get(item) == expected_holder, f"{scene['id']}: {item} must be with {expected_holder}")
        visible_zones, visibility = scene.get('visible_zones'), scene.get('visibility')
        require(isinstance(visible_zones, list) and len(visible_zones) == len(set(visible_zones))
                and all(z in zones for z in visible_zones), f"{scene['id']}: invalid visible zones")
        require(isinstance(visibility, dict), f"{scene['id']}: visibility must be an object")
        expected = {actor for actor, zone in occupants.items() if zone in visible_zones}
        require(set(visibility) == expected,
                f"{scene['id']}: visibility must account for every occupant in visible zones: {', '.join(sorted(expected))}")
        for actor, record in visibility.items():
            require(isinstance(record, dict) and record.get('status') in ('visible', 'occluded')
                    and prose(record.get('evidence')), f"{scene['id']}: {actor} needs visible/occluded status and evidence")
        result.append({'scene': scene['id'], 'before': before, 'occupancy': dict(occupants),
                       'movements': events, 'visibility': visibility, 'custody_before': custody_before,
                       'custody_after': dict(objects), 'transfers': scene.get('transfers', [])})
    if expected_scene_ids is not None:
        require([scene['scene'] for scene in result] == expected_scene_ids,
                'World scenes must match the scene plan exactly and in order')
    return result


def check_world(args):
    catalog = load(args.project / 'character-catalog.json')
    entries = catalog.get('entries') if isinstance(catalog, dict) else None
    require(isinstance(entries, dict), 'Character catalog needs entries')
    plan = load(args.project / 'scenes.json')
    pages = plan.get('pages') if isinstance(plan, dict) else None
    require(isinstance(pages, list) and pages and all(isinstance(p, dict) and identifier(p.get('id')) for p in pages),
            'Scene plan needs ordered page IDs')
    snapshots = validate_world(load(args.project / 'world.json'), set(entries), [p['id'] for p in pages])
    print(json.dumps({'status': 'timeline declarations valid; not yet used by staging; visual review still required', 'scenes': snapshots},
                     ensure_ascii=False, indent=2))


def register(subparsers):
    p = subparsers.add_parser("check-world", help="Check declared character occupancy and movement across scenes")
    p.add_argument("project", type=Path)
    p.set_defaults(func=check_world)
