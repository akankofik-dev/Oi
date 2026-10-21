"""Rolling usage ledger with provider-learned rate-limit ceilings.

Free-tier providers rarely publish their real limits, and the limits that
matter (per model, per key) are often stricter than the documented ones.
This ledger follows the FreeLLMAPI pattern: count requests in rolling
windows, and *learn* each model's ceilings from the provider's own 429
responses (``Retry-After`` / ``x-ratelimit-*`` headers, or "try again in
Xs" bodies). Availability is then checked *before* dispatch, so routing
moves on before the limit is hit instead of only reacting afterwards.

Process-local and deliberately conservative: an unknown model is always
available, learned ceilings only ever restrict, and all state clears on
restart (a fresh process gives every model a fresh chance, matching
:class:`oi.infra.agents.providers.health.ModelHealthRegistry`).
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

_MINUTE_S = 60.0
_DAY_S = 86_400.0

_RETRY_AFTER_MSG = re.compile(r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds|m|min|minutes)", re.I)
_LIMIT_MSG = re.compile(r"(?:limit|quota)[^0-9]{0,24}(\d[\d,]*)", re.I)


@dataclass(frozen=True)
class RateLimitHint:
    """Limit information extracted from one provider error."""

    retry_after_s: float | None = None
    rpm: int | None = None
    rpd: int | None = None


def _header(headers: object, name: str) -> str | None:
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    try:
        value = getter(name) or getter(name.title())
    except Exception:
        return None
    return str(value) if value is not None else None


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value.replace(",", "")))
    except (TypeError, ValueError):
        return None


def _as_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_rate_limit_hint(exc: BaseException) -> RateLimitHint | None:
    """Best-effort extraction of limit info from a provider exception.

    Sources, in order: the HTTP response attached to the exception
    (``Retry-After``, ``x-ratelimit-limit-requests``,
    ``x-ratelimit-limit-requests-per-day`` / ``-per-minute`` variants),
    then common phrasings in the error message itself. Returns ``None``
    when the error carries no usable hint.
    """
    retry_after: float | None = None
    rpm: int | None = None
    rpd: int | None = None

    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        retry_after = _as_seconds(_header(headers, "retry-after"))
        rpm = _as_int(
            _header(headers, "x-ratelimit-limit-requests")
            or _header(headers, "x-ratelimit-limit-requests-per-minute")
            or _header(headers, "x-ratelimit-requests-limit")
        )
        rpd = _as_int(
            _header(headers, "x-ratelimit-limit-requests-per-day")
            or _header(headers, "x-ratelimit-requests-per-day")
        )

    message = str(exc)
    if retry_after is None:
        match = _RETRY_AFTER_MSG.search(message)
        if match:
            value = float(match.group(1))
            unit = match.group(2).lower()
            if unit == "ms":
                retry_after = value / 1000.0
            elif unit.startswith("m"):
                retry_after = value * 60.0
            else:
                retry_after = value
    if rpm is None and ("per minute" in message.lower() or "rpm" in message.lower()):
        match = _LIMIT_MSG.search(message)
        if match:
            rpm = _as_int(match.group(1))

    if retry_after is None and rpm is None and rpd is None:
        return None
    return RateLimitHint(retry_after_s=retry_after, rpm=rpm, rpd=rpd)


@dataclass
class _RefState:
    requests_minute: deque[float]
    requests_day: deque[float]
    blocked_until: float = 0.0
    rpm_ceiling: int | None = None
    rpd_ceiling: int | None = None


class QuotaLedger:
    """Per-model request ledger + learned ceilings, checked pre-dispatch."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._refs: dict[str, _RefState] = {}

    def _state(self, ref: str) -> _RefState:
        state = self._refs.get(ref)
        if state is None:
            state = _RefState(requests_minute=deque(), requests_day=deque())
            self._refs[ref] = state
        return state

    @staticmethod
    def _prune(window: deque[float], now: float, span: float) -> None:
        cutoff = now - span
        while window and window[0] <= cutoff:
            window.popleft()

    def record_request(self, ref: str) -> None:
        """Count one dispatched model call against *ref*'s windows."""
        now = self._clock()
        with self._lock:
            state = self._state(ref)
            state.requests_minute.append(now)
            state.requests_day.append(now)

    def learn_from_exception(self, ref: str, exc: BaseException) -> RateLimitHint | None:
        """Fold any limit hint carried by *exc* into *ref*'s ceilings.

        Learned ceilings only ever tighten (a provider reporting a lower
        limit than previously learned wins). A ``Retry-After`` parks the
        model until the provider says it resets.
        """
        hint = parse_rate_limit_hint(exc)
        if hint is None:
            return None
        now = self._clock()
        with self._lock:
            state = self._state(ref)
            if hint.retry_after_s is not None:
                state.blocked_until = max(state.blocked_until, now + hint.retry_after_s)
            if hint.rpm is not None:
                state.rpm_ceiling = (
                    hint.rpm if state.rpm_ceiling is None else min(state.rpm_ceiling, hint.rpm)
                )
            if hint.rpd is not None:
                state.rpd_ceiling = (
                    hint.rpd if state.rpd_ceiling is None else min(state.rpd_ceiling, hint.rpd)
                )
        return hint

    def is_available(self, ref: str) -> bool:
        """True when *ref* may be dispatched now under its learned limits."""
        now = self._clock()
        with self._lock:
            state = self._refs.get(ref)
            if state is None:
                return True
            if now < state.blocked_until:
                return False
            if state.rpm_ceiling is not None:
                self._prune(state.requests_minute, now, _MINUTE_S)
                if len(state.requests_minute) >= state.rpm_ceiling:
                    return False
            if state.rpd_ceiling is not None:
                self._prune(state.requests_day, now, _DAY_S)
                if len(state.requests_day) >= state.rpd_ceiling:
                    return False
            return True

    def snapshot(self, ref: str) -> dict[str, object]:
        """Return a small UI/log-safe view of one ref's quota state."""
        now = self._clock()
        with self._lock:
            state = self._refs.get(ref)
            if state is None:
                return {"available": True, "rpm_ceiling": None, "rpd_ceiling": None}
            self._prune(state.requests_minute, now, _MINUTE_S)
            self._prune(state.requests_day, now, _DAY_S)
            return {
                "available": self.is_available(ref),
                "rpm_ceiling": state.rpm_ceiling,
                "rpd_ceiling": state.rpd_ceiling,
                "requests_last_minute": len(state.requests_minute),
                "requests_last_day": len(state.requests_day),
                "blocked_until": state.blocked_until or None,
            }


__all__ = [
    "QuotaLedger",
    "RateLimitHint",
    "parse_rate_limit_hint",
]
