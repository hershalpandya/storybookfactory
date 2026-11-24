"""Offline benchmark of the gates and scorer with authored visual observations."""

import json

import pytest

from storybook_toolkit import catalog, staging, visual_review
from support import approve_set, observed, png, run, write


def test_staged_commands_guard_handoff_registration_and_reuse(story, tmp_path):
    root, plan = story
    args = (root, "--page", "p2", "--kind", "illustration")
    assert "set-reviews" in run("scene-handoff", *args, ok=False).stderr
    preflight = approve_set(root, "p2")
    packet = json.loads(run("scene-handoff", *args).stdout)
    assert preflight["contract_sha256"] == packet["contract_sha256"]
    assert "A mouse with a striped shoulder badge. Smooth brushed coat." in packet["prompt"]
    assert "Anatomical legs: 4. Visible legs: 3." in packet["prompt"]
    assert "door-design: crossed doors" in packet["prompt"]
    assert {(ref["subject"], ref["view"]) for ref in packet["references"]} == {("pip", "side"), ("hall", "front")}
    assert "p1" == preflight["contract"]["adjacent_sets"][0]["id"]
    picture = tmp_path / "page.png"
    picture.write_bytes(png(100))
    argument = (root, "p2", "illustration", picture)
    assert "visual-reviews" in run("register-asset", *argument, ok=False).stderr
    checklist = json.loads(run("image-checklist", *argument).stdout)
    assert "visible_legs" not in checklist["subjects"]["pip"]
    record = observed(packet, checklist["image_sha256"], "illustration")
    run("review-image", *argument, write(tmp_path / "visual.json", record))
    run("register-asset", *argument)
    assert "recorded visual review passed" in run("check-assets", root).stdout
    plan["pages"][0]["set"]["layout"] = "Straw kept away from the threshold."
    write(root / "scenes.json", plan)
    assert "stale" in run("scene-handoff", *args, ok=False).stderr
    assert "scene plan changed" in run("check-assets", root, ok=False).stderr

    sequel = tmp_path / "sequel"
    run("init", sequel)
    config = json.loads((sequel / "project.json").read_text())
    config["scene_format_version"] = 2
    write(sequel / "project.json", config)
    run("init-catalogs", sequel)
    run("import-catalog-entry", sequel, root, "characters", "pip")
    run("check-catalogs", sequel)
    entries = catalog.catalogs(sequel)
    entries["characters"]["pip"]["states"]["brushed"]["description"] = "Different coat."
    write(catalog.catalog_path(sequel, "characters"), {"format_version": 1, "entries": entries["characters"]})
    assert "Stale" in run("check-catalogs", sequel, ok=False).stderr


MISMATCHES = [
    ("pip", "visible_legs", 5, "pip/visible_legs"),
    ("pip", "view", "front", "pip/view"),
    ("pip", "facts", {"badge": "on head", "coat": "curly"}, "pip/facts/coat"),
    ("hall", "facts", {"doors": "missing", "door-design": "none", "floor": "floor mats", "colour-trim": "cream"},
     "hall/facts/doors"),
]


def reject(root, tmp_path, packet, mismatch):
    subject, key, wrong, failure = mismatch
    stage = (root, "p2", "illustration")
    rejected = tmp_path / "rejected.png"
    rejected.write_bytes(png(120))
    bad_sha = catalog.sha256(rejected.read_bytes())
    bad = observed(packet, bad_sha, "illustration")
    bad["subjects"][subject][key] = wrong
    assert failure in run("review-image", *stage, rejected, write(tmp_path / "observations.json", bad),
                          ok=False).stderr
    assert failure in run("register-asset", *stage, rejected, ok=False).stderr
    return bad_sha


@pytest.mark.parametrize("mismatch", MISMATCHES, ids=[row[3] for row in MISMATCHES])
def test_review_rejects_prompt_mismatches(story, tmp_path, mismatch):
    root, _ = story
    reject(root, tmp_path, approve_set(root, "p2"), mismatch)


