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
from oi.infra.optimizations.chat_resilience import (
    BoundedCache,
    RateLimiter,
    TokenBucketRateLimiter,
    get_rate_limiter,
    get_token_bucket,
    is_context_length_error,
    is_rate_limit_error,
    parse_retry_after,
    register_model_rpm,
    resilient_stream,
    resolve_model_rpm,
    retry_delay_seconds,
)
from oi.infra.optimizations.context_compressor import (
    compress_for_retry,
    context_window_for_model,
    dedup_system_prompts,
    estimate_tokens,
    fit_messages_to_window,
    register_model_window,
    resolve_context_window,
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
    "BoundedCache",
    "Intent",
    "LatencyTracker",
    "MmapHistoryReader",
    "OptimizationManager",
    "RateLimiter",
    "RoutingDecision",
    "SmartAutoRouter",
    "StreamPipeline",
    "ThreadContextStore",
    "TokenBucketRateLimiter",
    "classify_intent",
    "compress_for_retry",
    "compress_request_messages",
    "configure",
    "context_window_for_model",
    "dedup_system_prompts",
    "default_cache_dir",
    "estimate_tokens",
    "fit_messages_to_window",
    "flush_batch",
    "get_manager",
    "get_rate_limiter",
    "get_token_bucket",
    "invalidate_thread",
    "is_context_length_error",
    "is_rate_limit_error",
    "maybe_batch_flush",
    "parse_retry_after",
    "prewarm_harness_factory",
    "record_turn_latency",
    "register_model_rpm",
    "register_model_window",
    "resolve_context_window",
    "resolve_model_rpm",
    "resilient_stream",
    "reset_manager",
    "retry_delay_seconds",
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
