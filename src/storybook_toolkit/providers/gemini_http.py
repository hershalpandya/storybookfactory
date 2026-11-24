"""HTTP adapter for the Google Gemini image API: request wire format, error mapping and response decoding.

It knows nothing about budgets, journals or reviews; generation.py owns those. Every adapter offers the
ImageProvider interface in providers/__init__.py. There is no fallback provider: callers get ProviderStop.
"""

from base64 import b64decode, b64encode
from hashlib import sha256 as sha256_digest
from http.client import HTTPException
from io import BytesIO
import json
import os
import re
import subprocess
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from PIL import Image

from ..edition import checked_path
from ..provider import KEYCHAIN_ACCOUNT, keychain_service
from ..store import ProjectError, require

MODEL = "gemini-nano-banana-2.1"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
MAX_INLINE_BYTES = 20_000_000
# Responses echo every input plus a large thought block; long ones can break mid-stream.
READBACK_WAITS = (2, 10, 30, 60, 120)


class ProviderStop(ProjectError):
    def __init__(self, reason, *, ambiguous=False, provider_id=None, usage=None):
        super().__init__(reason)
        self.ambiguous = ambiguous
        self.provider_id = provider_id
        self.usage = usage


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def error_detail(exc):
    """Short provider message from an HTTP error body; never includes request data."""
    try:
        body = json.loads(exc.read(4000))
        message = body["error"]["message"] if isinstance(body, dict) else ""
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        return ""
    return " ".join(str(message).split())[:300]


def to_png(data):
    """Google returns JPEG only; intake is PNG. Convert decoded pixels without resampling."""
    try:
        with Image.open(BytesIO(data)) as image:
            fmt = image.format
            require(fmt in ("JPEG", "PNG"), "Gemini output is neither JPEG nor PNG")
            if fmt == "PNG":
                return data, {"mime_type": "image/png", "sha256": sha256_digest(data).hexdigest()}
            out = BytesIO()
            image.convert("RGB").save(out, "PNG")
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ProjectError("Gemini output image could not be decoded") from exc
    return out.getvalue(), {"mime_type": "image/jpeg", "sha256": sha256_digest(data).hexdigest(),
                            "converted_to": "image/png"}


WIRE_JPEG_QUALITY = 92


def wire_bytes(path):
    """Bytes sent for one attachment: PNG sources travel as JPEG q92 to fit the inline limit."""
    data = path.read_bytes()
    if path.suffix != ".png":
        return data, {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[path.suffix]
    with Image.open(BytesIO(data)) as image:
        if image.mode in ("RGBA", "LA", "P"):
            rgba = image.convert("RGBA")
            image = Image.new("RGB", rgba.size, (255, 255, 255))
            image.paste(rgba, mask=rgba.getchannel("A"))
        out = BytesIO()
        image.convert("RGB").save(out, "JPEG", quality=WIRE_JPEG_QUALITY)
    return out.getvalue(), "image/jpeg"


def partial_id(exc):
    """Interaction id from the start of a truncated response body, if it arrived."""
    found = re.search(rb'"id"\s*:\s*"([A-Za-z0-9_-]{8,200})"', (getattr(exc, "partial", b"") or b"")[:4000])
    return found.group(1).decode() if found else None


def credential():
    value = os.environ.get("GEMINI_API_KEY", "").strip()
    if value:
        return value
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", keychain_service(),
             "-a", KEYCHAIN_ACCOUNT, "-w"],
            capture_output=True, timeout=5, check=False, text=True,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


class Gemini:
    def __init__(self):
        self._key = None
        self.source = None
        self.model_version = None

    def present(self):
        self._key = credential()
        return bool(self._key)

    def stored(self, provider_id):
        """Read a stored interaction back by id; this makes no new generation."""
        request = Request(f"{ENDPOINT}/{provider_id}",
                          headers={"x-goog-api-key": self._key, "Api-Revision": "2026-05-20"})
        with build_opener(NoRedirect()).open(request, timeout=300) as response:
            raw = response.read(80_000_001)
        require(len(raw) <= 80_000_000, "Gemini response exceeded the intake limit")
        return json.loads(raw)

    def decode(self, payload):
        """The single output image, its provider id and usage counters from an interaction payload."""
        provider_id = payload.get("id")
        self.model_version = payload.get("model") or payload.get("modelVersion") or payload.get("model_version")
        usage = {k: v for k, v in (payload.get("usage") or {}).items() if isinstance(v, int)}
        output = [c["data"] for step in payload.get("steps", []) if step.get("type") == "model_output"
                  for c in step.get("content", []) if c.get("type") == "image" and c.get("data")]
        if not output and payload.get("output_image", {}).get("data"):
            output = [payload["output_image"]["data"]]
        require(len(output) == 1, "Expected one output image")
        png, self.source = to_png(b64decode(output[0], validate=True))
        return png, provider_id, usage

    def send(self, root, packet):
        content = [{"type": "text", "text": packet["prompt"]}]
        for ref in packet["ordered_inputs"]:
            data, mime_type = wire_bytes(checked_path(root, ref))
            content.append({"type": "image", "mime_type": mime_type,
                            "data": b64encode(data).decode("ascii")})
        data = {"model": MODEL, "input": content,
                "response_format": {"type": "image", "aspect_ratio": packet["aspect_ratio"],
                                    "image_size": packet["image_size"], "mime_type": "image/jpeg"}}
        headers = {"x-goog-api-key": self._key, "Api-Revision": "2026-05-20"}
        request = Request(ENDPOINT, data=json.dumps(data).encode(),
                          headers={**headers, "Content-Type": "application/json"})

        def fetch(req):
            with build_opener(NoRedirect()).open(req, timeout=180) as response:
                raw = response.read(80_000_001)
            require(len(raw) <= 80_000_000, "Gemini response exceeded the intake limit")
            return json.loads(raw)

        try:
            try:
                payload = fetch(request)
            except (HTTPException, OSError) as exc:
                if isinstance(exc, HTTPError):
                    raise
                ident = partial_id(exc) or partial_id(exc.__cause__ or exc.__context__)
                if not ident:
                    raise
                # The interaction is stored by Google; reading it back makes no new generation.
                payload = None
                for wait in READBACK_WAITS:
                    sleep(wait)
                    try:
                        payload = fetch(Request(f"{ENDPOINT}/{ident}", headers=headers))
                        break
                    except (HTTPException, OSError, ValueError, ProjectError):
                        continue
                if payload is None:
                    raise ProviderStop("Gemini response interrupted; stored interaction could not be read back",
                                       ambiguous=True, provider_id=ident) from None
        except ProviderStop:
            raise
        except HTTPError as exc:
            reasons = {400: "request or API configuration rejected", 401: "authentication rejected",
                       403: "authentication or model access rejected", 404: "selected model unavailable",
                       429: "quota or billing limit reached"}
            detail = error_detail(exc)
            raise ProviderStop(f"Gemini HTTP {exc.code}: {reasons.get(exc.code, 'provider request failed')}"
                               + (f" ({detail})" if detail else ""),
                               ambiguous=exc.code >= 500) from None
        except (TimeoutError, URLError, OSError, HTTPException, UnicodeError, ValueError, ProjectError):
            raise ProviderStop("Gemini response interrupted or unreadable; reconcile before retrying",
                               ambiguous=True) from None
        try:
            return self.decode(payload)
        except (AttributeError, TypeError, KeyError, ValueError, ProjectError):
            raise ProviderStop("Gemini returned no usable single image",
                               provider_id=payload.get("id") if isinstance(payload, dict) else None) from None
