"""Context guard middleware: warn at 75%, auto-suggest compact at 90%.

This middleware checks the context window usage before each model call.
It does NOT modify the request - it only logs warnings to help prevent
the "context 100% full" errors.

Thresholds:
- 75%: WARNING - log that context is getting full, suggest compacting
- 90%: CRITICAL - log that auto-compact is recommended, suggest fork thread

The actual compaction is handled by the harness SummarizationMiddleware
or the manual /compact command. This middleware just provides early warnings.

Safe: read-only, never modifies the request, fail-open.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

logger = logging.getLogger(__name__)

# Thresholds for context usage warnings
WARN_THRESHOLD = 0.75  # 75% - warn user
CRITICAL_THRESHOLD = 0.90  # 90% - strongly suggest compact/fork


def _get_usage_ratio(request: ModelRequest[Any]) -> float | None:
    """Extract context usage ratio from request, if available.

    Returns ratio (0.0-1.0) or None if usage data not available.
    """
    try:
        # Try to get usage from request
        usage = getattr(request, "usage", None)
        if usage is None:
            return None

        used = int(getattr(usage, "used_tokens", 0) or 0)
        max_tokens = int(getattr(usage, "max_tokens", 0) or 0)

        if max_tokens <= 0 or used <= 0:
            return None

        return min(used / max_tokens, 1.0)
    except Exception:
        return None


def _check_and_warn(ratio: float | None) -> None:
    """Log warnings based on context usage ratio. Fail-open."""
    if ratio is None:
        return

    try:
        if ratio >= CRITICAL_THRESHOLD:
            logger.warning(
                "Context usage at %.1f%% (>=90%%) - CRITICAL! "
                "Consider running /compact or forking to a new thread "
                "to avoid model errors.",
                ratio * 100,
            )
        elif ratio >= WARN_THRESHOLD:
            logger.warning(
                "Context usage at %.1f%% (>=75%%) - WARNING! "
                "Context is getting full. Consider compacting soon.",
                ratio * 100,
            )
    except Exception:
        # Never break the request on logging errors
        pass


class ContextGuardMiddleware(AgentMiddleware[Any, Any]):
    """Warn when context usage exceeds thresholds.

    This is a read-only middleware that checks context usage before
    each model call and logs warnings. It never modifies the request.

    Thresholds:
    - 75%: WARNING level log
    - 90%: CRITICAL level log with suggestion to compact/fork
    """

    def __init__(
        self,
        warn_threshold: float = WARN_THRESHOLD,
        critical_threshold: float = CRITICAL_THRESHOLD,
        enabled: bool = True,
    ) -> None:
        self.warn_threshold = warn_threshold
        self.critical_threshold = critical_threshold
        self.enabled = enabled

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        if self.enabled:
            _check_and_warn(_get_usage_ratio(request))
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        if self.enabled:
            _check_and_warn(_get_usage_ratio(request))
        return await handler(request)


__all__ = [
    "WARN_THRESHOLD",
    "CRITICAL_THRESHOLD",
    "ContextGuardMiddleware",
]
