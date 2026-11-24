"""Set plans: one 3D plan per recurring set, rendered locally from each page's camera.

A set plan is a JSON file kept with the private project. It holds the set's objects in metres (x east, z north,
y up), the block style of each actor, and one shot per page (camera plus where the actors stand). For a shot the
toolkit renders a flat-colour layout image (no provider call), a sentence saying where each object falls in the
frame, and yes/no checks (presence and facts, counts, left-to-right order, horizontal third) that any image of
that page can be scored against. Attach the layout to the page brief as part of its ``layout_reference`` so a
set keeps its geography when the camera moves; see docs/EDITIONS.md "Set plans and rendered layouts".

Elements use ground, box, polygon, sphere or group geometry. Groups combine solid shapes under one element
ID, so the visible parts share a label and visual checks. Each element may carry ``label``, ``facts``,
``count``, ``fixture``, ``describe`` and ``visible_note``.
"""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

from .store import require

W, H, NEAR = 1200, 800, 0.3
SOLID_KINDS = {"box", "polygon", "sphere"}
KINDS = SOLID_KINDS | {"ground", "group"}


def load_plan(path):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    require(isinstance(plan.get("objects"), dict) and plan["objects"], "A set plan needs an objects map")
    for name, item in plan["objects"].items():
        require(isinstance(item, dict) and item.get("kind") in KINDS,
                f"Set element {name} needs a kind from {sorted(KINDS)}")
        if item["kind"] == "group":
            parts = item.get("parts")
            require(isinstance(parts, list) and parts and
                    all(isinstance(part, dict) and part.get("kind") in SOLID_KINDS for part in parts),
                    f"Set element {name} needs a nonempty parts list of boxes, polygons or spheres")
    require(isinstance(plan.get("shots", {}), dict), "shots must map page IDs to a camera and actors")
    return plan


class Camera:
    def __init__(self, pos, yaw, fov=60, pitch=-4):
        require(len(pos) == 3 and 10 <= fov <= 120, "A camera needs pos [x, y, z], yaw and a fov of 10-120 degrees")
        self.x, self.y, self.z = pos
        a, p = math.radians(yaw), math.radians(pitch)
        self.f = (math.sin(a), math.cos(a))
        self.r = (math.cos(a), -math.sin(a))
        self.cp, self.sp = math.cos(p), math.sin(p)
        self.focal = (W / 2) / math.tan(math.radians(fov) / 2)

    def view(self, p):
        dx, dy, dz = p[0] - self.x, p[1] - self.y, p[2] - self.z
        xr = dx * self.r[0] + dz * self.r[1]
        zf = dx * self.f[0] + dz * self.f[1]
        return xr, dy * self.cp - zf * self.sp, zf * self.cp + dy * self.sp

    def screen(self, v):
        xr, y, zf = v
        return W / 2 + self.focal * xr / zf, H / 2 - self.focal * y / zf


def clip(poly):
    """Clip a view-space polygon against the near plane (Sutherland-Hodgman)."""
    out = []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        ina, inb = a[2] >= NEAR, b[2] >= NEAR
        if ina:
            out.append(a)
        if ina != inb:
            t = (NEAR - a[2]) / (b[2] - a[2])
            out.append(tuple(a[k] + t * (b[k] - a[k]) for k in range(3)))
    return out


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def box(cx, cz, w, d, h, y0, colour, tag, yaw=0.0):
    a = math.radians(yaw)
    corners = []
    for sx, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        ox, oz = sx * w / 2, sz * d / 2
        corners.append((cx + ox * math.cos(a) + oz * math.sin(a), cz - ox * math.sin(a) + oz * math.cos(a)))
    lo = [(x, y0, z) for x, z in corners]
    hi = [(x, y0 + h, z) for x, z in corners]
    faces = [(hi, shade(colour, 1.08), tag)]
    for i, k in zip(range(4), (0.95, 0.8, 0.7, 0.85)):
        j = (i + 1) % 4
        faces.append(([lo[i], lo[j], hi[j], hi[i]], shade(colour, k), tag))
    return faces


