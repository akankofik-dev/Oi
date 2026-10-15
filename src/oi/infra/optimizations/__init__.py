"""Chat pipeline optimizations (L1-L3 + auto-router), all behind feature flags.

Every optimization in this package is inert unless its feature flag is enabled
in :class:`oi.config.ChatOptimizations` (all default OFF). With all flags OFF
the hot-path helpers delegate to the original code paths, so behaviour is
identical to the unoptimized pipeline.

Modules are standalone: importing this package must never pull in
``oi.infra.history``, ``oi.infra.gateway`` or any other heavy subsystem
(no circular imports). Cross-module access goes through the process-global
:class:`OptimizationManager` created by :func:`configure`.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from oi.infra.optimizations.auto_router import (
    Intent,
    LatencyTracker,
    RoutingDecision,
    SmartAutoRouter,
    ThreadContextStore,
    classify_intent,
)
from oi.infra.optimizations.batch_writer import BatchHistoryWriter
from oi.infra.optimizations.context_compressor import (
    context_window_for_model,
    dedup_system_prompts,
    estimate_tokens,
    smart_context_switch,
    summarize_tool_messages,
)
from oi.infra.optimizations.integration import (
    OptimizationManager,
    configure,
    flush_batch,
    get_manager,
    maybe_batch_flush,
    record_turn_latency,
    reset_manager,
)
from oi.infra.optimizations.mmap_history import (
    MmapHistoryReader,
    default_cache_dir,
    invalidate_thread,
)
from oi.infra.optimizations.provider_pool import (
    prewarm_harness_factory,
    schedule_prewarm,
)
from oi.infra.optimizations.stream_pipeline import StreamPipeline

__all__ = [
    "BatchHistoryWriter",
    "Intent",
    "LatencyTracker",
    "MmapHistoryReader",
    "OptimizationManager",
    "RoutingDecision",
    "SmartAutoRouter",
    "StreamPipeline",
    "ThreadContextStore",
    "classify_intent",
    "compress_request_messages",
    "configure",
    "context_window_for_model",
    "dedup_system_prompts",
    "default_cache_dir",
    "estimate_tokens",
    "flush_batch",
    "get_manager",
    "invalidate_thread",
    "maybe_batch_flush",
    "prewarm_harness_factory",
    "record_turn_latency",
    "reset_manager",
    "schedule_prewarm",
    "smart_context_switch",
    "summarize_tool_messages",
]


def compress_request_messages(
    messages: list[Any],
    *,
    context_window_tokens: int | None = None,
) -> list[Any]:
    """Apply flag-gated context compression to an LLM request's messages.

    Returns ``messages`` unchanged when no manager is configured or when
    neither ``smart_context_switch`` nor ``semantic_compress`` is enabled.
    """
    manager = get_manager()
    if manager is None:
        return messages
    return manager.compress_messages(
        messages, context_window_tokens=context_window_tokens
    )
