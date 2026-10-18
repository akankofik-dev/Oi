"""Simple 429 failover for pinned models (fbb80d3).

When the selected model returns HTTP 429 (rate limit), automatically retry
with up to 2 alternative models (max 3 total) using the same messages.
Only fails over on 429, not on other errors.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

MAX_FAILOVER_MODELS = 3


def _is_rate_limit(exc: BaseException) -> bool:
    """True if exc looks like an HTTP 429 rate-limit error."""
    # Check message text
    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg or "ratelimit" in msg:
        return True
    # Walk the cause chain for status_code == 429
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if getattr(cur, "status_code", None) == 429:
            return True
        # Some SDKs use .status or .code
        if getattr(cur, "status", None) == 429:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def _get_fallback_refs(
    provider_store: Any,
    current_ref: str,
    max_refs: int = 2,
) -> list[str]:
    """Get up to max_refs alternative model refs from enabled providers."""
    refs: list[str] = []
    try:
        for row in provider_store.iter_usable_rows():
            provider_name = getattr(row, "name", "") or ""
            for m in row.get_models():
                # Build ref as "provider/model" (same format as primary)
                model_name = m if isinstance(m, str) else m.get("name", "")
                if not model_name:
                    continue
                ref = f"{provider_name}/{model_name}" if provider_name else model_name
                if ref != current_ref and ref not in refs:
                    refs.append(ref)
                if len(refs) >= max_refs:
                    return refs
    except Exception:
        logger.exception("failover: failed to list fallback models")
    return refs


class FailoverChatModel:
    """Wraps a LangChain chat model with 429 failover.

    Delegates all attribute access to the primary model. Intercepts
    invoke/ainvoke to catch 429 and retry with alternative models.
    """

    def __init__(
        self,
        primary_ref: str,
        primary_model: Any,
        factory: Any,
        provider_store: Any,
    ) -> None:
        self._primary_ref = primary_ref
        self._primary_model = primary_model
        self._factory = factory
        self._provider_store = provider_store

    def _try_invoke(self, method: str, *args: Any, **kwargs: Any) -> Any:
        last_exc: BaseException | None = None
        # Build the attempt list: primary first, then fallbacks
        fallbacks = _get_fallback_refs(
            self._provider_store, self._primary_ref, MAX_FAILOVER_MODELS - 1
        )
        attempts: list[tuple[str, Any]] = [(self._primary_ref, self._primary_model)]
        for ref in fallbacks:
            try:
                model = self._factory.get_chat_model(ref)
                attempts.append((ref, model))
            except Exception:
                logger.warning("failover: could not build model for ref %s", ref)
                continue

        for ref, model in attempts:
            try:
                fn = getattr(model, method)
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if _is_rate_limit(exc):
                    logger.warning(
                        "failover: model %s hit 429, trying next (attempt %d/%d)",
                        ref,
                        attempts.index((ref, model)) + 1,
                        len(attempts),
                    )
                    continue
                # Not a rate limit: don't failover, raise immediately
                raise
        # All attempts exhausted
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("failover: no models available")

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return self._try_invoke("invoke", *args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        # For async, we need to await the underlying ainvoke
        last_exc: BaseException | None = None
        fallbacks = _get_fallback_refs(
            self._provider_store, self._primary_ref, MAX_FAILOVER_MODELS - 1
        )
        attempts: list[tuple[str, Any]] = [(self._primary_ref, self._primary_model)]
        for ref in fallbacks:
            try:
                model = self._factory.get_chat_model(ref)
                attempts.append((ref, model))
            except Exception:
                continue

        for ref, model in attempts:
            try:
                fn = getattr(model, "ainvoke", None) or getattr(model, "invoke")
                result = fn(*args, **kwargs)
                # If it's a coroutine, await it
                if hasattr(result, "__await__"):
                    result = await result
                return result
            except Exception as exc:
                last_exc = exc
                if _is_rate_limit(exc):
                    logger.warning(
                        "failover: model %s hit 429 (async), trying next", ref
                    )
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("failover: no models available")

    def __getattr__(self, name: str) -> Any:
        # Delegate all other attributes to the primary model
        # (e.g., bind_tools, with_config, etc.)
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._primary_model, name)


def build_failover_model(
    ref: str,
    factory: Any,
    provider_store: Any,
) -> Any:
    """Build a chat model with 429 failover wrapper.

    Returns a FailoverChatModel wrapping factory.get_chat_model(ref).
    If factory is unavailable, raises RuntimeError.
    """
    if factory is None:
        raise RuntimeError("provider failover: harness model factory unavailable")
    primary = factory.get_chat_model(ref)
    return FailoverChatModel(
        primary_ref=ref,
        primary_model=primary,
        factory=factory,
        provider_store=provider_store,
    )
