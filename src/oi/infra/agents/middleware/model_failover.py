"""Health-aware and context-safe model failover for AUTO-routed turns."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal, cast

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.agents.middleware.model_retry import ModelRetryMiddleware
from langchain_core.messages import AIMessage
from langgraph.errors import GraphBubbleUp
from oi_harness.context_usage import breakdown_from_model_request
from oi_harness.middleware.runtime import runtime_config
from oi_harness.middleware.turn_model import latest_human_needs_multimodal

from oi.i18n.domains.stream import model_retry_failure_prompt
from oi.infra.agents.providers.health import (
    FailureScope,
    ModelHealthRegistry,
    classify_model_failure,
)
from oi.infra.agents.providers.store import AutoRouteCandidate
from oi.infra.agents.settings.runtime_limits import CONFIGURABLE_MAX_INPUT_TOKENS

logger = logging.getLogger(__name__)

AUTO_ROUTE_CONFIG_KEY = "oi_auto_route"
_CONTEXT_SAFETY_RATIO = 0.9


def _configurable(request: ModelRequest[Any]) -> dict[str, Any]:
    config = runtime_config(request)
    configurable = config.get("configurable") if isinstance(config, dict) else None
    return configurable if isinstance(configurable, dict) else {}


def _estimated_input_tokens(request: ModelRequest[Any]) -> int:
    return sum(breakdown_from_model_request(request).values())


def _fits_context(
    candidate: AutoRouteCandidate,
    estimated_tokens: int,
    route_cap: int | None = None,
) -> bool:
    cap = candidate.max_input_tokens
    if route_cap is not None and route_cap > 0:
        cap = min(cap, route_cap) if cap > 0 else route_cap
    if cap <= 0:
        return True
    return estimated_tokens <= int(cap * _CONTEXT_SAFETY_RATIO)


def _is_rate_limit(exc: Exception) -> bool:
    """True when *exc* is a provider rate-limit (HTTP 429).

    Primary signal is Octop's message-based classifier. Structured SDK
    errors whose message lacks "429" are covered by walking the cause chain
    for a ``status_code == 429`` attribute.
    """
    if classify_model_failure(exc).kind == "rate_limit":
        return True
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "status_code", None) == 429:
            return True
        current = current.__cause__ or current.__context__
    return False


class SafeModelFailoverMiddleware(AgentMiddleware[Any, Any]):
    """Retry one model, then switch for AUTO turns on safe failure classes.

    Pinned (explicitly chosen) models also switch, but only on rate limits
    (429) — the user chose that model, so other failures stay on it.
    At most ``max_models`` distinct models are tried per model call.
    """

    def __init__(
        self,
        *,
        health: ModelHealthRegistry,
        candidates: Callable[[str, bool], Sequence[AutoRouteCandidate]],
        model_for_ref: Callable[[str], Any],
        max_retries: int,
        initial_delay: float,
        max_delay: float,
        on_failure: Callable[[Exception], str] | Literal["error"] | None = None,
        max_models: int = 3,
    ) -> None:
        super().__init__()
        self._health = health
        self._candidates = candidates
        self._model_for_ref = model_for_ref
        self._on_failure = on_failure
        self._max_models = max(1, max_models)
        self._retry = ModelRetryMiddleware(
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay,
            on_failure="error",
        )

    def _failure_response(self, exc: Exception) -> ModelResponse[Any]:
        if self._on_failure == "error":
            raise exc
        content = (
            self._on_failure(exc)
            if self._on_failure is not None
            else model_retry_failure_prompt(exc, "en")
        )
        return ModelResponse(result=[AIMessage(content=content)])

    def _route(self, request: ModelRequest[Any]) -> tuple[str, bool]:
        configurable = _configurable(request)
        ref = configurable.get("model")
        return (
            ref.strip() if isinstance(ref, str) else "",
            configurable.get(AUTO_ROUTE_CONFIG_KEY) is True,
        )

    def _fallbacks(self, request: ModelRequest[Any], current_ref: str) -> list[AutoRouteCandidate]:
        needs_multimodal = latest_human_needs_multimodal(list(request.messages or []))
        estimated = _estimated_input_tokens(request)
        raw_route_cap = _configurable(request).get(CONFIGURABLE_MAX_INPUT_TOKENS)
        route_cap = raw_route_cap if isinstance(raw_route_cap, int) else None
        return [
            candidate
            for candidate in self._candidates(current_ref, needs_multimodal)
            if candidate.ref != current_ref
            and self._health.is_routable(candidate.ref)
            and _fits_context(candidate, estimated, route_cap)
        ]

    def _attempts(
        self, request: ModelRequest[Any], current_ref: str, automatic: bool
    ) -> list[tuple[str, Any]]:
        """Ordered models to try: current model first, then healthy fallbacks.

        Fallbacks are always built (not only for AUTO turns) so a pinned
        model that hits a rate limit can fail over too. The list is capped
        at ``max_models`` distinct models per model call, so one turn never
        fans out across every configured provider. Fallback candidates
        already carry the same messages (same context) and are filtered to
        healthy models whose context window fits the request.
        """
        attempts: list[tuple[str, Any]] = []
        if not automatic or not current_ref or self._health.begin_attempt(current_ref):
            attempts.append((current_ref, request.model))
        if current_ref:
            attempts.extend(
                (candidate.ref, self._model_for_ref(candidate.ref))
                for candidate in self._fallbacks(request, current_ref)
            )
        return attempts[: self._max_models]

    def _record_failure(self, ref: str, exc: Exception) -> bool:
        decision = classify_model_failure(exc)
        if decision.scope is not FailureScope.NONE:
            self._health.record_failure(ref, kind=decision.kind, scope=decision.scope)
        return decision.failover

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any]:
        current_ref, automatic = self._route(request)
        last_error: Exception | None = None
        attempts = self._attempts(request, current_ref, automatic)

        for ref, model in attempts:
            if automatic and ref != current_ref and not self._health.begin_attempt(ref):
                continue
            routed = request if model is request.model else request.override(model=model)
            if automatic and ref and ref != current_ref:
                _configurable(request)["model"] = ref
            try:
                response = self._retry.wrap_model_call(routed, handler)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                last_error = exc
                may_failover = self._record_failure(ref, exc)
                # Pinned models fail over only on rate limits (429): the user
                # chose that model, so other failures stay on it. AUTO turns
                # keep the previous behaviour for every failover-eligible class.
                if not may_failover or (not automatic and not _is_rate_limit(exc)):
                    return self._failure_response(exc)
                logger.warning("AUTO model route failed; trying next candidate: model=%s", ref)
                continue
            self._health.record_success(ref)
            return cast(ModelResponse[Any], response)

        return self._failure_response(
            last_error or RuntimeError("no healthy AUTO model is available")
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        current_ref, automatic = self._route(request)
        last_error: Exception | None = None
        attempts = self._attempts(request, current_ref, automatic)

        for ref, model in attempts:
            if automatic and ref != current_ref and not self._health.begin_attempt(ref):
                continue
            routed = request if model is request.model else request.override(model=model)
            if automatic and ref and ref != current_ref:
                _configurable(request)["model"] = ref
            try:
                response = await self._retry.awrap_model_call(routed, handler)
            except GraphBubbleUp:
                raise
            except Exception as exc:
                last_error = exc
                may_failover = self._record_failure(ref, exc)
                # Pinned models fail over only on rate limits (429): the user
                # chose that model, so other failures stay on it. AUTO turns
                # keep the previous behaviour for every failover-eligible class.
                if not may_failover or (not automatic and not _is_rate_limit(exc)):
                    return self._failure_response(exc)
                logger.warning("AUTO model route failed; trying next candidate: model=%s", ref)
                continue
            self._health.record_success(ref)
            return cast(ModelResponse[Any], response)

        return self._failure_response(
            last_error or RuntimeError("no healthy AUTO model is available")
        )


__all__ = [
    "AUTO_ROUTE_CONFIG_KEY",
    "AutoRouteCandidate",
    "SafeModelFailoverMiddleware",
]
