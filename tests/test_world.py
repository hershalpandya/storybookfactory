import copy

import pytest

from storybook_toolkit.store import ProjectError
from storybook_toolkit.world import validate_world


def sample():
    return {
        'format_version': 1,
        'zones': {'hall': 'Inside hall', 'threshold': 'At doorway', 'yard': 'Outside'},
        'connections': [['hall', 'threshold'], ['threshold', 'yard']],
        'initial_occupancy': {'character-a': 'hall', 'character-b': 'hall'},
        'scenes': [
            {'id': 'call', 'visible_zones': ['hall'], 'visibility': {
                'character-a': {'status': 'visible', 'evidence': 'At the side of the aisle'},
                'character-b': {'status': 'occluded', 'evidence': 'Behind the hay'}}},
            {'id': 'exit', 'events': [{'character': 'character-a', 'from': 'hall',
                                      'to': 'threshold', 'reason': 'Hen offers help'}],
             'visible_zones': ['hall', 'threshold'], 'visibility': {
                 'character-a': {'status': 'visible', 'evidence': 'Crossing the doorway'},
                 'character-b': {'status': 'visible', 'evidence': 'Still inside'}}},
        ],
    }


def test_timeline_preserves_unmoved_characters_and_catalog_identity():
    result = validate_world(sample(), {'character-a', 'character-b'})
    assert result[1]['occupancy'] == {'character-a': 'threshold', 'character-b': 'hall'}
    bad = sample()
    bad['scenes'][1]['events'][0]['character'] = 'hen-2'
    with pytest.raises(ProjectError, match='present catalog character'):
        validate_world(bad, {'character-a', 'hen-2', 'character-b'})


def test_missing_visible_occupant_and_impossible_transition_fail():
    bad = sample()
    del bad['scenes'][0]['visibility']['character-b']
    with pytest.raises(ProjectError, match='every occupant'):
        validate_world(bad, {'character-a', 'character-b'})
    bad = sample()
    bad['scenes'][1]['events'][0]['to'] = 'yard'
    with pytest.raises(ProjectError, match='known connection'):
        validate_world(bad, {'character-a', 'character-b'})


def test_camera_excludes_zone_without_erasing_occupant():
    world = copy.deepcopy(sample())
    world['scenes'][1]['visible_zones'] = ['threshold']
    del world['scenes'][1]['visibility']['character-b']
    result = validate_world(world, {'character-a', 'character-b'})
    assert result[1]['occupancy']['character-b'] == 'hall'


def test_world_must_cover_the_scene_plan_in_order():
    with pytest.raises(ProjectError, match='exactly and in order'):
        validate_world(sample(), {'character-a', 'character-b'}, ['call', 'missing', 'exit'])
    with pytest.raises(ProjectError, match='exactly and in order'):
        validate_world(sample(), {'character-a', 'character-b'}, ['exit', 'call'])
    assert len(validate_world(sample(), {'character-a', 'character-b'}, ['call', 'exit'])) == 2
