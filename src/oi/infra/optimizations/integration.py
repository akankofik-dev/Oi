"""Central manager for chat-pipeline optimizations.

:class:`OptimizationManager` owns every optimization module and exposes them
through lazy properties, so merely configuring the manager costs nothing:
modules are only instantiated when their feature flag is ON and the code path
actually runs.

Process wiring:

* ``server.py`` calls :func:`configure` once at startup with
  ``config.chat`` (:class:`oi.config.ChatOptimizations`), then
  :meth:`OptimizationManager.schedule_prewarm` with the ``AgentManager``
  (warms the harness model cache in the background when the
  ``provider_prewarm`` flag is ON).
* Hot paths (``processor.py``, ``stream_project.py``, ``harness_request.py``)
  use the module-level helpers :func:`maybe_batch_flush`,
  :func:`flush_batch`, :func:`record_turn_latency` and
  :meth:`OptimizationManager.compress_messages`,
  which are no-ops delegating to the original behaviour when the manager is
  unconfigured or the relevant flag is OFF.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from oi.infra.optimizations.auto_router import SmartAutoRouter
from oi.infra.optimizations.batch_writer import BatchHistoryWriter, FlushFn
from oi.infra.optimizations.context_compressor import compress_request_messages
from oi.infra.optimizations.mmap_history import MmapHistoryReader
from oi.infra.optimizations.provider_pool import schedule_prewarm as _schedule_prewarm
from oi.infra.optimizations.stream_pipeline import StreamPipeline

logger = logging.getLogger(__name__)

_MANAGER: OptimizationManager | None = None


class OptimizationManager:
    """Holds feature flags and lazily-built optimization modules."""

    def __init__(self, flags: Any) -> None:
        # ``flags`` is oi.config.ChatOptimizations; typed as Any to keep this
        # package free of config imports (no circular imports).
        self.flags = flags
        self._batch_writer: BatchHistoryWriter | None = None
        self._stream_pipeline: StreamPipeline | None = None
        self._auto_router: SmartAutoRouter | None = None
        self._mmap_reader: MmapHistoryReader | None = None

    # -- lazy module access -------------------------------------------------

    @property
    def batch_writer(self) -> BatchHistoryWriter:
        if self._batch_writer is None:
            self._batch_writer = BatchHistoryWriter()
        return self._batch_writer

    def schedule_prewarm(self, agent_manager: Any) -> None:
        """Warm the harness model cache in the background (flag-gated).

        No-op unless the ``provider_prewarm`` flag is ON. Safe to call at
        server startup: the work runs in a background task and never blocks
        the caller. See :mod:`oi.infra.optimizations.provider_pool` for why
        pre-warming targets the harness factory cache directly.
        """
        if not bool(getattr(self.flags, "provider_prewarm", False)):
            return
        _schedule_prewarm(agent_manager)

    @property
    def stream_pipeline(self) -> StreamPipeline:
        if self._stream_pipeline is None:
            self._stream_pipeline = StreamPipeline()
        return self._stream_pipeline

    def fast_lane_decision(self, text: str, *, thread_used_tools: bool) -> Any | None:
        """Suggest-mode fast-lane decision for one turn (never applied here).

        Returns ``None`` unless the ``fast_lane`` flag is ON and a fast
        model ref is configured via ``fast_lane_model``. Callers log the
        decision; applying it (actually serving the turn from the fast
        model) is a separate, later step.
        """
        if not bool(getattr(self.flags, "fast_lane", False)):
            return None
        fast_ref = str(getattr(self.flags, "fast_lane_model", "") or "").strip()
        if not fast_ref:
            return None
        from oi.infra.optimizations.fast_lane import decide_fast_lane

        return decide_fast_lane(
            text,
            thread_used_tools=thread_used_tools,
            fast_model_ref=fast_ref,
        )

    @property
    def auto_router(self) -> SmartAutoRouter:
        if self._auto_router is None:
            mode = getattr(self.flags, "auto_router_mode", "suggest")
            self._auto_router = SmartAutoRouter(mode=mode)
        return self._auto_router

    def mmap_reader(self, cache_dir: str) -> MmapHistoryReader:
        if self._mmap_reader is None:
            self._mmap_reader = MmapHistoryReader(cache_dir)
        return self._mmap_reader

    # -- flag-gated helpers used by hot paths -------------------------------

    def compress_messages(
        self,
        messages: list[Any],
        *,
        context_window_tokens: int | None = None,
    ) -> list[Any]:
        """Apply enabled compression passes; identity when all flags OFF."""
        smart = bool(getattr(self.flags, "smart_context_switch", False))
        semantic = bool(getattr(self.flags, "semantic_compress", False))
        if not (smart or semantic):
            return messages
        return compress_request_messages(
            messages,
            context_window_tokens=context_window_tokens,
            smart_switch=smart,
            semantic=semantic,
        )

    def any_enabled(self) -> bool:
        for name in (
            "batch_db_writes",
            "async_history",
            "smart_context_switch",
            "semantic_compress",
            "auto_router",
            "zero_copy_stream",
            "mmap_history",
            "provider_prewarm",
            "fast_lane",
        ):
            if getattr(self.flags, name, False):
                return True
        return False


def configure(flags: Any) -> OptimizationManager:
    """Install the process-global manager (called once at server startup)."""
    global _MANAGER
    _MANAGER = OptimizationManager(flags)
    logger.info(
        "optimizations configured (any_enabled=%s)", _MANAGER.any_enabled()
    )
    return _MANAGER


def get_manager() -> OptimizationManager | None:
    """Return the configured manager, or None before server startup."""
    return _MANAGER


def reset_manager() -> None:
    """Clear the global manager (tests only)."""
    global _MANAGER
    _MANAGER = None


def _batching_on(manager: OptimizationManager) -> bool:
    """True when either batching flag is enabled (both gate the batch writer)."""
    return bool(manager.flags.batch_db_writes or manager.flags.async_history)


async def maybe_batch_flush(tracker: Any, flush_fn: FlushFn) -> None:
    """Per-chunk flush hook: batched when the flag is ON, direct otherwise.

    Drop-in replacement for ``await flush_tracker(history_tracker)``.
    """
    manager = _MANAGER
    if manager is None or not _batching_on(manager):
        await flush_fn(tracker)
        return
    await manager.batch_writer.maybe_flush(tracker, flush_fn)


async def flush_batch(tracker: Any, flush_fn: FlushFn | None = None) -> None:
    """Force-flush a tracker's pending batch (stream end / disconnect).

    No-op when the manager is unconfigured or batching is OFF — callers must
    still persist through their normal path in that case. ``flush_fn``
    defaults to ``oi.infra.history.recorder.flush_tracker`` (imported lazily
    so this package stays importable without the history subsystem).
    """
    manager = _MANAGER
    if manager is None or not _batching_on(manager):
        return
    if flush_fn is None:
        from oi.infra.history.recorder import flush_tracker  # noqa: PLC0415

        flush_fn = flush_tracker
    await manager.batch_writer.flush(tracker, flush_fn)
    manager.batch_writer.drop(tracker)


def record_turn_latency(agent_id: str, seconds: float) -> None:
    """Feed a completed turn's latency into the auto-router's tracker.

    Flag-gated: no-op unless the ``auto_router`` flag is ON. Best-effort and
    never raises — latency data is advisory only. Call at turn end (after the
    agent that actually handled the turn is known) so ``auto`` mode can
    prefer the fastest known agent for future turns.
    """
    manager = _MANAGER
    if manager is None or not getattr(manager.flags, "auto_router", False):
        return
    try:
        manager.auto_router.record_latency(agent_id, seconds)
    except Exception:
        logger.exception("record_turn_latency failed (non-fatal)")


FlushFnT = Callable[[Any], Awaitable[None]]
