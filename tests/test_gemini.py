# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""The Gemini adapter (wire format, errors, cost) and the dispatch policy gates of an edition."""

from base64 import b64encode
from copy import deepcopy
from http.client import IncompleteRead
from io import BytesIO
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from PIL import Image

from storybook_toolkit import edition, gemini
from storybook_toolkit.providers import gemini_http
from storybook_toolkit.store import ProjectError, load, write_json
from support import revise, run, stub_http


def test_gemini_error_detail_reports_provider_message_only():
    body = b'{"error": {"code": 400, "message": "Invalid  value\\nfor image_size", "status": "INVALID_ARGUMENT"}}'
    assert gemini.error_detail(HTTPError("u", 400, "x", {}, BytesIO(body))) == "Invalid value for image_size"
    assert gemini.error_detail(HTTPError("u", 400, "x", {}, BytesIO(b"<html>"))) == ""


def test_gemini_jpeg_output_is_converted_to_png_pixels():
    source = BytesIO()
    Image.new("RGB", (30, 20), (120, 60, 30)).save(source, "JPEG")
    png, info = gemini.to_png(source.getvalue())
    with Image.open(BytesIO(png)) as image:
        assert image.format == "PNG" and image.size == (30, 20)
    assert info["mime_type"] == "image/jpeg" and info["converted_to"] == "image/png"
    with pytest.raises(ProjectError, match="decoded"):
        gemini.to_png(b"not an image")


def test_gemini_resume_releases_a_failed_attempt_once(tmp_path):
    path, record = gemini.journal(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    record["attempts"]["a1"] = {"case": "c", "status": "failed", "slot": "p/illustration"}
    write_json(path, record)
    args = SimpleNamespace(project=tmp_path, owner="Owner", evidence="Request format fixed",
                           resubmit="a1", reconcile=None, resubmission=None)
    gemini.resume(args)
    saved = load(path)
    assert saved["attempts"]["a1"]["resubmission"] == "allow" and not saved.get("paused")
    assert saved["resumptions"][-1]["attempt"] == "a1"
    with pytest.raises(ProjectError, match="not yet released"):
        gemini.resume(args)
    with pytest.raises(ProjectError, match="not paused"):
        gemini.resume(SimpleNamespace(**{**vars(args), "resubmit": None}))


def test_gemini_png_attachments_travel_as_jpeg(tmp_path):
    path = tmp_path / "ref.png"
    Image.new("RGBA", (40, 30), (10, 200, 30, 0)).save(path)
    data, mime = gemini.wire_bytes(path)
    assert mime == "image/jpeg" and data[:3] == b"\xff\xd8\xff"


def test_gemini_partial_response_yields_interaction_id():
    assert gemini.partial_id(IncompleteRead(b'{\n  "id": "v1_AbC-123_xyz",\n  "status"')) == "v1_AbC-123_xyz"
    assert gemini.partial_id(IncompleteRead(b'{"steps": [')) is None
    assert gemini.partial_id(ValueError("x")) is None


def test_gemini_cost_estimate_uses_recorded_tokens():
    used = {"status": "captured", "usage": {"total_input_tokens": 8000, "total_output_tokens": 2000}}
    assert abs(gemini.cost_estimate(used) - (0.004 + 0.06)) < 1e-9
    assert gemini.cost_estimate({"status": "failed"}) == 0.0
    lost = {"status": "reconciled", "image_size": "2K", "reconciliation": "treat as delivered and billed"}
    assert gemini.cost_estimate(lost) > 0.05


def test_gemini_dry_run_warns_about_scene_references_and_missing_neighbours():
    scene = {"image": {"sha256": "s"}}
    manifest = {"roots": {f"characters/{name}/summer/side": scene for name in ("a", "b", "c")}}
    packet = {"kind": "illustration", "parent": None,
              "ordered_inputs": [{"file": "content/s.png", "sha256": "s", "roles": ["a summer side"]}]}
    warnings = gemini.packet_warnings(manifest, packet)
    assert any("3 subjects" in w for w in warnings) and any("neighbour" in w for w in warnings)
    packet["ordered_inputs"][0]["roles"] = ["Match its style"]
    manifest["roots"] = {"characters/a/summer/side": scene}
    assert gemini.packet_warnings(manifest, packet, [{"sha256": "s"}]) == []


def set_policy(root, tmp_path, **options):
    revise(root, tmp_path / "policy.json", {"op": "generation", "model": gemini.MODEL,
                                             "slots": ["outbound/illustration"], **options})


def test_strict_references_refuse_one_scene_shared_by_three_subjects(delivery, tmp_path):
    _, root, _, _ = delivery
    set_policy(root, tmp_path, max_submissions=3, strict_references=True)
    manifest = edition.load_edition(root)
    shared = manifest["roots"]["characters/marine/flying/front"]
    for subject in ("lumen", "display"):
        manifest["roots"][f"characters/{subject}/flying/front"] = deepcopy(shared)
    edition.publish(root, manifest, manifest["revision"])
    args = SimpleNamespace(project=root, slot="outbound/illustration", parent=None, edit=None, dry_run=False)
    with pytest.raises(ProjectError, match="Strict references: .* 3 subjects"):
        gemini.dispatch(args)
    assert not gemini.journal(root)[0].exists()


def captured_journal(root, count):
    path, record = gemini.journal(root)
    for index in range(1, count + 1):
        record["attempts"][f"a{index}"] = {"case": f"c{index}", "status": "captured", "slot": "outbound/illustration"}
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, record)
    return path


