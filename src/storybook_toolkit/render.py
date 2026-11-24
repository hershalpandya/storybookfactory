"""Book geometry, typesetting and PDF drawing shared by editions and scene-plan books.

The scene-plan commands (layout-preflight, render) live in legacy/book.py and are re-exported at the end.
"""
from importlib import resources
import re

from PIL import Image, ImageDraw, ImageFont, features
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .store import ProjectError, load

W, H = 297 * 72 / 25.4, 210 * 72 / 25.4
MM = 72 / 25.4
# Package data is a plain file in every supported install (wheel or editable), so the Traversable is a Path.
FONT = resources.files('storybook_toolkit').joinpath('fonts', 'Marelle2-Regular.ttf')
SCALE = 5
SAFE = 8 * MM
SAFE_SCALE = min((W - 2 * SAFE) / W, (H - 2 * SAFE) / H)
# Bound print: content shrinks and moves away from the binding so sewn pages can fold open.
BOUND_SCALE = 0.92
BOUND_SHIFT = 34 * MM - BOUND_SCALE * 50  # front illustration edge (x=50 pt) lands 34 mm from the binding
BOUND_MARK = 12 * MM
# Typesetting shared by scene-plan renders and editions (points unless named otherwise).
TEXT_WIDTH_PT = 707
TEXT_SIZE = 15
LINE_PT = 24
GAP_PT = 6
MAX_TEXT_PT = 290  # text height must stay under this
READING_GREY, SAFE_GREY = 145, 125  # reading-mark greys: screen and printer-safe variants
TITLE_SIZES = (("title", 32), ("author", 18), ("dedication", 18), ("date", 14), ("back_title", 30))


def _font(path, size):
    if not features.check('raqm'):
        raise ProjectError('Pillow must be built with libraqm for shaped text')
    try:
        return ImageFont.truetype(str(path), round(size * SCALE), layout_engine=ImageFont.Layout.RAQM)
    except OSError as exc:
        raise ProjectError(f'Cannot load font {path}: {exc}') from exc


def _lines(text, font, width, marks=(), *, keep_french_punctuation=False):
    # Preserve offsets for per-occurrence marks, including line breaks.
    result = []
    for paragraph in re.finditer(r'[^\n]*', text):
        start, end = paragraph.span()
        if start == end:
            if start < len(text):
                result.append((start, start))
            continue
        line_start = None
        last_end = None
        groups = []
        for word in re.finditer(r'\S+', text[start:end]):
            a, b = start + word.start(), start + word.end()
            # A reviewed span or liaison may join consecutive words into one wrap unit.
            join_punctuation = (keep_french_punctuation and groups
                                and (text[a] in "!?;:»" or text[groups[-1][1]-1] == "«"))
            if groups and (join_punctuation or any(mark["start"] < a and
                              (mark["target"] >= a if mark["kind"] == "liaison" else mark["end"] > a)
                              for mark in marks)):
                groups[-1] = (groups[-1][0], b)
            else:
                groups.append((a, b))
        for a, b in groups:
            if font.getlength(text[a:b]) > width * SCALE:
                raise ProjectError(f'Text overflow: word or reviewed span at offset {a} exceeds line width')
            if line_start is not None and font.getlength(text[line_start:b]) > width * SCALE:
                result.append((line_start, last_end))
                line_start = None
            if line_start is None:
                line_start = a
            last_end = b
        if line_start is not None:
            result.append((line_start, last_end))
    return result


