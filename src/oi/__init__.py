"""Oi — smarter self-hosted AI assistant (multi-user, multi-agent)."""

from __future__ import annotations

from oi.infra.utils.httpx_proxy import install_httpx_cidr_no_proxy

def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("oi")
    except Exception:
        return "1.0.2"


__version__ = _get_version()

# httpx 0.28 treats NO_PROXY CIDR as an exact IP (see issue #1347). Patch once
# at import so CLI, ``oi run``, and in-process harness clients all honor it.
install_httpx_cidr_no_proxy()