def geometry(plan, actors):
    """Calculate ground tiles and solid shapes for the shot's elements and characters."""
    faces, spheres, ground = [], [], []
    for name, o in plan["objects"].items():
        c = tuple(o.get("colour", (180, 180, 180)))
        kind = o["kind"]
        if kind == "ground":
            (x0, x1), (z0, z1) = o["x"], o["z"]
            z = z0
            while z < z1:
                x = x0
                while x < x1:
                    x2, z2 = min(x + 2, x1), min(z + 2, z1)
                    ground.append(([(x, 0, z), (x2, 0, z), (x2, 0, z2), (x, 0, z2)], c, name))
                    x += 2
                z += 2
            if "dashes" in o:
                d = o["dashes"]
                for x in range(int(x0), int(x1), 4):
                    ground.append(([(x, 0.01, d - 0.1), (x + 2, 0.01, d - 0.1), (x + 2, 0.01, d + 0.1),
                                    (x, 0.01, d + 0.1)], (245, 245, 245), name))
        else:
            for part in o["parts"] if kind == "group" else (o,):
                colour = tuple(part.get("colour", c))
                if part["kind"] == "box":
                    faces += box(part["x"], part["z"], part["width"], part["depth"], part["height"],
                                 part.get("y", 0), colour, name, part.get("yaw", 0))
                elif part["kind"] == "polygon":
                    faces.append((part["vertices"], colour, name))
                else:
                    spheres.append(((part["x"], part["y"], part["z"]), part["radius"], colour, name))
    for name, where in actors.items():
        require(name in plan.get("actors", {}), f"Unknown actor {name}; declare it in the plan's actors map")
        spec = plan["actors"][name]
        x, z, *rest = where
        faces += box(x, z, spec["width"], spec.get("depth", spec["width"] * 0.6), spec["height"], rest[0] if rest else 0,
                     tuple(spec["colour"]), name)
    return ground, faces, spheres


def render(plan, shot, target):
    """Draw the shot to ``target`` and return each visible object's frame box and distance."""
    cam = Camera(**shot["camera"])
    ground, faces, spheres = geometry(plan, shot.get("actors", {}))
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)], fill=(int(150 + 80 * t), int(195 + 40 * t), 245))
    ownership = Image.new("I", img.size)
    owner_draw = ImageDraw.Draw(ownership)
    tag_ids = {}
    distances = {}

    def owner_id(tag, distance):
        ident = tag_ids.setdefault(tag, len(tag_ids) + 1)
        distances[ident] = min(distance, distances.get(ident, distance))
        return ident

    def paint(poly3, colour, tag, record=True):
        v = clip([cam.view(p) for p in poly3])
        if len(v) < 3:
            return
        pts = [cam.screen(p) for p in v]
        draw.polygon(pts, fill=colour)
        if record:
            distance = min(math.hypot(p[0], p[2]) for p in v)
            owner_draw.polygon(pts, fill=owner_id(tag, distance))

    for poly, colour, tag in sorted(ground, key=lambda f: -sum(cam.view(p)[2] for p in f[0]) / 4):
        paint(poly, colour, tag, record=False)

    def depth(item):
        kind, f = item
        if kind == "sphere":
            return cam.view(f[0])[2] + f[1] * 0.3
        return max(cam.view(p)[2] for p in f[0])

    for kind, f in sorted([("face", f) for f in faces] + [("sphere", s) for s in spheres], key=depth, reverse=True):
        if kind == "face":
            paint(*f)
            continue
        centre, radius, colour, tag = f
        v = cam.view(centre)
        if v[2] < NEAR + radius:
            continue
        u, w = cam.screen(v)
        r = cam.focal * radius / v[2]
        bounds = [u - r, w - r * 0.85, u + r, w + r * 0.85]
        draw.ellipse(bounds, fill=colour)
        draw.ellipse([u - r * 0.6, w - r * 0.75, u + r * 0.3, w], fill=shade(colour, 1.15))
        owner_draw.ellipse(bounds, fill=owner_id(tag, math.hypot(v[0], v[2])))
    img.save(target)

    # Rasterize element IDs in the same draw order as the image. Only the topmost ID survives per pixel.
    boxes = {ident: [W, H, 0, 0] for ident in tag_ids.values()}
    for offset, ident in enumerate(ownership.get_flattened_data()):
        if ident == 0:
            continue
        y, x = divmod(offset, W)
        box_ = boxes[ident]
        box_[0] = min(box_[0], x)
        box_[1] = min(box_[1], y)
        box_[2] = max(box_[2], x + 1)
        box_[3] = max(box_[3], y + 1)
    visible = {}
    for tag, ident in tag_ids.items():
        u0, v0, u1, v1 = boxes[ident]
        if u1 - u0 > 4 and v1 - v0 > 4:
            visible[tag] = {"box": [round(u0 / W, 3), round(v0 / H, 3), round(u1 / W, 3), round(v1 / H, 3)],
                            "distance_m": round(distances[ident], 1)}
    return visible


def label(plan, tag):
    item = plan.get("objects", {}).get(tag) or plan.get("actors", {}).get(tag) or {}
    return item.get("label", tag)


