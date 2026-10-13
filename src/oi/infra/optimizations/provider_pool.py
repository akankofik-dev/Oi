"""L1+L3: provider connection pool + pre-warm.

Creating an LLM client (auth, session, model handshake) on every agent switch
is a cold-start tax. :class:`ProviderConnectionPool` caches clients keyed by
``(provider, model)`` and can keep a few idle connections warm in the
background. Pooling is lazy — nothing is created until first use — and
pre-warming runs in a background task so it never slows server startup.

WIRING NOTE (2026-10-14): this module is intentionally NOT hooked into the
hot path. LLM client instantiation lives inside the external ``oi-harness``
package (``HarnessAgentManager``'s shared model factory, fed via
``sync_providers_to_harness`` with provider *configs*); this repository
contains no per-request client factory call site to pool (the only direct
``ChatOpenAI(...)`` construction is the one-off connectivity probe in
``providers/probe.py``). Hooking would require changing the external
oi-harness package, which is out of scope. The pool remains available
standalone via :meth:`OptimizationManager.provider_pool` for future use —
e.g. if oi-harness ever accepts an injected client factory, or for the
probe/prewarm paths.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

#: Factory invoked as ``factory(provider, model)``; may be sync or async.
ClientFactory = Callable[[str, str], Any]

#: How many idle connections pre-warm keeps ready per (provider, model).
PREWARM_IDLE_COUNT = 3


@dataclass
class _PoolEntry:
    client: Any
    in_use: int = 0


@dataclass
class ProviderConnectionPool:
    """Cache LLM clients per ``(provider, model)`` with idle pre-warming."""

    prewarm_idle_count: int = PREWARM_IDLE_COUNT
    _entries: dict[tuple[str, str], _PoolEntry] = field(
        default_factory=dict, init=False, repr=False
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _prewarm_tasks: set[asyncio.Task[None]] = field(
        default_factory=set, init=False, repr=False
    )

    def _key(self, provider: str, model: str) -> tuple[str, str]:
        return (provider.strip().lower(), model.strip())

    async def _build(self, factory: ClientFactory, provider: str, model: str) -> Any:
        client = factory(provider, model)
        if asyncio.iscoroutine(client):
            client = await client
        return client

    async def get_or_create(
        self, provider: str, model: str, factory: ClientFactory
    ) -> Any:
        """Return the cached client for ``(provider, model)``, creating it once."""
        key = self._key(provider, model)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                client = await self._build(factory, provider, model)
                entry = _PoolEntry(client=client)
                self._entries[key] = entry
            entry.in_use += 1
            return entry.client

    async def release(self, provider: str, model: str) -> None:
        """Mark one use of the cached client as finished (best-effort)."""
        key = self._key(provider, model)
        async with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry.in_use > 0:
                entry.in_use -= 1

    def prewarm(
        self,
        provider: str,
        model: str,
        factory: ClientFactory,
        *,
        count: int | None = None,
    ) -> None:
        """Warm ``count`` idle clients in the background (fire-and-forget).

        Safe to call at startup: the work happens in a background task and
        never blocks the caller. Duplicate pre-warm requests for the same key
        are coalesced.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("provider_pool: no running loop; skipping prewarm")
            return
        key = self._key(provider, model)
        if key in self._entries:
            return  # already warm

        async def _warm() -> None:
            try:
                await self.get_or_create(provider, model, factory)
                await self.release(provider, model)
            except Exception:
                logger.exception("provider_pool: prewarm failed for %s/%s", provider, model)

        task = loop.create_task(_warm())
        self._prewarm_tasks.add(task)
        task.add_done_callback(self._prewarm_tasks.discard)

    async def evict(self, provider: str, model: str) -> None:
        """Drop the cached client (e.g. after auth failure); closes if closable."""
        key = self._key(provider, model)
        async with self._lock:
            entry = self._entries.pop(key, None)
        if entry is None:
            return
        close = getattr(entry.client, "aclose", None) or getattr(entry.client, "close", None)
        if close is not None:
            try:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("provider_pool: error closing evicted client")

    async def close_all(self) -> None:
        """Close every cached client and cancel pending pre-warm tasks."""
        for task in list(self._prewarm_tasks):
            task.cancel()
        async with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
        for entry in entries:
            close = getattr(entry.client, "aclose", None) or getattr(
                entry.client, "close", None
            )
            if close is not None:
                try:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("provider_pool: error closing pooled client")

    @property
    def cached_count(self) -> int:
        """Number of cached (provider, model) clients (introspection)."""
        return len(self._entries)
