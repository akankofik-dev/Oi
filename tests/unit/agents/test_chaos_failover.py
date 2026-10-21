"""Chaos suite for the in-app chat resilience layer.

One test per failure mode the layer promises to survive (SOLUSI-CHAT-100
matrix, in-repo rows). Fake models fail in specific ways; the assertions
check the *turn outcome* — answered by a fallback, ended clearly with a
bounded number of attempts, or the dead model quarantined — never a hang
and never an unbounded fan-out.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage

from oi.infra.agents.middleware import model_failover
from oi.infra.agents.middleware.model_failover import (
    AutoRouteCandidate,
    SafeModelFailoverMiddleware,
)
from oi.infra.agents.providers.health import ModelHealthRegistry
from oi.infra.agents.providers.quota import QuotaLedger


def _model(ref: str, cap: int) -> SimpleNamespace:
    provider, _, model = ref.partition("/")
    return SimpleNamespace(
        model=ref,
        provider=provider,
        model_name=model,
        profile={"max_input_tokens": cap},
    )


def _middleware(
    monkeypatch,
    *,
    models: dict[str, SimpleNamespace],
    candidates: list[AutoRouteCandidate],
    automatic: bool = True,
    quota: QuotaLedger | None = None,
    health: ModelHealthRegistry | None = None,
) -> tuple[SafeModelFailoverMiddleware, ModelHealthRegistry, dict]:
    configurable = {"model": "p/a", "oi_auto_route": automatic}
    health = health or ModelHealthRegistry(clock=lambda: 100.0)
    middleware = SafeModelFailoverMiddleware(
        health=health,
        candidates=lambda _current, _vision: candidates,
        model_for_ref=models.__getitem__,
        max_retries=1,
        initial_delay=0,
        max_delay=0,
        on_failure="error",
        quota=quota,
    )
    monkeypatch.setattr(model_failover, "_configurable", lambda _request: configurable)
    return middleware, health, configurable


def _handler(failures: dict[str, BaseException], attempts: list[str]):
    async def handler(request: ModelRequest) -> ModelResponse:
        ref = request.model.model
        attempts.append(ref)
        exc = failures.get(ref)
        if exc is not None:
            raise exc
        return ModelResponse(result=[AIMessage(content=f"ok from {ref}")])

    return handler


def _request(models: dict[str, SimpleNamespace], text: str = "hello") -> ModelRequest:
    return ModelRequest(model=models["p/a"], messages=[HumanMessage(content=text)])


@pytest.mark.asyncio
async def test_chaos_429_primary_fails_over_and_provider_quarantined(monkeypatch) -> None:
    models = {"p/a": _model("p/a", 100_000), "q/b": _model("q/b", 100_000)}
    middleware, health, _ = _middleware(
        monkeypatch, models=models, candidates=[AutoRouteCandidate("q/b", 100_000)]
    )
    attempts: list[str] = []
    handler = _handler({"p/a": RuntimeError("HTTP 429 rate limit exceeded")}, attempts)

    response = await middleware.awrap_model_call(_request(models), handler)

    assert response.result[0].content == "ok from q/b"
    # rate limits quarantine the whole provider, not just the one model
    assert health.is_routable("p/a") is False
    assert health.is_routable("p/anything-else") is False
    assert health.is_routable("q/b") is True


@pytest.mark.asyncio
async def test_chaos_all_down_turn_ends_clearly_with_bounded_attempts(monkeypatch) -> None:
    models = {"p/a": _model("p/a", 100_000), "q/b": _model("q/b", 100_000)}
    middleware, _, _ = _middleware(
        monkeypatch, models=models, candidates=[AutoRouteCandidate("q/b", 100_000)]
    )
    attempts: list[str] = []
    handler = _handler(
        {
            "p/a": RuntimeError("HTTP 503 service unavailable"),
            "q/b": RuntimeError("HTTP 503 service unavailable"),
        },
        attempts,
    )

    with pytest.raises(RuntimeError):
        await middleware.awrap_model_call(_request(models), handler)

    # (1 retry + 1) per model x 2 models: bounded, never a hang loop
    assert len(attempts) == 4


@pytest.mark.asyncio
async def test_chaos_quota_exhausted_candidate_skipped_before_dispatch(monkeypatch) -> None:
    models = {
        "p/a": _model("p/a", 100_000),
        "q/b": _model("q/b", 100_000),
        "r/c": _model("r/c", 100_000),
    }
    quota = QuotaLedger(clock=lambda: 100.0)
    quota.learn_from_exception(
        "q/b",
        RuntimeError(
            "HTTP 429",
            # headers carried on the exception object below
        ),
    )
    exc = RuntimeError("HTTP 429 rate limit")
    exc.response = SimpleNamespace(  # type: ignore[attr-defined]
        headers={"x-ratelimit-limit-requests": "1"}
    )
    quota.learn_from_exception("q/b", exc)
    quota.record_request("q/b")  # the one allowed request is spent

    middleware, _, _ = _middleware(
        monkeypatch,
        models=models,
        candidates=[AutoRouteCandidate("q/b", 100_000), AutoRouteCandidate("r/c", 100_000)],
        quota=quota,
    )
    attempts: list[str] = []
    handler = _handler({"p/a": RuntimeError("HTTP 503 service unavailable")}, attempts)

    response = await middleware.awrap_model_call(_request(models), handler)

    assert response.result[0].content == "ok from r/c"
    assert "q/b" not in attempts  # skipped pre-dispatch, never called


@pytest.mark.asyncio
async def test_chaos_unknown_errors_open_short_circuit(monkeypatch) -> None:
    models = {"p/a": _model("p/a", 100_000), "q/b": _model("q/b", 100_000)}
    health = ModelHealthRegistry(
        clock=lambda: 100.0, unknown_threshold=3, unknown_cooldown_s=30.0
    )
    middleware, health, _ = _middleware(
        monkeypatch,
        models=models,
        candidates=[AutoRouteCandidate("q/b", 100_000)],
        health=health,
    )
    attempts: list[str] = []
    handler = _handler({"p/a": RuntimeError("weird upstream glitch xyz")}, attempts)

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await middleware.awrap_model_call(_request(models), handler)

    assert health.is_routable("p/a") is False


@pytest.mark.asyncio
async def test_chaos_small_context_candidate_skipped(monkeypatch) -> None:
    models = {
        "p/a": _model("p/a", 100_000),
        "q/b": _model("q/b", 10),
        "r/c": _model("r/c", 100_000),
    }
    middleware, _, _ = _middleware(
        monkeypatch,
        models=models,
        candidates=[AutoRouteCandidate("q/b", 10), AutoRouteCandidate("r/c", 100_000)],
    )
    attempts: list[str] = []
    handler = _handler({"p/a": RuntimeError("HTTP 503 service unavailable")}, attempts)
    long_text = "word " * 400

    response = await middleware.awrap_model_call(_request(models, long_text), handler)

    assert response.result[0].content == "ok from r/c"
    assert "q/b" not in attempts


@pytest.mark.asyncio
async def test_chaos_pinned_model_switches_on_429(monkeypatch) -> None:
    models = {"p/a": _model("p/a", 100_000), "q/b": _model("q/b", 100_000)}
    middleware, _, _ = _middleware(
        monkeypatch,
        models=models,
        candidates=[AutoRouteCandidate("q/b", 100_000)],
        automatic=False,
    )
    attempts: list[str] = []
    handler = _handler({"p/a": RuntimeError("HTTP 429 rate limit exceeded")}, attempts)

    response = await middleware.awrap_model_call(_request(models), handler)

    assert response.result[0].content == "ok from q/b"


@pytest.mark.asyncio
async def test_chaos_retry_after_learned_from_429(monkeypatch) -> None:
    models = {"p/a": _model("p/a", 100_000), "q/b": _model("q/b", 100_000)}
    quota = QuotaLedger(clock=lambda: 100.0)
    middleware, _, _ = _middleware(
        monkeypatch,
        models=models,
        candidates=[AutoRouteCandidate("q/b", 100_000)],
        quota=quota,
    )
    exc = RuntimeError("HTTP 429 rate limit exceeded")
    exc.response = SimpleNamespace(headers={"retry-after": "120"})  # type: ignore[attr-defined]
    attempts: list[str] = []
    handler = _handler({"p/a": exc}, attempts)

    response = await middleware.awrap_model_call(_request(models), handler)

    assert response.result[0].content == "ok from q/b"
    assert quota.is_available("p/a") is False  # parked by the learned Retry-After
    assert quota.is_available("q/b") is True
