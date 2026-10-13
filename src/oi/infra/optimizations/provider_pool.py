"""L1+L3: provider pre-warming for the harness model cache.

AUDIT NOTE (2026-10-14, multi-repo audit): an earlier revision of this module
implemented its own per-(provider, model) client cache
(``ProviderConnectionPool``). That cache was REMOVED as redundant:
oi-harness's ``ChatModelFactory`` (``oi_harness/llm/factory.py``) already
caches ``BaseChatModel`` instances per ``(provider, model_id)``, shared
across agents through ``AgentManager.shared_factory``. A second Oi-side
cache could not add value — and pre-building its own clients would have
created orphan clients the harness never uses.

What remains valuable, and what this module now does, is PRE-WARMING the
harness cache: building each configured model client once at startup (in a
background task, never blocking boot) so the first real turn never pays
client-construction cost. This uses only public harness APIs
(``shared_factory``, ``list_refs()``, ``get_chat_model()``); no changes to
oi-harness are required.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Hard references to in-flight pre-warm tasks so they are not GC'd.
_PREWARM_TASKS: set[asyncio.Task[None]] = set()


async def prewarm_harness_factory(agent_manager: Any) -> dict[str, str]:
    """Warm the harness ``ChatModelFactory`` cache for every enabled model.

    For each ``provider/model`` ref known to the shared factory, builds (and
    thereby caches) the client via the public ``get_chat_model()`` escape
    hatch. Construction runs in a worker thread so the event loop is never
    blocked; per-ref failures are recorded, never raised.

    Returns a mapping of ``model_ref -> "ok" | "error: ..."``.
    """
    results: dict[str, str] = {}
    try:
        harness_manager = getattr(agent_manager, "harness_manager", None)
        if harness_manager is None:
            logger.debug("provider prewarm: no harness manager available")
            return results
        factory = getattr(harness_manager, "shared_factory", None)
        if factory is None:
            logger.debug("provider prewarm: no shared factory available")
            return results
        refs = factory.list_refs(enabled_only=True)
    except Exception:
        logger.exception("provider prewarm: failed to list model refs")
        return results

    for ref in refs:
        try:
            await asyncio.to_thread(factory.get_chat_model, ref)
            results[ref] = "ok"
        except Exception as exc:
            results[ref] = f"error: {exc}"
            logger.warning("provider prewarm: %s failed: %s", ref, exc)
    return results


def schedule_prewarm(agent_manager: Any) -> None:
    """Fire-and-forget :func:`prewarm_harness_factory` (safe at startup).

    No running event loop (e.g. called outside async context) → silently
    skipped. The task is best-effort: failures are logged, never raised.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("provider prewarm: no running loop; skipping")
        return

    async def _run() -> None:
        try:
            results = await prewarm_harness_factory(agent_manager)
            warmed = sum(1 for v in results.values() if v == "ok")
            logger.info(
                "provider prewarm: warmed %d/%d model refs",
                warmed,
                len(results),
            )
        except Exception:
            logger.exception("provider prewarm: background task failed")

    task = loop.create_task(_run())
    _PREWARM_TASKS.add(task)
    task.add_done_callback(_PREWARM_TASKS.discard)
