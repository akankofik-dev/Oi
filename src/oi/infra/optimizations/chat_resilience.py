"""Chat resilience: rate-limit retry, context-length recovery, throttling.

This module is the shared home for the three "chat must not hard-fail"
behaviours:

* **Rate-limit resilient** — :func:`resilient_stream` retries a stream
  factory when the provider answers 429 (or an equivalent rate-limit
  error) *before any chunk was yielded*, with exponential backoff that
  honours the ``Retry-After`` header. A ``{"type": "status", "status":
  "rate_limited_retrying", ...}`` chunk is yielded before each retry so
  the client sees "rate-limited, retrying" instead of a bare error.
* **No context-length block** — when the provider answers with a
  context-length error before any chunk was yielded, the request's
  messages are recompressed more aggressively
  (:func:`oi.infra.optimizations.context_compressor.compress_for_retry`)
  and the stream is retried.
* **Throttling** — :class:`RateLimiter` bounds concurrent LLM calls per
  model key (burst guard) so a burst of turns cannot hammer one model.
  :class:`TokenBucketRateLimiter` additionally bounds the *rate* (requests
  per minute) per model key: before every model call a token is taken,
  and when the bucket is empty the caller *waits* for a refill instead of
  sending the request. The concurrency guard alone cannot stop bursts
  from getting 429s; the token bucket prevents our own bursts. Retries
  still handle 429s caused by *other* clients sharing the same API key,
  which no local bucket can prevent.

Safety rule: a retry only ever happens when **zero** chunks were yielded
by the failed attempt. Once the first chunk has been delivered (and
observed by history/trajectory bookkeeping), restarting the turn would
duplicate content, so the error propagates as before.

All helpers are stdlib-only and provider-agnostic: error detection works
on status codes, exception attributes, and message text, never on a
single provider's error shape.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Bounded cache (TTL + max entries, LRU eviction)
# ---------------------------------------------------------------------------


class BoundedCache:
    """Small LRU cache with a max-entry cap and per-entry TTL.

    Used for per-turn / per-process caches in the chat path so no cache can
    grow without bound. Thread-safety: callers in the chat path use one
    cache per event loop; :meth:`get`/:meth:`set` are cheap dict ops.
    """

    def __init__(self, *, max_entries: int = 256, ttl_seconds: float = 3600.0) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._store: OrderedDict[Any, tuple[float, Any]] = OrderedDict()

    def _expired(self, expires_at: float) -> bool:
        return time.monotonic() >= expires_at

    def get(self, key: Any, default: Any = None) -> Any:
        entry = self._store.get(key)
        if entry is None:
            return default
        expires_at, value = entry
        if self._expired(expires_at):
            del self._store[key]
            return default
        self._store.move_to_end(key)
        return value

    def set(self, key: Any, value: Any) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)
        self._store.move_to_end(key)
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def pop(self, key: Any, default: Any = None) -> Any:
        entry = self._store.pop(key, None)
        if entry is None:
            return default
        expires_at, value = entry
        return default if self._expired(expires_at) else value

    def purge_expired(self) -> int:
        now = time.monotonic()
        stale = [k for k, (exp, _v) in self._store.items() if now >= exp]
        for key in stale:
            del self._store[key]
        return len(stale)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, key: Any) -> bool:
        return self.get(key) is not None


# ---------------------------------------------------------------------------
# Error classification (provider-agnostic)
# ---------------------------------------------------------------------------

_RATE_LIMIT_PATTERNS = (
    re.compile(r"\b429\b"),
    re.compile(r"rate.?limit", re.IGNORECASE),
    re.compile(r"too many requests", re.IGNORECASE),
    re.compile(r"quota.?exceeded", re.IGNORECASE),
    re.compile(r"capacity", re.IGNORECASE),
    re.compile(r"overloaded", re.IGNORECASE),
    re.compile(r"try again later", re.IGNORECASE),
)

_CONTEXT_LENGTH_PATTERNS = (
    re.compile(r"context.?length", re.IGNORECASE),
    re.compile(r"context_length_exceeded", re.IGNORECASE),
    re.compile(r"maximum context length", re.IGNORECASE),
    re.compile(r"token.{0,20}(limit|exceed|too (long|many))", re.IGNORECASE),
    re.compile(r"input.{0,20}too (long|large)", re.IGNORECASE),
    re.compile(r"prompt.{0,20}too (long|large)", re.IGNORECASE),
    re.compile(r"messages? too long", re.IGNORECASE),
    re.compile(r"context window", re.IGNORECASE),
)


def _error_text(exc: BaseException) -> str:
    parts = [type(exc).__name__, str(exc)]
    for attr in ("code", "status", "status_code", "error_code"):
        value = getattr(exc, attr, None)
        if value is not None:
            parts.append(str(value))
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status", "status_code"):
            value = getattr(response, attr, None)
            if value is not None:
                parts.append(str(value))
    body = getattr(exc, "body", None)
    if isinstance(body, (str, bytes)):
        parts.append(body.decode("utf-8", "replace") if isinstance(body, bytes) else body)
    return " ".join(parts)


def _error_status(exc: BaseException) -> int | None:
    for attr in ("status_code", "status", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    response = getattr(exc, "response", None)
    if response is not None:
        for attr in ("status_code", "status"):
            value = getattr(response, attr, None)
            if isinstance(value, int):
                return value
    return None


def is_rate_limit_error(exc: BaseException) -> bool:
    """True when ``exc`` looks like a provider 429 / rate-limit error."""
    if _error_status(exc) == 429:
        return True
    return any(p.search(_error_text(exc)) for p in _RATE_LIMIT_PATTERNS)


def is_context_length_error(exc: BaseException) -> bool:
    """True when ``exc`` looks like a context-window overflow."""
    status = _error_status(exc)
    # A bare 400 is not enough evidence on its own; require a keyword.
    if status is not None and status not in (400, 413):
        return False
    return any(p.search(_error_text(exc)) for p in _CONTEXT_LENGTH_PATTERNS)


def parse_retry_after(exc: BaseException, *, default: float, cap: float) -> float:
    """Seconds to wait before retrying, honouring ``Retry-After``.

    Accepts numeric seconds (``"120"``, ``120``) and, when the header is a
    date, the delta until that date. Anything unparseable falls back to
    ``default``; the result is always clamped to ``[0, cap]``.
    """
    raw: Any = None
    headers = getattr(exc, "headers", None)
    if isinstance(headers, dict):
        for key in ("Retry-After", "retry-after", "retry_after"):
            if key in headers:
                raw = headers[key]
                break
    if raw is None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
        if isinstance(headers, dict):
            for key in ("Retry-After", "retry-after", "retry_after"):
                if key in headers:
                    raw = headers[key]
                    break
        elif headers is not None:
            get = getattr(headers, "get", None)
            if callable(get):
                raw = get("Retry-After") or get("retry-after")
    if raw is not None:
        try:
            seconds = float(str(raw).strip())
            return max(0.0, min(seconds, cap))
        except (TypeError, ValueError):
            pass
        # HTTP-date form: "Wed, 21 Oct 2015 07:28:00 GMT".
        try:
            from email.utils import parsedate_to_datetime  # noqa: PLC0415

            when = parsedate_to_datetime(str(raw))
            delta = (when.timestamp() - time.time()) if when is not None else default
            return max(0.0, min(delta, cap))
        except (TypeError, ValueError, OverflowError):
            pass
    return max(0.0, min(default, cap))


def retry_delay_seconds(attempt: int, *, base: float = 1.0, cap: float = 30.0) -> float:
    """Exponential backoff with jitter: base * 2**attempt, capped."""
    import random  # noqa: PLC0415

    delay = base * (2**max(0, attempt))
    return min(delay, cap) + random.uniform(0, min(0.5, delay * 0.1))


# ---------------------------------------------------------------------------
# Throttling: per-model concurrency guard
# ---------------------------------------------------------------------------


class RateLimiter:
    """Bounded-concurrency + min-interval guard for LLM calls.

    ``max_concurrent`` caps how many turns may call the same model at once
    (extra callers wait on the semaphore instead of hammering the model);
    ``min_interval_seconds`` spaces out call starts. Defaults are a burst
    guard, not a throttle: normal traffic never waits.
    """

    def __init__(self, *, max_concurrent: int = 8, min_interval_seconds: float = 0.0) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval = max(0.0, min_interval_seconds)
        self._last_start = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        await self._semaphore.acquire()
        if self._min_interval > 0:
            async with self._lock:
                wait = self._min_interval - (time.monotonic() - self._last_start)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_start = time.monotonic()

    def release(self) -> None:
        self._semaphore.release()

    async def __aenter__(self) -> "RateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.release()


_LIMITERS: dict[str, RateLimiter] = {}
_LIMITERS_MAX_KEYS = 64


def get_rate_limiter(model_key: str | None, **kwargs: Any) -> RateLimiter:
    """Process-wide per-model limiter (bounded number of limiter objects)."""
    key = (model_key or "default").strip().lower() or "default"
    limiter = _LIMITERS.get(key)
    if limiter is None:
        if len(_LIMITERS) >= _LIMITERS_MAX_KEYS:
            # Evict the oldest limiter so the registry itself cannot grow
            # without bound when model names are attacker-controlled.
            _LIMITERS.pop(next(iter(_LIMITERS)))
        limiter = RateLimiter(**kwargs) if kwargs else RateLimiter()
        _LIMITERS[key] = limiter
    return limiter


# ---------------------------------------------------------------------------
# Throttling: per-model token bucket (requests-per-minute)
# ---------------------------------------------------------------------------
#
# The semaphore-based RateLimiter above only bounds *concurrency* (how
# many calls are in flight at once). It does NOT bound the *rate*: a burst
# of short calls can still exceed the provider's requests-per-minute
# quota and get 429. This token bucket is the permanent fix for that:
# before every model call a token is taken; when the bucket is empty the
# caller waits for a refill instead of sending the request.
#
# Thread-safety: token state is guarded by a ``threading.Lock`` held only
# for the microsecond refill/check/consume critical section (never across
# an ``await``), so it is safe from both async and sync callers. The
# async ``acquire`` sleeps with ``asyncio.sleep`` (never blocks the event
# loop); ``acquire_sync`` uses ``time.sleep`` and is for sync callers only.

DEFAULT_MODEL_RPM = 30.0
_MODEL_RPM_OVERRIDES: dict[str, float] = {}


def register_model_rpm(model: str, rpm: float) -> None:
    """Register an explicit requests-per-minute limit for ``model``.

    Registered overrides win over the ``OI_RATE_LIMIT_RPM`` env var and
    the default. Raises ``ValueError`` for non-positive ``rpm``.
    """
    rpm_value = float(rpm)
    if rpm_value <= 0:
        raise ValueError("rpm must be > 0")
    _MODEL_RPM_OVERRIDES[(model or "").strip().lower()] = rpm_value


def resolve_model_rpm(model: str | None, explicit: float | None = None) -> float:
    """Resolve the RPM for ``model``: explicit > override > env > default.

    ``explicit`` (when positive) wins. A non-positive or unparseable env
    value falls back to the default with a warning, never crashing the
    chat path on a bad config value.
    """
    if explicit is not None:
        try:
            explicit_value = float(explicit)
        except (TypeError, ValueError):
            explicit_value = 0.0
        if explicit_value > 0:
            return explicit_value
        logger.warning(
            "resolve_model_rpm: ignoring non-positive explicit rpm %r, "
            "falling through to override/env/default",
            explicit,
        )
    key = (model or "").strip().lower()
    override = _MODEL_RPM_OVERRIDES.get(key)
    if override is not None and override > 0:
        return override
    raw_env = os.getenv("OI_RATE_LIMIT_RPM")
    if raw_env is not None:
        try:
            env_value = float(raw_env.strip())
        except (TypeError, ValueError):
            env_value = 0.0
        if env_value > 0:
            return env_value
        logger.warning(
            "resolve_model_rpm: ignoring invalid OI_RATE_LIMIT_RPM %r, "
            "falling back to default %.0f",
            raw_env,
            DEFAULT_MODEL_RPM,
        )
    return DEFAULT_MODEL_RPM


class TokenBucketRateLimiter:
    """Per-model token bucket: at most ``rpm`` requests per minute.

    The bucket starts full (``burst`` tokens), so the first ``burst``
    calls go through immediately; afterwards tokens refill smoothly at
    ``rpm / 60`` per second and a caller that finds the bucket empty
    waits for the next refill instead of sending the request. Burst
    capacity defaults to ``max(1, rpm // 6)`` (5 for the 30 RPM default),
    which lets a small burst through but spreads a 40-tool-call turn over
    ~a minute instead of hammering the provider at once.

    ``acquire`` never deadlocks: if no token becomes available within
    ``max_wait`` seconds it returns ``(False, waited)`` and the caller
    proceeds anyway (the retry/backoff in :func:`resilient_stream` then
    handles any 429 that results).
    """

    def __init__(
        self,
        *,
        rpm: float = DEFAULT_MODEL_RPM,
        burst: int | None = None,
        max_wait: float = 120.0,
    ) -> None:
        rpm_value = float(rpm)
        if rpm_value <= 0:
            raise ValueError("rpm must be > 0")
        self._rpm = rpm_value
        self._refill_rate = rpm_value / 60.0
        self._burst = max(1, int(rpm_value // 6)) if burst is None else max(1, int(burst))
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()
        self._max_wait = max(0.0, float(max_wait))

    @property
    def rpm(self) -> float:
        return self._rpm

    @property
    def burst(self) -> int:
        return self._burst

    def _refill_locked(self, now: float) -> None:
        """Top the bucket up for elapsed time. Caller must hold ``_lock``."""
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(
                float(self._burst),
                self._tokens + elapsed * self._refill_rate,
            )
            self._last_refill = now

    def try_acquire(self) -> bool:
        """Take a token if one is available right now (sync, non-blocking)."""
        with self._lock:
            self._refill_locked(time.monotonic())
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    async def acquire(self, max_wait: float | None = None) -> tuple[bool, float]:
        """Wait for a token; return ``(acquired, seconds_waited)``.

        ``acquired`` is False only when ``max_wait`` elapsed without a
        token; the caller should then proceed anyway and let retry
        handle any 429. Never blocks the event loop (sleeps with
        ``asyncio.sleep``); never deadlocks (bounded by ``max_wait``).
        """
        budget = self._max_wait if max_wait is None else max(0.0, float(max_wait))
        waited = 0.0
        deadline = time.monotonic() + budget
        while True:
            with self._lock:
                now = time.monotonic()
                self._refill_locked(now)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True, waited
                wait_needed = (1.0 - self._tokens) / self._refill_rate
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False, waited
            sleep_for = min(wait_needed, remaining)
            await asyncio.sleep(sleep_for)
            waited += sleep_for

    def acquire_sync(self, max_wait: float | None = None) -> tuple[bool, float]:
        """Blocking sync version of :meth:`acquire` (sync callers only).

        Do NOT call from async code — it uses ``time.sleep`` and would
        block the event loop. Async callers must use :meth:`acquire`.
        """
        budget = self._max_wait if max_wait is None else max(0.0, float(max_wait))
        waited = 0.0
        deadline = time.monotonic() + budget
        while True:
            with self._lock:
                now = time.monotonic()
                self._refill_locked(now)
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True, waited
                wait_needed = (1.0 - self._tokens) / self._refill_rate
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False, waited
            sleep_for = min(wait_needed, remaining)
            time.sleep(sleep_for)
            waited += sleep_for

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"TokenBucketRateLimiter(rpm={self._rpm}, burst={self._burst}, "
            f"tokens={self._tokens:.2f})"
        )


_TOKEN_BUCKETS: dict[str, TokenBucketRateLimiter] = {}
_TOKEN_BUCKETS_MAX_KEYS = 64


def get_token_bucket(
    model_key: str | None,
    *,
    rpm: float | None = None,
    burst: int | None = None,
    max_wait: float | None = None,
) -> TokenBucketRateLimiter:
    """Process-wide per-model token bucket (bounded registry).

    ``rpm`` (when given) resolves via :func:`resolve_model_rpm` — an
    explicit value wins over registered overrides and the env var.
    """
    key = (model_key or "default").strip().lower() or "default"
    bucket = _TOKEN_BUCKETS.get(key)
    if bucket is None:
        if len(_TOKEN_BUCKETS) >= _TOKEN_BUCKETS_MAX_KEYS:
            # Evict the oldest bucket so the registry itself cannot grow
            # without bound when model names are attacker-controlled.
            _TOKEN_BUCKETS.pop(next(iter(_TOKEN_BUCKETS)))
        bucket = TokenBucketRateLimiter(
            rpm=resolve_model_rpm(model_key, explicit=rpm),
            burst=burst,
            max_wait=120.0 if max_wait is None else max_wait,
        )
        _TOKEN_BUCKETS[key] = bucket
    return bucket


# ---------------------------------------------------------------------------
# Resilient stream: retry-before-first-chunk only
# ---------------------------------------------------------------------------


DEFAULT_FAILOVER_MAX_MODELS = 3


def resolve_failover_max_models(explicit: int | None = None) -> int:
    """Resolve total models to try per turn: explicit > env > default.

    ``explicit`` (when positive) wins. A non-positive or unparseable
    ``OI_FAILOVER_MAX_MODELS`` env value falls back to the default with a
    warning, never crashing the chat path on a bad config value.
    """
    if explicit is not None:
        try:
            explicit_value = int(explicit)
        except (TypeError, ValueError):
            explicit_value = 0
        if explicit_value > 0:
            return explicit_value
        logger.warning(
            "resolve_failover_max_models: ignoring non-positive explicit "
            "max_models %r, falling through to env/default",
            explicit,
        )
    raw_env = os.getenv("OI_FAILOVER_MAX_MODELS")
    if raw_env is not None:
        try:
            env_value = int(raw_env.strip())
        except (TypeError, ValueError):
            env_value = 0
        if env_value > 0:
            return env_value
        logger.warning(
            "resolve_failover_max_models: ignoring invalid "
            "OI_FAILOVER_MAX_MODELS %r, falling back to default %d",
            raw_env,
            DEFAULT_FAILOVER_MAX_MODELS,
        )
    return DEFAULT_FAILOVER_MAX_MODELS


def _same_model_ref(a: str | None, b: str | None) -> bool:
    """True when two model identifiers refer to the same model.

    Compares the full ``"provider/model"`` ref (case-insensitive) and,
    so a bare model id still matches its ref, the model-id part after
    the last ``"/"``.
    """
    if a is None or b is None:
        return a is b
    norm_a = str(a).strip().lower()
    norm_b = str(b).strip().lower()
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    return norm_a.rsplit("/", 1)[-1] == norm_b.rsplit("/", 1)[-1]


async def resilient_stream(
    stream_factory: Callable[[], AsyncIterator[dict[str, Any]]],
    *,
    request: dict[str, Any] | None = None,
    model: str | None = None,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_after_cap: float = 60.0,
    limiter: RateLimiter | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    token_bucket: TokenBucketRateLimiter | None = None,
    rpm: float | None = None,
    token_bucket_max_wait: float = 120.0,
    fallback_models: Sequence[str] | None = None,
    max_models: int | None = None,
    failover_status: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield chunks from ``stream_factory()``, retrying pre-first-chunk failures.

    ``stream_factory`` is called fresh on every attempt so a failed attempt
    never reuses a half-consumed generator. ``request`` (when given) is the
    mutable harness request dict: on a context-length error its
    ``"messages"`` are recompressed more aggressively before the next
    attempt, so a long conversation keeps working instead of erroring out.
    Rate-limit retries honour ``Retry-After`` and yield a status chunk first.

    Before the first call — and before every retry attempt — a token is
    taken from the per-model token bucket (``token_bucket`` when given,
    else :func:`get_token_bucket` for the current model with ``rpm``). When the
    bucket is empty the caller *waits* for a refill (yielding a
    ``rate_limit_waiting`` status chunk when the wait is noticeable)
    instead of sending the request, so our own bursts never cause 429.
    If the wait exceeds ``token_bucket_max_wait`` the call proceeds
    anyway and the retry/backoff below handles any 429 that results
    (e.g. from other clients sharing the same API key).

    Failover (429 only): when a model's retry attempts are exhausted on a
    rate-limit error and ``fallback_models`` names other configured models,
    the turn automatically switches to the next model — ``request["model"]``
    is updated and a ``model_failover`` status chunk (``from_model`` /
    ``to_model``) is yielded, so the switch is never silent. The fallback
    gets the SAME ``request`` (same ``messages``/history, unchanged), so
    conversation context and meaning are preserved; only the ``model``
    key changes. Up to ``max_models`` total models are tried per turn
    (``max_models`` param > ``OI_FAILOVER_MAX_MODELS`` env > default 3).
    Non-rate-limit errors (auth, invalid model, context-length, ...) never
    trigger failover. If every tried model fails with 429, the FIRST
    model's 429 is re-raised. ``failover_status`` (when given) is filled
    with ``model_used`` / ``failover_from`` / ``failovers`` /
    ``tried_models`` so callers can report which model actually served.
    """
    attempts = max(1, int(max_attempts))
    max_models_resolved = max(1, resolve_failover_max_models(max_models))
    # Model queue: primary first, then fallbacks (deduplicated against the
    # primary and each other), capped at max_models total.
    queue: list[str | None] = []

    def _push(m: str | None) -> None:
        if m is None:
            if None not in queue:
                queue.append(None)
            return
        text = str(m).strip()
        if not text:
            return
        for existing in queue:
            if existing is not None and _same_model_ref(existing, text):
                return
        queue.append(text)

    _push(model)
    for fallback in fallback_models or []:
        _push(fallback)
    queue = queue[:max_models_resolved]
    # Without a mutable request dict the factory cannot pick up a model
    # switch, so failover is impossible: try the primary only.
    if not isinstance(request, dict):
        queue = queue[:1]
    status_out: dict[str, Any] = {
        "model_used": None,
        "failover_from": [],
        "failovers": 0,
        "tried_models": [],
    }
    first_rate_limit_error: BaseException | None = None
    try:
        for model_index, current_model in enumerate(queue):
            status_out["tried_models"].append(current_model)
            # Explicit limiter/bucket (caller-supplied) stay as given;
            # auto-created ones are per-model so a fallback gets its own
            # concurrency slot and token bucket.
            active_limiter = (
                limiter if limiter is not None else get_rate_limiter(current_model)
            )
            active_bucket = (
                token_bucket
                if token_bucket is not None
                else get_token_bucket(current_model, rpm=rpm)
            )
            switched = False
            for attempt in range(attempts):
                # Token bucket FIRST (rate gate) so a caller never holds a
                # concurrency slot while waiting for a refill. Runs before the
                # first call and before every retry attempt.
                acquired, waited = await active_bucket.acquire(
                    max_wait=token_bucket_max_wait
                )
                if waited > 0.5:
                    yield {
                        "type": "status",
                        "status": "rate_limit_waiting",
                        "wait_seconds": round(waited, 2),
                    }
                if not acquired:
                    logger.warning(
                        "resilient_stream: token bucket wait exceeded %.0fs; "
                        "proceeding anyway (retry will handle 429)",
                        token_bucket_max_wait,
                    )
                yielded_any = False
                try:
                    async with active_limiter:
                        stream = stream_factory()
                        async for chunk in stream:
                            yielded_any = True
                            if status_out["model_used"] is None:
                                status_out["model_used"] = current_model
                            yield chunk
                    return
                except BaseException as exc:  # noqa: BLE001 — classify, then re-raise
                    if yielded_any:
                        # Content already delivered: restarting would duplicate it.
                        raise
                    last_attempt = attempt >= attempts - 1
                    if is_context_length_error(exc) and not last_attempt:
                        if request is not None and isinstance(
                            request.get("messages"), list
                        ):
                            from oi.infra.optimizations.context_compressor import (  # noqa: PLC0415
                                compress_for_retry,
                            )

                            try:
                                request["messages"] = compress_for_retry(
                                    request["messages"],
                                    model=current_model,
                                    attempt=attempt,
                                )
                            except Exception:
                                logger.exception(
                                    "resilient_stream: recompress failed"
                                )
                        logger.warning(
                            "resilient_stream: context-length error, retrying with "
                            "compressed context (attempt %d/%d)",
                            attempt + 1,
                            attempts,
                        )
                        yield {
                            "type": "status",
                            "status": "context_compressed_retrying",
                            "attempt": attempt + 1,
                        }
                        continue
                    if is_rate_limit_error(exc):
                        if first_rate_limit_error is None:
                            first_rate_limit_error = exc
                        if not last_attempt:
                            wait = parse_retry_after(
                                exc,
                                default=retry_delay_seconds(
                                    attempt, base=base_delay, cap=max_delay
                                ),
                                cap=retry_after_cap,
                            )
                            logger.warning(
                                "resilient_stream: rate-limited, retrying in %.1fs "
                                "(attempt %d/%d)",
                                wait,
                                attempt + 1,
                                attempts,
                            )
                            yield {
                                "type": "status",
                                "status": "rate_limited_retrying",
                                "attempt": attempt + 1,
                                "wait_seconds": round(wait, 2),
                            }
                            if wait > 0:
                                await sleep(wait)
                            continue
                        # Retries exhausted for this model. Fail over to the
                        # next model on 429 only — never on other errors.
                        if model_index + 1 < len(queue):
                            next_model = queue[model_index + 1]
                            status_out["failover_from"].append(current_model)
                            status_out["failovers"] = len(
                                status_out["failover_from"]
                            )
                            logger.warning(
                                "resilient_stream: model %r rate-limited after "
                                "%d attempts; failing over to %r",
                                current_model,
                                attempts,
                                next_model,
                            )
                            yield {
                                "type": "status",
                                "status": "model_failover",
                                "from_model": current_model,
                                "to_model": next_model,
                                "reason": "rate_limited",
                            }
                            if request is not None:
                                request["model"] = next_model
                            switched = True
                        break
                    raise
            if switched:
                continue
            break
        if first_rate_limit_error is not None:
            raise first_rate_limit_error
    finally:
        if failover_status is not None:
            failover_status.update(status_out)


__all__ = [
    "BoundedCache",
    "RateLimiter",
    "TokenBucketRateLimiter",
    "get_rate_limiter",
    "get_token_bucket",
    "is_context_length_error",
    "is_rate_limit_error",
    "parse_retry_after",
    "register_model_rpm",
    "resilient_stream",
    "resolve_failover_max_models",
    "resolve_model_rpm",
    "retry_delay_seconds",
]