def centre(box_):
    return (box_[0] + box_[2]) / 2


def third(box_):
    c = centre(box_)
    return "left third" if c < 1 / 3 else "right third" if c > 2 / 3 else "centre"


def tracked(plan, tag, actors):
    return tag in actors or plan["objects"].get(tag, {}).get("fixture", False)


def describe(plan, visible):
    """Where each visible object falls in the frame, left to right; reused word for word by every page."""
    parts = []
    for tag, v in sorted(visible.items(), key=lambda kv: centre(kv[1]["box"])):
        if plan["objects"].get(tag, {}).get("describe") is False:
            continue
        dist = "near" if v["distance_m"] < 7 else "middle distance" if v["distance_m"] < 16 else "far"
        parts.append(f"{label(plan, tag)} in the {third(v['box'])}, {dist}")
    notes = [plan["objects"][t]["visible_note"] for t in visible if plan["objects"].get(t, {}).get("visible_note")]
    text = "Layout from this camera (left to right): " + "; ".join(parts) + "." if parts else ""
    return " ".join([text, *notes]).strip()


def checks(plan, visible, actors):
    """Yes/no checks derived from the plan for one shot: presence and facts, counts, order and placement."""
    out = {}
    for tag in visible:
        item = plan["objects"].get(tag, {})
        if item.get("facts"):
            out[f"set-{tag}"] = f"Present and matches the plan: {item['facts']}."
        if item.get("count"):
            out[f"count-{tag}"] = f"{item['count'][0].upper()}{item['count'][1:]}."
    order = [t for t, v in sorted(visible.items(), key=lambda kv: centre(kv[1]["box"])) if tracked(plan, t, actors)]
    for a, b in zip(order, order[1:]):
        if centre(visible[b]["box"]) - centre(visible[a]["box"]) > 0.08:
            out[f"order-{a}-{b}"] = f"{label(plan, a)} is left of {label(plan, b)} in the picture."
    for tag in order:
        out[f"place-{tag}"] = f"{label(plan, tag)} sits in the {third(visible[tag]['box'])} of the picture."
    return out


def compose(layout, top_images, target, width=1800):
    """Reference sheet: the given images side by side in a top band, the rendered layout below."""
    tops = []
    for path in top_images:
        with Image.open(path) as im:
            tops.append(im.convert("RGB"))
    band = 420 if tops else 0
    if tops:
        total = sum(t.width * band / t.height for t in tops)
        scale = min(1.0, (width - 20 * (len(tops) - 1)) / total)
        tops = [t.resize((max(1, round(t.width * band * scale / t.height)), round(band * scale))) for t in tops]
    with Image.open(layout) as block:
        block = block.convert("RGB").resize((width, round(width * block.height / block.width)))
        sheet = Image.new("RGB", (width, band + (40 if tops else 0) + block.height), "white")
        x = 0
        for t in tops:
            sheet.paste(t, (x, band - t.height))
            x += t.width + 20
        sheet.paste(block, (0, band + (40 if tops else 0)))
        sheet.save(target)
    return target


def layout_role(plan, actors, top_roles):
    """Attachment role for a composed sheet; names the colour of every actor block."""
    blocks = ", ".join(f"{label(plan, a)} = {plan['actors'][a].get('colour_name', 'its coloured block')}" for a in actors)
    lead = " ".join(top_roles) + " " if top_roles else ""
    return (lead + f"{'Bottom' if top_roles else 'This picture'}: a flat-colour 3D layout of the set seen from THIS "
            f"page's camera; coloured blocks mark where each character or object stands ({blocks}). Paint the scene "
            "with exactly this camera and layout: the same objects in the same places, at the same sizes, in the same "
            "left-to-right order. Do not copy the flat colours, the blocks or the sheet layout.")


def score(answers, key=None):
    """Agreement rate per image and, with a key, per arm: the share of derived checks answered yes."""
    rows = {}
    for image, items in answers.items():
        values = [v["answer"] if isinstance(v, dict) else v for v in items.values()]
        rows[image] = {"yes": values.count("yes"), "no": values.count("no"), "unclear": values.count("unclear"),
                       "total": len(values)}
        rows[image]["rate"] = round(rows[image]["yes"] / max(1, len(values)), 3)
    report = {"images": rows}
    if key:
        arms = {}
        for image, row in rows.items():
            arm = arms.setdefault(key[image]["arm"], {"yes": 0, "total": 0})
            arm["yes"] += row["yes"]
            arm["total"] += row["total"]
        for arm in arms.values():
            arm["rate"] = round(arm["yes"] / max(1, arm["total"]), 3)
        report["arms"] = arms
    return report
