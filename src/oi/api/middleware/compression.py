"""Gzip text responses (dashboard assets, API JSON).

Starlette's ``GZipMiddleware`` compresses anything that accepts gzip, which is
wrong for two cases this app hits constantly:

* ``FileResponse`` partial bodies — the dashboard serves Vite assets through
  ``FileResponse``, which answers ``Range`` requests with ``206`` and a
  ``content-range`` header. Compressing a 206 body makes the byte offsets in
  that header meaningless.
* Already-compressed payloads — ``woff2``, ``png``, ``webp``, ``mp4``, ``zip``.
  Gzipping them burns CPU and grows the body.

This middleware narrows the stock implementation to text payloads and skips
range requests entirely, so byte-exact downloads and the service worker cache
keep working.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware, GZipResponder
from starlette.types import ASGIApp, Receive, Scope, Send

# Text-ish payloads worth compressing. Anything else (fonts, images, video,
# archives) is already compressed or opaque to the browser.
_COMPRESSIBLE_EXACT = frozenset(
    {
        "application/javascript",
        "application/json",
        "application/xhtml+xml",
        "application/xml",
    }
)

# Below this, the gzip header + checksum cost more than they save. Vite CSS and
# JS chunks are all well above it; small JSON responses are not.
DEFAULT_MINIMUM_SIZE = 512

# Level 6 is the stdlib default: ~10% larger than level 9 on these chunks but
# roughly 3x faster, which matters when every cold cache re-compresses 3.6 MB.
DEFAULT_COMPRESSLEVEL = 6


def is_compressible_content_type(content_type: str) -> bool:
    """True when a ``Content-Type`` value should be gzip-compressed."""
    media_type = content_type.split(";", 1)[0].strip().lower()
    if not media_type:
        return False
    if media_type.startswith("text/"):
        return True
    if media_type in _COMPRESSIBLE_EXACT:
        return True
    return media_type.endswith("+json") or media_type.endswith("+xml")


class _TextOnlyGZipResponder(GZipResponder):
    """``GZipResponder`` that also skips non-text and pre-encoded responses.

    Exclusion is only ever turned *on* here — never off. Starlette already
    excludes ``text/event-stream`` for SSE buffering, and re-enabling
    compression for it would defeat that guard.
    """

    async def send_with_compression(self, message: MutableMapping[str, Any]) -> None:
        await super().send_with_compression(message)
        # ``http.response.start`` only stashes the message; the body message is
        # what flushes headers, so flipping the flag right after is still in
        # time to suppress compression.
        if message["type"] == "http.response.start":
            content_type = Headers(raw=self.initial_message["headers"]).get("content-type", "")
            if not is_compressible_content_type(content_type):
                self.content_type_is_excluded = True


class TextGZipMiddleware(GZipMiddleware):
    """``GZipMiddleware`` restricted to text payloads, skipping range requests."""

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = DEFAULT_MINIMUM_SIZE,
        compresslevel: int = DEFAULT_COMPRESSLEVEL,
    ) -> None:
        super().__init__(app, minimum_size=minimum_size, compresslevel=compresslevel)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover - websockets pass through
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        # A ``Range`` request gets a 206 partial body that must stay byte-exact.
        if "range" in headers or "gzip" not in headers.get("accept-encoding", ""):
            await self.app(scope, receive, send)
            return

        responder = _TextOnlyGZipResponder(
            self.app,
            self.minimum_size,
            compresslevel=self.compresslevel,
        )
        await responder(scope, receive, send)
