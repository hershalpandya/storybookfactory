# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Inspect decoded print pixels independently of PNG metadata and visual claims."""

from io import BytesIO
import struct
import zlib

from PIL import Image

from .store import ProjectError, require, sha256


def inspect_png(content, target_pt=None, *, check_resolution=True):
    try:
        with Image.open(BytesIO(content), formats=["PNG"]) as source:
            require(source.width * source.height <= 24_000_000, "PNG exceeds the decoded pixel limit")
            require(getattr(source, "n_frames", 1) == 1, "Use a single-frame PNG")
            rgba = source.convert("RGBA")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ProjectError(f"Cannot decode PNG: {exc}") from exc
    width, height = rgba.size
    if check_resolution and target_pt:
        effective_dpi = max(width * 72 / target_pt[0], height * 72 / target_pt[1])
        require(min(width, height) >= 128 and effective_dpi >= 120,
                f"PNG is undersized for its print slot ({width} × {height}, {effective_dpi:.0f} dpi)")
    elif check_resolution:
        require(min(width, height) >= 256, f"Reference PNG is undersized ({width} × {height})")
    paper = Image.new("RGB", rgba.size, "white")
    paper.paste(rgba, mask=rgba.getchannel("A"))
    require(any(lo != hi for lo, hi in paper.getextrema()), "PNG is blank or a uniform colour on white paper")
    return sha256(struct.pack(">II", width, height) + paper.tobytes())


def validate_png(content):
    if not content.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ProjectError('Asset must be a PNG file')
    pos, chunks, compressed = 8, [], bytearray()
    header = None
    try:
        while pos < len(content):
            length = struct.unpack_from('>I', content, pos)[0]
            kind = content[pos + 4:pos + 8]
            end = pos + 12 + length
            if end > len(content) or len(kind) != 4:
                raise ValueError('truncated chunk')
            payload = content[pos + 8:pos + 8 + length]
            crc = struct.unpack_from('>I', content, pos + 8 + length)[0]
            if zlib.crc32(kind + payload) != crc:
                raise ValueError('invalid chunk checksum')
            chunks.append(kind)
            if kind == b'IHDR':
                if length != 13 or header is not None:
                    raise ValueError('invalid header')
                header = struct.unpack('>IIBBBBB', payload)
                width, height, depth, colour, compression, filtering, interlace = header
                allowed = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
                if not width or not height or colour not in allowed or depth not in allowed[colour] or compression or filtering or interlace not in (0, 1):
                    raise ValueError('invalid image header')
            if kind == b'IDAT':
                compressed.extend(payload)
            pos = end
            if kind == b'IEND':
                break
        if not chunks or chunks[0] != b'IHDR' or chunks[-1] != b'IEND' or pos != len(content) or not compressed:
            raise ValueError('missing required chunks or trailing data')
        if chunks.count(b'IHDR') != 1 or chunks.count(b'IEND') != 1 or (colour == 3 and b'PLTE' not in chunks):
            raise ValueError('invalid required chunks')
        channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[colour]
        passes = [(0, 0, 1, 1)] if not interlace else [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]
        rows = []
        for x, y, dx, dy in passes:
            w = max(0, (width - x + dx - 1) // dx)
            h = max(0, (height - y + dy - 1) // dy)
            if w and h:
                rows.append(((w * channels * depth + 7) // 8 + 1, h))
        size = sum(row * count for row, count in rows)
        if size > 256 * 1024 * 1024:
            raise ValueError('image data exceeds validation limit')
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(compressed, size + 1)
        if len(pixels) != size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('invalid image data length or stream')
        offset = 0
        for row, count in rows:
            for _ in range(count):
                if pixels[offset] > 4:
                    raise ValueError('invalid PNG row filter')
                offset += row
    except (ValueError, struct.error, zlib.error) as exc:
        raise ProjectError(f'Invalid PNG: {exc}') from exc
