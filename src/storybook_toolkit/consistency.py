"""Plan v2 consistency tools: drift gate, colouring metrics, cast and contact sheets, scorecard, next action.

All of these run locally and make no provider call.
"""

from collections import Counter, deque

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .store import require

WORK_WIDTH = 600
DRIFT_DELTA = 40
HOTSPOT_SHARE = 0.15


def parse_region(value):
    """A target region as fractions of width and height: x0,y0,x1,y1."""
    try:
        box = [float(part) for part in str(value).split(",")]
    except ValueError:
        box = []
    require(len(box) == 4 and 0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1,
            f"Region must be four fractions x0,y0,x1,y1 with x0<x1 and y0<y1: {value}")
    return box


def drift(before, after, regions, *, width=WORK_WIDTH, delta=DRIFT_DELTA, margin=0.02):
    """Share of pixels outside the target regions that changed by more than ``delta`` (0-255).

    Both images are resized to the same working size; a different aspect ratio fails rather than guessing an
    alignment. Regions are dilated by ``margin`` so shadows at the edge of an edited object do not count.
    """
    with Image.open(before) as a_image, Image.open(after) as b_image:
        a_ratio, b_ratio = a_image.width / a_image.height, b_image.width / b_image.height
        require(abs(a_ratio - b_ratio) < 0.02, "Images differ in aspect ratio; drift cannot be measured")
        height = round(width / a_ratio)
        a = a_image.convert("RGB").resize((width, height), Image.LANCZOS)
        b = b_image.convert("RGB").resize((width, height), Image.LANCZOS)
    diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > delta else 0)
    mask = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(mask)
    for x0, y0, x1, y1 in regions:
        draw.rectangle(((x0 - margin) * width, (y0 - margin) * height, (x1 + margin) * width,
                        (y1 + margin) * height), fill=0)
    outside = nonzero(mask)
    changed = nonzero(ImageChops.multiply(diff, mask))
    inside_total = width * height - outside
    inside_changed = nonzero(ImageChops.multiply(diff, ImageOps.invert(mask)))
    # Local changes can be missed by the page-wide fraction. Flag cells with concentrated drift.
    outside_diff = ImageChops.multiply(diff, mask)
    cell = max(8, width // 20)
    hotspots = []
    for x in range(0, width, cell):
        for y in range(0, height, cell):
            box = (x, y, min(width, x + cell), min(height, y + cell))
            area = (box[2] - box[0]) * (box[3] - box[1])
            share = nonzero(outside_diff.crop(box)) / area
            if share > HOTSPOT_SHARE:
                hotspots.append({"box": [round(box[0] / width, 3), round(box[1] / height, 3),
                                         round(box[2] / width, 3), round(box[3] / height, 3)],
                                 "changed": round(share, 3)})
    return {"outside_changed": round(changed / outside, 5) if outside else 0.0,
            "inside_changed": round(inside_changed / inside_total, 5) if inside_total else 0.0,
            "hotspots": hotspots, "work_size": [width, height], "delta": delta, "regions": regions}


def nonzero(image):
    return image.width * image.height - image.histogram()[0]


def edit_drift(root, attempt, limit):
    """Plan v2 P1 gate for one edit: compare the parent with the result outside the declared target."""
    from .edition import checked_path
    require(attempt.get("target_regions"), "This edit has no declared target region; drift cannot be measured")
    measured = drift(checked_path(root, attempt["ordered_inputs"][0]),
                     checked_path(root, {"file": attempt["file"], "sha256": attempt["image_sha256"]}),
                     attempt["target_regions"])
    measured["limit"] = limit
    measured["rejected"] = measured["outside_changed"] > limit or bool(measured["hotspots"])
    return measured


def colouring_metrics(path, width=1000):
    """Grey fill share and stroke width of a colouring outline, at a fixed working width."""
    with Image.open(path) as image:
        grey = ImageOps.grayscale(image.convert("RGB"))
        grey = grey.resize((width, round(width * image.height / image.width)), Image.LANCZOS)
    total = grey.width * grey.height
    # A grey fill or shading is a flat mid-tone area. Dense line work also averages to mid-tone
    # but has high local contrast, so count only mid-tone pixels in flat 5x5 neighbourhoods.
    contrast = ImageChops.subtract(grey.filter(ImageFilter.MaxFilter(5)), grey.filter(ImageFilter.MinFilter(5)))
    flat_mid = ImageChops.multiply(contrast.point(lambda v: 255 if v < 30 else 0),
                                   grey.point(lambda v: 255 if 70 < v < 190 else 0))
    mid = nonzero(flat_mid) / total
    ink = grey.point(lambda v: 255 if v < 128 else 0)
    ink_count = nonzero(ink)
    width_px, current = 0, ink
    while ink_count and width_px < 20:
        current = current.filter(ImageFilter.MinFilter(3))
        remaining = nonzero(current)
        width_px += 2
        if remaining < 0.2 * ink_count:
            break
    return {"grey_share": round(mid, 4), "ink_share": round(ink_count / total, 4), "stroke_px": width_px}


def cast_sheet(images, target, height=520, gap=40):
    """Place clean subject images left to right on white, trimmed to their content; no labels."""
    tiles = []
    for path, scale in images:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
        box = ImageOps.invert(rgb.convert("L")).point(lambda v: 255 if v > 18 else 0).getbbox() or (0, 0, *rgb.size)
        tile = rgb.crop(box)
        h = max(40, round(height * scale))
        tiles.append(tile.resize((max(1, round(tile.width * h / tile.height)), h), Image.LANCZOS))
    width = sum(t.width for t in tiles) + gap * (len(tiles) + 1)
    sheet = Image.new("RGB", (width, height + 2 * gap), "white")
    x = gap
    for tile in tiles:
        sheet.paste(tile, (x, gap + height - tile.height))
        x += tile.width + gap
    sheet.save(target)
    return target


def contact_sheet(items, target, *, tile=(600, 402), columns=4):
    """Grid of (label, path) thumbnails for book-level review."""
    w, h = tile
    rows = max(1, (len(items) + columns - 1) // columns)
    sheet = Image.new("RGB", (columns * w, rows * (h + 26)), "white")
    draw = ImageDraw.Draw(sheet)
    for index, (label, path) in enumerate(items):
        x, y = (index % columns) * w, (index // columns) * (h + 26)
        if path:
            with Image.open(path) as image:
                thumb = image.convert("RGB")
            thumb.thumbnail((w - 6, h - 6))
            sheet.paste(thumb, (x + 3, y + 3))
        else:
            draw.rectangle((x + 3, y + 3, x + w - 3, y + h - 3), outline="#a53232", width=3)
        draw.text((x + 6, y + h + 6), label, fill="black")
    sheet.save(target, quality=85)
    return target


def scorecard(record, assigned_slots, issues=None):
    """Book-level KPIs from one Gemini journal and an optional issue ledger."""
    from .generation import cost_estimate
    attempts = list(record.get("attempts", {}).values())
    by_slot = {}
    for attempt in attempts:
        by_slot.setdefault(attempt["slot"], []).append(attempt)
    page_slots = {s: a for s, a in by_slot.items() if not s.endswith("/profile")}
    first_pass = sum(1 for group in page_slots.values()
                     if next((a for a in group if a["status"] == "captured"), {}).get("quality") == "pass")
    cost = sum(cost_estimate(a) for a in attempts)
    assigned = max(1, len(assigned_slots))
    result = {
        "submissions": len(attempts),
        "profile_calls": sum(a["kind"] == "profile" for a in attempts),
        "page_calls": sum(a["kind"] != "profile" for a in attempts),
        "targeted_edits": sum(bool(a.get("parent")) for a in attempts),
        "slots_generated": len(page_slots),
        "first_delivered_image_passes": first_pass,
        "quality": dict(Counter(str(a.get("quality")) for a in attempts if a["status"] == "captured")),
        "drift_rejects": sum(1 for a in attempts if (a.get("drift") or {}).get("rejected")),
        "cost_estimate_usd": round(cost, 3),
        "calls_per_assigned_slot": round(len(attempts) / assigned, 2),
        "cost_per_assigned_slot_usd": round(cost / assigned, 3),
        "assigned_slots": len(assigned_slots),
        "model_versions": sorted({str(a.get("model_version")) for a in attempts if a.get("model_version")}),
        "review_seconds": sum(a.get("review_seconds") or 0 for a in attempts),
        "owner_resumptions": sum(not r.get("agent") for r in record.get("resumptions", [])),
        "agent_recoveries": sum(bool(r.get("agent")) for r in record.get("resumptions", [])),
    }
    if issues is not None:
        result["issues"] = {"total": len(issues),
                            "by_type": dict(Counter(i.get("type", "unknown") for i in issues)),
                            "escaped": sum(bool(i.get("escaped")) for i in issues)}
    return result


def next_action(project, manifest, record, reviews, packets):
    """The single next step for an agent following the edition, in generation-policy order."""
    from .edition import art_dependency, review_for
    slots = (manifest.get("generation") or {}).get("slots", [])
    attempts = list(record.get("attempts", {}).items())
    if record.get("paused"):
        return {"action": "resolve-pause", "detail": record["paused"],
                "command": f"storybook edition gemini-resume {project} --owner NAME --evidence TEXT"}
    for ident, attempt in attempts:
        if attempt["status"] == "captured" and attempt.get("quality") is None:
            return {"action": "review-capture", "slot": attempt["slot"], "attempt": ident,
                    "command": f"storybook edition gemini-quality {project} {ident} pass|localized|unusable "
                               "--reviewer NAME --seconds S --evidence TEXT"}
    for slot in slots:
        if slot.endswith("/profile"):
            continue
        packet = packets.get(slot)
        if packet is None:
            continue
        mine = [(i, a) for i, a in attempts if a["slot"] == slot]
        latest = mine[-1][1] if mine else None
        approved = review_for(reviews, slot, art_dependency(packet))
        if packet.get("image") and approved and approved["decision"] == "approved":
            continue
        if latest and latest.get("quality") == "pass" and not packet.get("image"):
            return {"action": "assign", "slot": slot, "attempt": mine[-1][0],
                    "command": "storybook edition revise PROJECT assign.json (op assign with attempt)"}
        if packet.get("image"):
            return {"action": "visual-review", "slot": slot,
                    "command": f"storybook edition review {project} {slot} --role visual ..."}
        if latest and latest.get("quality") == "localized" and not latest.get("parent"):
            return {"action": "targeted-edit", "slot": slot, "attempt": mine[-1][0],
                    "command": f"storybook edition gemini {project} {slot} --parent {mine[-1][0]} --edit TEXT --region x0,y0,x1,y1"}
        if latest and latest.get("quality") in ("unusable", "localized"):
            return {"action": "restage", "slot": slot,
                    "detail": "Two tries on this slot failed: check the references before rewording the brief"}
        return {"action": "generate", "slot": slot,
                "command": f"storybook edition gemini {project} {slot} --dry-run, then director review, then dispatch"}
    return {"action": "book-sweep",
            "command": f"storybook edition sheets {project} OUT.jpg; storybook edition check {project}; "
                       "owner thumbnail checkpoint"}



# --- Batched colouring sheets -------------------------------------------------------------------------------
# Split a sheet of colouring outlines into individual elements.
# These helpers cut such a sheet into one page image per subject, locally.

def ink_boxes(image, k=4):
    """Bounding boxes of ink components, found at 1/k scale and returned in full-resolution pixels."""
    W, H = image.size
    mask = ImageOps.invert(image.convert("L").resize((W // k, H // k))).point(lambda v: 255 if v > 60 else 0)
    w, h = mask.size
    px, seen, found = mask.load(), bytearray(w * h), []
    for x in range(w):
        for y in range(h):
            if px[x, y] and not seen[y * w + x]:
                queue, seen[y * w + x] = deque([(x, y)]), 1
                x0, y0, x1, y1 = x, y, x, y
                while queue:
                    a, b = queue.popleft()
                    x0, y0, x1, y1 = min(x0, a), min(y0, b), max(x1, a), max(y1, b)
                    for cx in (a - 1, a, a + 1):
                        for cy in (b - 1, b, b + 1):
                            if 0 <= cx < w and 0 <= cy < h and px[cx, cy] and not seen[cy * w + cx]:
                                seen[cy * w + cx] = 1
                                queue.append((cx, cy))
                found.append([x0 * k, y0 * k, (x1 + 1) * k, (y1 + 1) * k])
    return found


def box_area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def box_gap(a, b):
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return (dx * dx + dy * dy) ** 0.5


def group_subjects(found, expected, sheet_area):
    """Group ink components into the expected subjects.

    Fragments mostly inside a larger component's box (an ear, a plank) are folded in first, because diagonal
    neighbours can have overlapping boxes; then the closest groups merge; small specks join the nearest group.
    """
    def inside(inner, outer):
        x0, y0, x1, y1 = max(inner[0], outer[0]), max(inner[1], outer[1]), min(inner[2], outer[2]), min(inner[3], outer[3])
        return max(0, x1 - x0) * max(0, y1 - y0) / max(1, box_area(inner))

    big = sorted((list(b) for b in found if box_area(b) > 0.004 * sheet_area), key=box_area, reverse=True)
    groups = []
    for box in big:
        if not any(inside(box, g) > 0.7 for g in groups):
            groups.append(box)
    while len(groups) > expected:
        _, i, j = min((box_gap(groups[i], groups[j]), i, j)
                      for i in range(len(groups)) for j in range(i + 1, len(groups)))
        a, b = groups[i], groups.pop(j)
        groups[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
    require(len(groups) == expected, f"Found {len(groups)} subjects on the sheet, expected {expected}")
    for box in found:
        if box_area(box) <= 0.004 * sheet_area:
            nearest = min(groups, key=lambda g: box_gap(g, box))
            if box_gap(nearest, box) < 60:
                nearest[:] = [min(nearest[0], box[0]), min(nearest[1], box[1]),
                              max(nearest[2], box[2]), max(nearest[3], box[3])]
    return groups


def despeck(crop, k=2, reach=30):
    """Erase small ink pieces outside the subject's outline and more than ``reach`` px from its large pieces."""
    W, H = crop.size
    mask = ImageOps.invert(crop.convert("L").resize((W // k, H // k))).point(lambda v: 255 if v > 60 else 0)
    w, h = mask.size
    px, label, sizes = mask.load(), [0] * (w * h), [0]
    for x in range(w):
        for y in range(h):
            if px[x, y] and not label[y * w + x]:
                sizes.append(0)
                n = len(sizes) - 1
                queue, label[y * w + x] = deque([(x, y)]), n
                while queue:
                    a, b = queue.popleft()
                    sizes[n] += 1
                    for cx in (a - 1, a, a + 1):
                        for cy in (b - 1, b, b + 1):
                            if 0 <= cx < w and 0 <= cy < h and px[cx, cy] and not label[cy * w + cx]:
                                label[cy * w + cx] = n
                                queue.append((cx, cy))
    if len(sizes) <= 2:
        return crop
    big = {i for i in range(1, len(sizes)) if sizes[i] >= 0.2 * max(sizes)}
    body = Image.new("L", (w, h), 0)
    bp = body.load()
    for i, lab in enumerate(label):
        if lab in big:
            bp[i % w, i // w] = 255
    for _ in range(reach // k // 2):
        body = body.filter(ImageFilter.MaxFilter(5))
    # Eyes, nostrils and patches lie inside the outline: flood the outside from the border and keep the rest.
    bp, outside = body.load(), Image.new("L", (w, h), 0)
    op = outside.load()
    queue = deque((x, y) for x in range(w) for y in (0, h - 1) if not bp[x, y])
    queue.extend((x, y) for y in range(h) for x in (0, w - 1) if not bp[x, y])
    for x, y in queue:
        op[x, y] = 255
    while queue:
        a, b = queue.popleft()
        for cx, cy in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
            if 0 <= cx < w and 0 <= cy < h and not op[cx, cy] and not bp[cx, cy]:
                op[cx, cy] = 255
                queue.append((cx, cy))
    kept = {lab for i, lab in enumerate(label) if lab and (lab in big or not op[i % w, i // w])}
    out = crop.copy()
    draw = ImageDraw.Draw(out)
    for i, lab in enumerate(label):
        if lab and lab not in kept:
            x, y = i % w, i // w
            draw.rectangle([x * k - 1, y * k - 1, x * k + k, y * k + k], fill="white")
    return out


def split_sheet(path, rows, out_dir, size=(1466, 1073)):
    """Cut a colouring sheet into one image per subject. ``rows`` lists names per grid row, top to bottom."""
    image = Image.open(path).convert("RGB")
    W, H = image.size
    names = [name for row in rows for name in row]
    groups = group_subjects(ink_boxes(image), len(names), W * H)
    top = [g for g in groups if (g[1] + g[3]) / 2 < H / 2] if len(rows) > 1 else groups
    bottom = [g for g in groups if g not in top]
    require([len(top), len(bottom)][:len(rows)] == [len(row) for row in rows],
            "The sheet's subjects do not match the declared rows")
    aspect = size[0] / size[1]
    results = {}
    for box, name in zip(sorted(top, key=lambda g: g[0]) + sorted(bottom, key=lambda g: g[0]), names):
        box = [max(0, box[0] - 8), max(0, box[1] - 8), min(W, box[2] + 8), min(H, box[3] + 8)]
        crop = despeck(image.crop(box))
        cw, ch = crop.size
        tw = max(cw * 1.08, ch * 1.08 * aspect)
        canvas = Image.new("RGB", (round(tw), round(tw / aspect)), "white")
        canvas.paste(crop, ((canvas.width - cw) // 2, (canvas.height - ch) // 2))
        target = out_dir / f"{name}.png"
        canvas.resize(size, Image.LANCZOS).save(target)
        results[name] = {"file": str(target), "sheet_box": box, **colouring_metrics(target)}
    return results
