"""Model routing events: middleware -> stream notifications.

The failover middleware runs deep inside the harness model-call stack, far
from the code that streams chunks to the user. This module bridges the gap
with a :class:`contextvars.ContextVar`: middleware appends
:class:`RoutingEvent` records during a turn, and
:meth:`AgentManager.stream` drains them afterwards and re-emits them as
``model_routing`` stream chunks the frontend can render.

Event kinds
-----------
- ``"selected"``: a model call succeeded; ``model`` is the ref that actually
  answered. The *last* selected event of a turn is the turn's effective
  model (used by the UI model badge).
- ``"switched"``: the active model changed mid-turn; ``from_model`` ->
  ``model``, ``reason`` is ``"failed"`` (previous candidate errored) or
  ``"slow"`` (previous candidate was too slow).
- ``"slow"``: a model call succeeded but took longer than the configured
  slow threshold; ``to_model`` names the faster alternative that will be
  preferred next.
- ``"retrying"``: every candidate failed this cycle; the router waits
  ``next_retry_in_s`` and tries again (cycle N). Only the user cancelling
  the stream stops the loop.

All emission is fail-open: outside an active
:func:`routing_event_scope` events are silently dropped, and emission never
raises.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class RoutingEvent:
    """One model-routing observation from a middleware."""

    kind: str  # "selected" | "switched" | "slow" | "retrying"
    model: str | None = None
    from_model: str | None = None
    to_model: str | None = None
    reason: str | None = None  # "failed" | "slow" | ...
    detail: str | None = None
    latency_s: float | None = None
    cycle: int | None = None
    next_retry_in_s: float | None = None


@dataclass
class RoutingReport:
    """All routing events collected during one stream turn."""

    events: list[RoutingEvent] = field(default_factory=list)
    effective_model: str | None = None


_ROUTING_SCOPE: contextvars.ContextVar[RoutingReport | None] = (
    contextvars.ContextVar("oi_model_routing", default=None)
)


@contextmanager
def routing_event_scope() -> Iterator[RoutingReport]:
    """Collect routing events for the enclosed stream turn.

    The middleware and the stream run in the same asyncio task, so the
    ContextVar set here is visible inside ``awrap_model_call``.
    """
    report = RoutingReport()
    token = _ROUTING_SCOPE.set(report)
    try:
        yield report
    finally:
        _ROUTING_SCOPE.reset(token)


def emit_routing_event(
    kind: str,
    *,
    model: str | None = None,
    from_model: str | None = None,
    to_model: str | None = None,
    reason: str | None = None,
    detail: str | None = None,
    latency_s: float | None = None,
    cycle: int | None = None,
    next_retry_in_s: float | None = None,
) -> None:
    """Append a routing event to the active scope (fail-open)."""
    try:
        report = _ROUTING_SCOPE.get()
    except Exception:
        return
    if report is None:
        return
    try:
        report.events.append(
            RoutingEvent(
                kind=kind,
                model=model,
                from_model=from_model,
                to_model=to_model,
                reason=reason,
                detail=detail,
                latency_s=latency_s,
                cycle=cycle,
                next_retry_in_s=next_retry_in_s,
            )
        )
        if kind == "selected" and model:
            report.effective_model = model
    except Exception:
        pass  # never break a model call


def current_routing_report() -> RoutingReport | None:
    """Return the active routing report, or None outside a scope."""
    try:
        return _ROUTING_SCOPE.get()
    except Exception:
        return None


def routing_report_to_chunks(report: RoutingReport) -> list[dict[str, Any]]:
    """Convert a drained report into ``model_routing`` stream chunks.

    The effective model goes first so frontends can stamp it onto the
    turn's message metadata; user-visible notifications follow in order.
    ``"selected"`` events are summarized by the leading chunk.
    """
    chunks: list[dict[str, Any]] = []
    if report.effective_model:
        chunks.append(
            {
                "type": "model_routing",
                "event": "selected",
                "model": report.effective_model,
            }
        )
    for ev in report.events:
        if ev.kind == "selected":
            continue
        chunk: dict[str, Any] = {"type": "model_routing", "event": ev.kind}
        if ev.model is not None:
            chunk["model"] = ev.model
        if ev.from_model is not None:
            chunk["from_model"] = ev.from_model
        if ev.to_model is not None:
            chunk["to_model"] = ev.to_model
        if ev.reason is not None:
            chunk["reason"] = ev.reason
        if ev.detail is not None:
            chunk["detail"] = ev.detail
        if ev.latency_s is not None:
            chunk["latency_s"] = round(ev.latency_s, 1)
        if ev.cycle is not None:
            chunk["cycle"] = ev.cycle
        if ev.next_retry_in_s is not None:
            chunk["next_retry_in_s"] = round(ev.next_retry_in_s, 1)
        chunks.append(chunk)
    return chunks


__all__ = [
    "RoutingEvent",
    "RoutingReport",
    "current_routing_report",
    "emit_routing_event",
    "routing_event_scope",
    "routing_report_to_chunks",
]