def _line_image(text, marks, start, end, font, mark_grey=145):
    line = text[start:end]
    bbox = font.getbbox(line, anchor='ls')
    pad = 25
    img = Image.new('RGBA', (max(1, bbox[2]-bbox[0]+2*pad), max(1, bbox[3]-bbox[1]+2*pad+35)), (255,255,255,0))
    origin = (pad-bbox[0], pad-bbox[1])
    ImageDraw.Draw(img).text(origin, line, font=font, anchor='ls', fill=(48,45,54,255))
    grey = Image.new('RGBA', img.size, (255,255,255,0))
    ImageDraw.Draw(grey).text(origin, line, font=font, anchor='ls', fill=(mark_grey,mark_grey,mark_grey,255))
    for mark in marks:
        a, b = mark['start'], mark['end']
        if a < end and b > end:
            raise ProjectError('Text overflow: a reviewed annotation crosses a line')
        if mark['kind'] == 'liaison' and a < end and mark['target'] >= end:
            raise ProjectError('Text overflow: a reviewed liaison crosses a line; adjust page text or width')
        if a >= start and b <= end:
            left = origin[0] + font.getlength(text[start:a])
            right = origin[0] + font.getlength(text[start:b])
            if mark['kind'] == 'silent':
                mask = Image.new('L', img.size)
                ImageDraw.Draw(mask).rectangle((left, 0, right, img.height), fill=255)
                img.paste(grey, (0,0), mask)
            elif mark['kind'] == 'liaison':
                target = origin[0] + font.getlength(text[start:mark['target']+1])
                # Measure the linked characters, not the whole line: a descender
                # elsewhere on the line must not push this arc out of place.
                descent = max(0, font.getbbox(text[a:mark['target']+1], anchor='ls')[3])
                top = origin[1] + descent + 3
                ImageDraw.Draw(img).arc((left, top, target, top+15), 10, 170, fill=(mark_grey,mark_grey,mark_grey,255), width=3)
    return img


def _draw_line(pdf, img, x, top):
    pdf.drawImage(ImageReader(img), x, top-img.height/SCALE, width=img.width/SCALE, height=img.height/SCALE, mask='auto')


def _centered_image(text, size, font_path):
    img = _line_image(text, [], 0, len(text), _font(font_path, size))
    if img.width/SCALE > W-100:
        raise ProjectError('Cover/back metadata overflow: text exceeds page width')
    return img


def _center(pdf, text, y, size, font_path):
    img = _centered_image(text, size, font_path)
    _draw_line(pdf, img, (W-img.width/SCALE)/2, y)


def _picture(pdf, path, box):
    try:
        with Image.open(path) as image:
            image.load()
            iw, ih = image.size
            image = image.convert('RGBA')
            x, y, w, h = box
            scale = min(w/iw, h/ih)
            ww, hh = iw*scale, ih*scale
            pdf.drawImage(ImageReader(image), x+(w-ww)/2, y+(h-hh)/2, ww, hh, mask='auto')
    except (OSError, ValueError) as exc:
        raise ProjectError(f'Cannot decode image {path}: {exc}') from exc


def artwork_boxes(height, back=False):
    return {
        "illustration": (190 if back else 50, 63, 575 if back else 600, min(390, H - 48 - height - 63)),
        "colouring": (38 if back else W - 38 - 145.6, 60, 145.6, 106.6),
    }


COVER_BOXES = {"front": (115, 135, W - 230, 365), "back": (155, 80, W - 310, 415)}


def book_metadata(path):
    metadata = load(path)
    if not isinstance(metadata, dict) or not isinstance(metadata.get('title'), str) or not metadata['title'].strip():
        raise ProjectError('Metadata requires a nonempty title')
    for key in ('author', 'dedication', 'date', 'back_title', 'cover_image', 'back_image'):
        if key in metadata and not isinstance(metadata[key], str):
            raise ProjectError(f'Metadata {key} must be a string')
    return metadata


def check_titles(metadata, font_path):
    """Every cover and back-page metadata line must fit the page width."""
    for key, size in TITLE_SIZES:
        if metadata.get(key):
            _centered_image(metadata[key], size, font_path)


def typeset(pages, font_path, *, keep_french_punctuation=False, overflow="{page}: text overflow"):
    """Wrap and render page text. pages is a list of (page_id, blocks), blocks a list of (text, annotations);
    blocks on one page are separated by a gap line. Returns, per page, (lines, height, spans per block), where
    each line is a (reading, printer-safe) image pair or None for a gap."""
    font = _font(font_path, TEXT_SIZE)
    result = []
    for page_id, blocks in pages:
        lines, spans = [], []
        for text, marks in blocks:
            block = _lines(text, font, TEXT_WIDTH_PT, marks, keep_french_punctuation=keep_french_punctuation)
            spans.append(block)
            lines.extend(tuple(_line_image(text, marks, a, b, font, grey) for grey in (READING_GREY, SAFE_GREY))
                         if a != b else None for a, b in block)
            lines.append(None)
        if lines:
            lines.pop()
        height = sum(GAP_PT if line is None else LINE_PT for line in lines)
        if height >= MAX_TEXT_PT:
            raise ProjectError(overflow.format(page=page_id, height=height, limit=MAX_TEXT_PT))
        result.append((lines, height, spans))
    return result


