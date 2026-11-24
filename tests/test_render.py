# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
import json
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas

from storybook_toolkit import render, scenes
from storybook_toolkit.store import ProjectError


def test_geometry_and_duplex_padding(tmp_path, monkeypatch):
    monkeypatch.setattr(scenes, 'check_adaptation', lambda args: None)
    def write(name, data):
        (tmp_path / name).write_text(json.dumps(data), encoding='utf8')
    write('project.json', {'format_version': 1, 'transcripts': [], 'adapted_story': {'sha256': 'approved'}})
    write('adapted-story.json', {'passages': [{'text': 'Les amis.', 'annotations': [{'kind': 'liaison', 'start': 2, 'end': 3, 'target': 4}]}]})
    write('scenes.json', {'format_version': 1, 'adaptation_sha256': 'approved', 'pages': [{'id':'one', 'passages':[0], 'scene':'A kite', 'colouring':'A kite outline', 'entities':[]}]})
    for i, kind in enumerate(('illustration', 'colouring')):
        p = tmp_path / f'{kind}.png'
        Image.new('RGB', (30, 20), (i * 120, 100, 80)).save(p)
        scenes.register_asset(SimpleNamespace(project=tmp_path, page='one', kind=kind, file=p))
    write('metadata.json', {'title':'A kite', 'author':'A storyteller', 'back_title':'The end'})
    counts = []
    circles = []
    real_canvas = canvas.Canvas
    class RecordingCanvas(real_canvas):
        def circle(self, x, y, *args, **kwargs):
            circles.append((self.getPageNumber(), x, y))
            return super().circle(x, y, *args, **kwargs)
        def save(self):
            counts.append(self.getPageNumber()-1)
            return super().save()
    monkeypatch.setattr(render.canvas, 'Canvas', RecordingCanvas)
    out = tmp_path / 'output'
    render.render(SimpleNamespace(project=tmp_path, metadata=tmp_path/'metadata.json', output=out, font=None))
    assert counts == [3, 3, 4, 3, 4, 4]
    assert len(circles) == 54
    assert all(abs(x-9*render.MM) < 0.01 for _, x, _ in circles[:9])
    assert [round(circles[i][1], 2) for i in (9,12,15,18)] == [round(9*render.MM,2), round(render.W-9*render.MM,2), round(9*render.MM,2), round(render.W-9*render.MM,2)]
    safe_circles = circles[21:42]
    bound_circles = circles[42:]
    assert [round(safe_circles[i][1], 2) for i in (0, 3, 6)] == [round(10.5*render.MM, 2)] * 3
    assert [round(safe_circles[i][1], 2) for i in (9, 12, 15, 18)] == [round(10.5*render.MM, 2), round(render.W-10.5*render.MM, 2), round(10.5*render.MM, 2), round(render.W-10.5*render.MM, 2)]
    assert abs((render.H - render.H*render.SAFE_SCALE)/2 - 8*render.MM) < 1e-8
    assert (render.W - render.W*render.SAFE_SCALE)/2 >= 8*render.MM
    for page, x, y in safe_circles:
        assert min(x, render.W-x, y, render.H-y) - 1.6 >= 8*render.MM
    # Bound duplex: sewing marks 12 mm from the binding, mirrored on backs; content clears the fold.
    assert [round(bound_circles[i][1], 2) for i in (0, 3, 6, 9)] == [round(12*render.MM, 2), round(render.W-12*render.MM, 2), round(12*render.MM, 2), round(render.W-12*render.MM, 2)]
    s, a = render.BOUND_SCALE, render.BOUND_SHIFT
    assert render.W - (a + s*(render.W - 38)) >= 8*render.MM         # front colouring, outer edge
    back_shift = render.W - a - s*render.W
    assert render.W - (back_shift + s*(62 + 707)) >= 34*render.MM   # back text end, binding edge
    assert back_shift + s*38 >= 8*render.MM                         # back colouring, outer edge
    assert json.loads((out/'reviewed-text.json').read_text())['adaptation']['passages'][0]['text'] == 'Les amis.'
    assert all((out/f'{mode}.pdf').stat().st_size > 1000 for mode in render.MODES)


def test_overflow_and_missing_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(scenes, 'validated_plan', lambda root: {'pages': [{'id':'one', 'passages':[0]}]})
    with pytest.raises(ProjectError, match='Missing assets: one illustration'):
        render.render(SimpleNamespace(project=tmp_path, output=tmp_path/'out'))
    font = render._font(render.FONT, 15)
    with pytest.raises(ProjectError, match='overflow'):
        render._lines('W'*1000, font, 707)


def test_safe_reading_marks_are_darker():
    font = render._font(render.FONT, 15)
    text = 'Les amis'
    marks = [{'kind': 'silent', 'start': 2, 'end': 3}, {'kind': 'liaison', 'start': 2, 'end': 3, 'target': 4}]
    normal = render._line_image(text, marks, 0, len(text), font)
    safe = render._line_image(text, marks, 0, len(text), font, mark_grey=125)
    assert normal.size == safe.size
    assert (145, 145, 145, 255) in normal.get_flattened_data()
    assert (125, 125, 125, 255) in safe.get_flattened_data()
    assert (48, 45, 54, 255) in safe.get_flattened_data()


def arc_box(text, mark, monkeypatch):
    calls = []
    original = ImageDraw.ImageDraw.arc
    def capture(draw, box, *args, **kwargs):
        calls.append(box)
        return original(draw, box, *args, **kwargs)
    monkeypatch.setattr(ImageDraw.ImageDraw, 'arc', capture)
    render._line_image(text, [mark], 0, len(text), render._font(render.FONT, 15))
    monkeypatch.undo()
    assert len(calls) == 1
    return calls[0]


def test_liaison_arc_ignores_descenders_elsewhere_on_the_line(monkeypatch):
    mark = {'kind': 'liaison', 'start': 2, 'end': 3, 'target': 4}
    short = arc_box('Les amis', mark, monkeypatch)
    long = arc_box('Les amis jouent', mark, monkeypatch)
    assert short[1] == long[1] and short[3] - short[1] == 15


def test_layout_keeps_reviewed_liaison_together():
    font = render._font(render.FONT, 15)
    width = font.getlength("Les amis.") / render.SCALE
    text = "Je vois les amis."
    mark = {"kind": "liaison", "start": 10, "end": 11, "target": 12}
    assert [text[a:b] for a, b in render._lines(text, font, width, [mark])] == ["Je vois", "les amis."]


def test_french_closing_punctuation_stays_with_the_preceding_word():
    text = "Oui, au musée ! »"
    font = render._font(render.FONT, 15)
    width = font.getlength("musée ! »") / render.SCALE + 1
    spans = render._lines(text, font, width, keep_french_punctuation=True)
    assert [text[a:b] for a, b in spans] == ["Oui, au", "musée ! »"]


def test_typeset_separates_blocks_and_stops_before_the_text_limit():
    ((lines, height, spans),) = render.typeset([('one', [('Les amis.', []), ('Bonjour.', [])])], render.FONT)
    assert [line is None for line in lines] == [False, True, False]
    assert height == 2 * render.LINE_PT + render.GAP_PT and spans == [[(0, 9)], [(0, 8)]]
    reading, safe = lines[0]
    assert reading.size == safe.size
    many = [('long', [('Mot.', [])] * 12)]
    with pytest.raises(ProjectError, match='^Page long: text overflow'):
        render.typeset(many, render.FONT, overflow='Page {page}: text overflow ({height} pt)')
