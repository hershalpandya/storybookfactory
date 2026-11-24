# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Image provider adapters.

An adapter implements ImageProvider; generation.dispatch talks to one adapter and never falls back to another.
"""

from typing import Protocol


class ImageProvider(Protocol):
    """What generation.dispatch needs from an image provider."""

    source: dict | None  # what the provider returned before intake conversion
    model_version: str | None

    def present(self) -> bool:
        """True when a credential is available; makes no request."""

    def send(self, root, packet):
        """Submit one packet; return (png_bytes, provider_id, usage) or raise ProviderStop."""

    def stored(self, provider_id):
        """Read a stored response back by id without a new generation."""

    def decode(self, payload):
        """Return (png_bytes, provider_id, usage) from a stored response."""