def quality(root, attempt, decision, ok=True):
    return run("edition", "gemini-quality", root, attempt, decision, "--reviewer", "Fixture reviewer",
               "--seconds", "3", "--evidence", "Fixture observation", ok=ok)


def test_failures_pause_a_slot_only_at_the_per_slot_cap(delivery, tmp_path):
    _, root, _, _ = delivery
    set_policy(root, tmp_path, max_submissions=5, max_failures_per_slot=2)
    path = captured_journal(root, 2)
    quality(root, "a1", "unusable")
    assert not load(path).get("paused")
    assert "Visual review stopped the pilot" in quality(root, "a2", "unusable", ok=False).stderr
    assert load(path)["paused"]["attempt"] == "a2"


def test_submission_ceiling_pauses_after_a_review_that_does_not_pass(delivery, tmp_path):
    _, root, _, _ = delivery
    set_policy(root, tmp_path, max_submissions=3)
    path = captured_journal(root, 2)
    quality(root, "a1", "localized")
    assert not load(path).get("paused")
    path_record = load(path)
    path_record["attempts"]["a3"] = {"case": "c3", "status": "captured", "slot": "outbound/illustration"}
    write_json(path, path_record)
    assert "ceiling reached before visual acceptance" in quality(root, "a3", "localized", ok=False).stderr
    assert json.loads(run("edition", "next", root).stdout)["action"] == "budget-exhausted"


def image_payload(*images):
    encoded = []
    for colour in images:
        buffer = BytesIO()
        Image.new("RGB", (8, 8), colour).save(buffer, "JPEG")
        encoded.append({"type": "image", "data": b64encode(buffer.getvalue()).decode()})
    return {"id": "v1_fixture", "steps": [{"type": "model_output", "content": encoded}]}


def send_packet(tmp_path):
    return {"prompt": "Draw", "ordered_inputs": [], "aspect_ratio": "3:2", "image_size": "2K"}


def test_adapter_decodes_exactly_one_image():
    png, provider_id, _ = gemini_http.Gemini().decode(image_payload("red"))
    assert png.startswith(b"\x89PNG") and provider_id == "v1_fixture"
    with pytest.raises(ProjectError, match="Expected one output image"):
        gemini_http.Gemini().decode(image_payload("red", "blue"))


def test_adapter_maps_http_errors_and_interruptions_to_provider_stops(tmp_path, monkeypatch):
    adapter = gemini_http.Gemini()
    stub_http(monkeypatch, [HTTPError("u", 429, "x", {}, BytesIO(b"{}"))])
    with pytest.raises(gemini_http.ProviderStop, match="HTTP 429: quota") as stop:
        adapter.send(tmp_path, send_packet(tmp_path))
    assert not stop.value.ambiguous
    monkeypatch.setattr(gemini_http, "sleep", lambda seconds: None)
    interrupted = IncompleteRead(b'{"id": "v1_AbC-123_xyz", "status"')
    stub_http(monkeypatch, [interrupted] + [TimeoutError()] * len(gemini_http.READBACK_WAITS))
    with pytest.raises(gemini_http.ProviderStop, match="could not be read back") as stop:
        adapter.send(tmp_path, send_packet(tmp_path))
    assert stop.value.ambiguous and stop.value.provider_id == "v1_AbC-123_xyz"
    requests = stub_http(monkeypatch, [interrupted, image_payload("red")])
    png, provider_id, _ = adapter.send(tmp_path, send_packet(tmp_path))
    assert provider_id == "v1_fixture" and requests[1].full_url.endswith("/v1_AbC-123_xyz")