MODES = ('reading', 'single-sided', 'duplex', 'single-sided-printer-safe', 'duplex-printer-safe', 'duplex-bound')


def render_book(out, metadata, font_path, prepared, assets, cover_art, modes=MODES):
    for mode in modes:
        bound = mode.endswith('-bound')
        safe = mode.endswith('-printer-safe')
        duplex = mode.startswith('duplex')
        scale = BOUND_SCALE if bound else SAFE_SCALE
        offset_x = (W - W * SAFE_SCALE) / 2
        offset_y = (H - H * scale) / 2
        pdf = canvas.Canvas(str(out / f'{mode}.pdf'), pagesize=(W,H), pageCompression=1)
        pdf.setTitle(metadata['title'])
        pdf.setAuthor(metadata.get('author',''))
        def begin():
            if safe:
                pdf.saveState()
                pdf.translate(offset_x, offset_y)
                pdf.scale(SAFE_SCALE, SAFE_SCALE)
            elif bound:
                # Fronts bind on the left; duplex backs bind on the right, so mirror the shift.
                back_side = pdf.getPageNumber() % 2 == 0
                pdf.saveState()
                pdf.translate(W - BOUND_SHIFT - BOUND_SCALE * W if back_side else BOUND_SHIFT, offset_y)
                pdf.scale(BOUND_SCALE, BOUND_SCALE)
        def finish():
            if safe or bound:
                pdf.restoreState()
            if mode != 'reading':
                edge = BOUND_MARK if bound else (10.5 if safe else 9) * MM
                x = W-edge if duplex and pdf.getPageNumber() % 2 == 0 else edge
                pdf.setStrokeColorRGB(.35,.35,.35)
                for fraction in (.22,.5,.78):
                    y = offset_y + H*fraction*scale if safe or bound else H*fraction
                    pdf.circle(x,y,1.6,stroke=1,fill=0)
            pdf.showPage()
        begin()
        _center(pdf, metadata['title'], H-30, 32, font_path)
        if 'front' in cover_art: _picture(pdf, cover_art['front'], COVER_BOXES['front'])
        for key, y, size in (('author',125,18),('dedication',95,18),('date',65,14)):
            if metadata.get(key): _center(pdf, metadata[key], y, size, font_path)
        finish()
        for number, (page, lines, height) in enumerate(prepared, 1):
            begin()
            back = duplex and pdf.getPageNumber() % 2 == 0
            # Reserve a separate bottom corner for colouring; scene never overlays text.
            for kind, box in artwork_boxes(height, back).items():
                _picture(pdf, assets[(page['id'], kind)], box)
            y = H-38
            for line in lines:
                if line is None: y -= 6
                else:
                    _draw_line(pdf, line[1 if safe or bound else 0], 62, y)
                    y -= 24
            pdf.setFont('Helvetica', 12)
            pdf.drawCentredString(W/2, 40, str(number))
            finish()
        if duplex and (len(prepared)+2) % 2:
            begin()
            finish()  # Explicit blank reverse immediately before the back cover.
        begin()
        if metadata.get('back_title'): _center(pdf, metadata['back_title'], H-60, 30, font_path)
        if 'back' in cover_art: _picture(pdf, cover_art['back'], COVER_BOXES['back'])
        finish()
        pdf.save()


# Scene-plan book commands, kept importable from their former home. Resolved on first use because
# legacy/book.py imports this module.
LEGACY_NAMES = {"approved_layout", "layout_preflight", "pagination_key", "prepare_text", "render"}


def __getattr__(name):
    if name in LEGACY_NAMES:
        from .legacy import book
        return getattr(book, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