def test_benchmark_scores_first_pass_and_retries(story, tmp_path):
    root, _ = story
    packet = approve_set(root, "p2")
    failure = MISMATCHES[0][3]
    bad_sha = reject(root, tmp_path, packet, MISMATCHES[0])
    good = tmp_path / "accepted.png"
    good.write_bytes(png(121))
    good_sha = catalog.sha256(good.read_bytes())
    run("review-image", root, "p2", "illustration", good,
        write(tmp_path / "observations.json", observed(packet, good_sha, "illustration")))
    run_manifest = write(tmp_path / "run.json", {"label": "offline benchmark", "cases": [{
        "page": "p2", "kind": "illustration", "contract_sha256": packet["contract_sha256"],
        "attempts": [{"error": "Transfer failed"}, {"image_sha256": bad_sha}, {"image_sha256": good_sha}],
    }]})
    report = json.loads(run("benchmark-images", root, run_manifest).stdout)
    assert (report["first_pass_cases"], report["passed_cases"], report["total_attempts"]) == (0, 1, 3)
    assert report["cases"][0]["first_pass_attempt"] == 3
    assert failure in report["cases"][0]["attempts"][1]["failures"]
    assert "threshold missed" in run("benchmark-images", root, run_manifest, "--min-first-pass", 0.5, ok=False).stderr


def test_structural_and_colouring_gates(story):
    root, plan = story
    del plan["pages"][1]["characters"]["pip"]["state_change"]
    write(root / "scenes.json", plan)
    assert "without a story reason" in run("set-preflight", root, "p2", ok=False).stderr
    plan["pages"][1]["characters"]["pip"]["state_change"] = "Sheared inside."
    write(root / "scenes.json", plan)
    packet = approve_set(root, "p2")
    output = json.loads(run("scene-handoff", root, "--page", "p2", "--kind", "colouring").stdout)
    assert list(output["expected"]["subjects"]) == ["pip"]
    contract = staging.page_contract(root, "p2")
    actual = observed(packet, "fixture-sha", "colouring")
    actual["extras"].append("A second mouse without a catalog ID.")
    assert visual_review.evaluate(contract, "colouring", "fixture-sha", actual) == ["extra-subjects"]


def test_staged_cover_and_render_require_reviewed_assets(story, tmp_path):
    root, plan = story
    cover = dict(plan["pages"][1], id="cover")
    for key in ("passages", "colouring", "colouring_subjects"):
        del cover[key]
    cover["characters"] = {"pip": {k: v for k, v in cover["characters"]["pip"].items() if k != "state_change"}}
    plan["covers"] = {"front": cover}
    write(root / "scenes.json", plan)
    assert "cover illustration: PENDING" in run("check-assets", root).stdout
    assert "cover colouring" not in run("check-assets", root).stdout
    counter = 170
    for page in ("p1", "p2", "cover"):
        packet = approve_set(root, page)
        kinds = ("illustration",) if page == "cover" else ("illustration", "colouring")
        for kind in kinds:
            counter += 1
            image = tmp_path / "candidate.png"
            image.write_bytes(png(counter))
            record = observed(packet, catalog.sha256(image.read_bytes()), kind)
            if page == "p1":
                record["subjects"]["pip"]["facts"]["coat"] = "curly"
            args = (root, page, kind, image)
            run("review-image", *args, write(tmp_path / "review.json", record))
            run("register-asset", *args)
    assert "Image kind unavailable for this page" in run(
        "scene-handoff", root, "--page", "cover", "--kind", "colouring", ok=False).stderr
    metadata = write(tmp_path / "metadata.json", {"title": "The hall"})
    output = tmp_path / "book"
    run("render", root, metadata, output)
    assert (output / "reading.pdf").read_bytes().startswith(b"%PDF")
    write(metadata, {"title": "The hall", "cover_image": "candidate.png"})
    assert "Use a staged front cover" in run("render", root, metadata, tmp_path / "bad-book", ok=False).stderr
