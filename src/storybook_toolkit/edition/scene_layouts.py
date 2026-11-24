# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Recurring-setting declarations and the preflight for fresh scene generation."""

from shlex import join

from ..store import ProjectError, identifier, prose, require, strings
from .manifest import checked_path


def plan_file(setting):
    return f"set-plans/{setting}.json"


def declaration(brief):
    setting = brief.get("setting")
    if identifier(setting) and "standalone_reason" not in brief:
        return setting
    if "setting" not in brief and prose(brief.get("standalone_reason")):
        return None
    raise ProjectError("Declare a setting ID or a standalone_reason in the illustration brief")


def layered_brief(brief):
    """Combine generated checks with authored checks without rewriting the authored brief."""
    reference = brief.get("layout_reference") or {}
    rendered = reference.get("rendered")
    if rendered is None:
        return brief
    require(isinstance(rendered, dict), "Invalid rendered layout record")
    checks = rendered.get("checks")
    require(strings(checks) and prose(rendered.get("text")), "Invalid rendered layout checks or description")
    authored = brief.get("visual_checks", {})
    for key in authored.keys() & checks.keys():
        require(authored[key] == checks[key], f"Rendered layout conflicts with authored visual check {key}")
    return {**brief, "visual_checks": {**authored, **checks}}


def blocker(root, manifest, slot, attached=None):
    """Return the first recovery step for a fresh scene packet, or None when ready."""
    page, _, kind = slot.partition("/")
    scenes = {p["id"]: p["art"]["illustration"]["brief"] for p in manifest["pages"]}
    if kind != "illustration" or page not in scenes:
        return None
    if not manifest.get("require_scene_layouts") and not any(
            "setting" in brief or "standalone_reason" in brief for brief in scenes.values()):
        return None
    settings = {}
    for scene, brief in scenes.items():
        try:
            settings[scene] = declaration(brief)
        except ProjectError as exc:
            return (f"{scene}/illustration: {exc}. Use a stage operation with "
                    f"{join(['storybook', 'edition', 'revise', str(root), 'stage.json'])}")
    setting = settings[page]
    if setting is None:
        return None

    source = plan_file(setting)
    output = root / "artwork-preparation" / f"layout-{page}"
    suffix = 2
    while output.exists() or output.is_symlink():
        output = output.with_name(f"layout-{page}-{suffix}")
        suffix += 1
    recovery = join(["storybook", "edition", "set-layout", str(root), source, page, str(output), "--stage"])
    reference = scenes[page].get("layout_reference") or {}
    rendered = reference.get("rendered") or {}
    if rendered.get("page") != page or rendered.get("plan") != source:
        return f"{slot}: missing rendered layout. Prepare {source}, then run {recovery}"
    try:
        checked_path(root, {"file": source, "sha256": rendered["plan_sha256"]})
        checked_path(root, reference)
    except (ProjectError, OSError, KeyError) as exc:
        return f"{slot}: stale rendered layout ({exc}). Run {recovery}"
    if attached is not None and not any(item["sha256"] == reference["sha256"] for item in attached):
        return f"{slot}: attach the staged rendered layout from {reference['file']} ({reference['sha256']})"
    return None
