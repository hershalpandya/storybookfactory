# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
import hashlib
import json
import struct
import zlib
from types import SimpleNamespace

import pytest

from storybook_toolkit import scenes
from support import png


SERIES = {'entities': [{'id': 'pip', 'name': 'Pip', 'visible_in_v10': 'A mouse with a striped shoulder badge.',
                         'uncertainty': '', 'reference_ids': ['pip-side']}],
          'references': [{'id': 'pip-side', 'path': 'pip-side.png', 'use': 'Side view of Pip.'}]}


def test_legacy_plans_need_a_project_series_manifest(tmp_path, monkeypatch):
    monkeypatch.delenv('STORYBOOK_SERIES_MANIFEST', raising=False)
    with pytest.raises(scenes.ProjectError, match='series manifest'):
        scenes.series_manifest(tmp_path)
    (tmp_path / 'elsewhere.json').write_text(json.dumps(SERIES), encoding='utf8')
    monkeypatch.setenv('STORYBOOK_SERIES_MANIFEST', str(tmp_path / 'elsewhere.json'))
    assert scenes.series_manifest(tmp_path)[1]['entities'][0]['id'] == 'pip'


@pytest.mark.parametrize('indices,duplicate,message', [
    ([0, 0], False, 'exactly once and in order'), ([1, 0], False, 'exactly once and in order'),
    ([0], False, 'exactly once and in order'), ([0, 1], True, 'distinct scene request')])
def test_plan_rejects_missing_repeated_or_reordered_passages_and_requests(tmp_path, monkeypatch, indices, duplicate,
                                                                          message):
    monkeypatch.setattr(scenes, 'check_adaptation', lambda args: None)
    def write(name, value):
        (tmp_path / name).write_text(json.dumps(value), encoding='utf8')
    write('project.json', {'format_version': 1, 'transcripts': [], 'adapted_story': {'sha256': 'approved'}})
    write('series-manifest.json', SERIES)
    write('adapted-story.json', {'passages': [{'text': 'First'}, {'text': 'Second'}]})
    pages = [{'id': str(i), 'passages': [index], 'scene': 'Same' if duplicate else f'Scene {i}',
              'colouring': f'Outline {i}', 'entities': []} for i, index in enumerate(indices)]
    write('scenes.json', {'format_version': 1, 'adaptation_sha256': 'approved', 'pages': pages})
    with pytest.raises(scenes.ProjectError, match=message):
        scenes.validated_plan(tmp_path)


def test_scene_handoff_brief_and_asset_registry_follow_the_plan(tmp_path, monkeypatch, capsys):
    # Exercise scene handling independently of the upstream approval workflow.
    monkeypatch.setattr(scenes, 'check_adaptation', lambda args: None)
    def write(name, value):
        (tmp_path / name).write_text(json.dumps(value), encoding='utf8')
    write('project.json', {'format_version': 1, 'transcripts': [], 'adapted_story': {'sha256': 'approved'}})
    write('series-manifest.json', SERIES)
    write('adapted-story.json', {'passages': [{'text': 'Kite'}, {'text': 'Rain'}]})
    plan = {'format_version': 1, 'adaptation_sha256': 'approved', 'pages': [
        {'id': 'one', 'passages': [0], 'scene': 'A kite', 'colouring': 'A kite outline', 'entities': ['pip'],
         'visual_brief': {'action': 'Pip holds the kite', 'checks': 'Badge stays at shoulder'}},
        {'id': 'two', 'passages': [1], 'scene': 'Rain', 'colouring': 'A cloud outline', 'entities': []}]}
    write('scenes.json', plan)
    monkeypatch.setenv('STORYBOOK_REFERENCE_DIR', str(tmp_path / 'missing'))
    args = SimpleNamespace(project=tmp_path)
    scenes.handoff(args)
    output = capsys.readouterr().out
    assert '[MISSING]' in output
    assert 'Visible action: Pip holds the kite' in output
    assert 'Acceptance checks: Badge stays at shoulder' in output
    plan['pages'][0]['visual_brief'] = {'acton': 'typo'}
    write('scenes.json', plan)
    with pytest.raises(scenes.ProjectError, match='visual_brief'):
        scenes.validated_plan(tmp_path)
    plan['pages'][0]['visual_brief'] = {'action': 'Pip holds the kite', 'checks': 'Badge stays at shoulder'}
    write('scenes.json', plan)
    scenes.check_assets(args)
    assert capsys.readouterr().out.count('PENDING — obtain') == 4
    for i, (page, kind) in enumerate((('one', 'illustration'), ('one', 'colouring'), ('two', 'illustration'), ('two', 'colouring'))):
        path = tmp_path / f'{i}.png'
        path.write_bytes(png(i))
        scenes.register_asset(SimpleNamespace(project=tmp_path, page=page, kind=kind, file=path))
    scenes.check_assets(args)
    assert capsys.readouterr().out.count('human visual review PENDING') == 4
    plan['pages'][0]['scene'] = 'Changed'
    write('scenes.json', plan)
    with pytest.raises(scenes.ProjectError, match='scene plan changed'):
        scenes.check_assets(args)


def chunk(name, payload):
    return struct.pack('>I', len(payload)) + name + payload + struct.pack('>I', zlib.crc32(name + payload))


def with_pixels(raw):
    header = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    return b'\x89PNG\r\n\x1a\n' + header + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


@pytest.mark.parametrize('image,message', [
    (png(1)[:-2], 'truncated chunk'),
    (with_pixels(b''), 'invalid image data length'),
    (with_pixels(b'\x05\x00\x00\x00'), 'invalid PNG row filter'),
], ids=['truncated', 'empty-pixels', 'bad-filter'])
def test_png_rejects_invalid_files(image, message):
    with pytest.raises(scenes.ProjectError, match=message):
        scenes.validate_png(image)


def test_check_assets_rejects_duplicate_bytes_in_edited_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(scenes, 'validated_plan', lambda root: {
        'adaptation_sha256': 'approved', 'pages': [{'id': 'one'}]})
    (tmp_path / 'scenes.json').write_text('{}', encoding='utf8')
    content = png(1)
    sha = hashlib.sha256(content).hexdigest()
    directory = tmp_path / 'assets'
    directory.mkdir()
    (directory / f'{sha}.png').write_bytes(content)
    plan_hash = hashlib.sha256(b'{}').hexdigest()
    entry = {'page': 'one', 'file': f'assets/{sha}.png', 'sha256': sha,
             'plan_sha256': plan_hash, 'adaptation_sha256': 'approved'}
    (tmp_path / 'assets.json').write_text(json.dumps({'format_version': 1, 'assets': [
        dict(entry, kind='illustration'), dict(entry, kind='colouring')]}), encoding='utf8')
    with pytest.raises(scenes.ProjectError, match='distinct asset'):
        scenes.check_assets(SimpleNamespace(project=tmp_path))
