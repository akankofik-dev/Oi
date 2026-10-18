"""Automatic provider failover for agent model calls.

When the primary (router-selected) model fails -- provider down, timeout,
circuit breaker open -- this middleware automatically retries the same
request on a fallback model instead of surfacing an error to the user.
The user never notices the outage; they just get an answer.

How it works
------------
1. The call first goes to the primary model (whatever
   ``ModelRouterMiddleware`` selected: user preference, multimodal upgrade,
   ...). The primary is *always* tried first, so recovery is automatic: as
   soon as the primary provider is healthy again, calls succeed on it with
   no manual intervention.
2. On failure the middleware builds an ordered candidate list from
   ``explicit_fallbacks`` (agent config ``failover_models``) plus
   auto-discovered usable models (``list_refs``), excluding the primary.
3. Candidates are ordered by **health, then speed** (smart routing):
   providers with recent consecutive failures -- or a currently OPEN
   circuit breaker -- sort last; among healthy providers the one with the
   lowest exponentially-weighted latency (EWMA) is tried first. If the
   fastest is down, the next-fastest is tried, and so on.
4. Each candidate is tried at most once per call cycle; the total number
   of attempts is bounded by ``max_attempts`` (default 3). Latency and
   failure counters are updated per model ref and exposed via
   :meth:`stats` for dashboard observability.
5. If every candidate fails, the middleware either raises
   :class:`FailoverExhaustedError` (single-cycle mode) or sleeps with
   backoff and starts a new cycle (persistent-retry mode). Only the user
   cancelling the stream stops the loop.

Slow bypass
-----------
If the primary's EWMA latency exceeds ``slow_threshold`` (default 30s) and
a healthy, faster candidate exists, the fastest healthy candidate is tried
*first* for the next call instead of the slow primary. A ``"slow"``
routing event is emitted so the UI can notify the user. Set
``slow_threshold=0`` to disable (pure failure-driven failover).

Permission safety
-----------------
This middleware operates at the **model-call** level, strictly *below* the
HITL/permission layer. Retrying a failed model call -- or switching to a
different provider -- does **not** bypass tool permissions: ``allow
session`` / ``always allow`` / HITL approvals are enforced when the model
attempts to *use* a tool, not when the model itself is invoked. A different
model answering does not grant new capabilities.

Placement
---------
Registered *outside* (before) :class:`CircuitBreakerMiddleware` so a
``CircuitOpenError`` -- fail-fast on a dead provider -- is caught here and
turned into an immediate fallback attempt instead of an error. The inner
circuit breaker still records per-model failures, so its cooldown and
half-open probing keep working unchanged.

Config knobs (see ``oi.infra.agents.settings.runtime_limits``)::

    failover_enabled          bool (default: True)
    failover_models           list of "provider/model" refs, priority order (default: [])
    failover_max_attempts     total attempts incl. primary (default: 3)
    failover_unhealthy_after  consecutive failures before deprioritized (default: 3)
    failover_persistent_retry bool (default: True) -- keep retrying new cycles
    failover_max_cycles       int (default: 0 = unlimited; cron: 10)
    failover_retry_backoff_base float (default: 5.0s; doubles per cycle, cap 60s)
    failover_slow_threshold   float (default: 30.0s; 0 disables slow bypass)

Backward compatibility: with a single configured provider (no fallbacks and
nothing discovered) the middleware is a pure pass-through that only records
latency statistics. Set ``failover_enabled`` to false to restore the exact
legacy behavior.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from oi.infra.agents.middleware.routing_events import emit_routing_event

log = logging.getLogger(__name__)

# EWMA smoothing factor for per-provider latency tracking. 0.3 reacts to
# change within a handful of calls without oscillating on one slow outlier.
_LATENCY_ALPHA = 0.3

# Cap for the backoff sleep between persistent-retry cycles.
_RETRY_BACKOFF_CAP_S = 60.0


class FailoverExhaustedError(RuntimeError):
    """Raised when the primary model and every fallback candidate failed.

    Carries the per-candidate errors so logs / the dashboard can show
    exactly which providers were tried and why each one failed.
    """

    def __init__(self, attempts: Sequence[tuple[str, BaseException]]) -> None:
        details = "; ".join(
            f"{ref}: {type(err).__name__}: {err}" for ref, err in attempts
        )
        super().__init__(
            f"All {len(attempts)} model candidates failed; automatic "
            f"failover exhausted. Tried -> {details}"
        )
        self.attempts: list[tuple[str, BaseException]] = list(attempts)


def _model_id_from_request(request: Any) -> str:
    """Best-effort model id for logging (matches circuit-breaker keys)."""
    model = getattr(request, "model", None)
    if model is None:
        return "unknown"
    name = getattr(model, "model_name", None) or getattr(model, "model", None)
    return str(name or model)


class ProviderFailoverMiddleware(AgentMiddleware[Any, Any]):
    """Retry a failed model call on the healthiest, fastest fallback provider.

    Args:
        enabled: Master switch. When False the middleware passes every
            call through untouched.
        explicit_fallbacks: Ordered ``"provider/model"`` refs from agent
            config. Tried before auto-discovered refs.
        list_refs: Callable returning usable ``"provider/model"`` refs in
            priority order. Called lazily (and cached briefly) so provider
            changes are picked up without an agent rebuild.
        model_builder: Callable mapping a ref to a langchain chat model.
            Typically ``shared_factory.get_chat_model`` from oi-harness.
        circuit_breaker: Optional :class:`CircuitBreakerMiddleware` instance.
            Its :meth:`status` is consulted to deprioritize candidates whose
            circuit is currently OPEN. The breaker itself is never modified.
        max_attempts: Total model-call attempts per cycle, including the
            primary. Must be >= 1.
        unhealthy_after: Consecutive failures after which a ref is treated
            as unhealthy and sorted behind healthy candidates.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        explicit_fallbacks: Sequence[str] | None = None,
        list_refs: Callable[[], list[str]] | None = None,
        model_builder: Callable[[str], Any] | None = None,
        circuit_breaker: Any | None = None,
        max_attempts: int = 3,
        unhealthy_after: int = 3,
        persistent_retry: bool = True,
        max_cycles: int = 0,
        retry_backoff_base: float = 5.0,
        slow_threshold: float = 30.0,
    ) -> None:
        super().__init__()
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if unhealthy_after < 1:
            raise ValueError("unhealthy_after must be >= 1")
        if max_cycles < 0:
            raise ValueError("max_cycles must be >= 0")
        if retry_backoff_base < 0:
            raise ValueError("retry_backoff_base must be >= 0")
        if slow_threshold < 0:
            raise ValueError("slow_threshold must be >= 0")
        self._enabled = bool(enabled)
        self._explicit_fallbacks = [r for r in (explicit_fallbacks or []) if r]
        self._list_refs = list_refs
        self._model_builder = model_builder
        self._circuit_breaker = circuit_breaker
        self._max_attempts = int(max_attempts)
        self._unhealthy_after = int(unhealthy_after)
        self._persistent_retry = bool(persistent_retry)
        self._max_cycles = int(max_cycles)
        self._retry_backoff_base = float(retry_backoff_base)
        self._slow_threshold = float(slow_threshold)
        self._lock = threading.Lock()
        # Per-ref stats: {"ewma_latency_s": float|None, "consecutive_failures": int,
        #                 "successes": int, "failovers": int}
        self._stats: dict[str, dict[str, Any]] = {}
        self._discovered_cache: tuple[float, list[str]] | None = None

    # ------------------------------------------------------------------
    # introspection
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, dict[str, Any]]:
        """Return per-ref latency/health stats for observability."""
        with self._lock:
            return {
                ref: {
                    "ewma_latency_s": (
                        round(s["ewma_latency_s"], 3)
                        if s["ewma_latency_s"] is not None
                        else None
                    ),
                    "consecutive_failures": s["consecutive_failures"],
                    "successes": s["successes"],
                    "failovers": s["failovers"],
                }
                for ref, s in self._stats.items()
            }

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _stat(self, ref: str) -> dict[str, Any]:
        return self._stats.setdefault(
            ref,
            {
                "ewma_latency_s": None,
                "consecutive_failures": 0,
                "successes": 0,
                "failovers": 0,
            },
        )

    def _record_success(self, ref: str, duration_s: float) -> None:
        with self._lock:
            s = self._stat(ref)
            prev = s["ewma_latency_s"]
            s["ewma_latency_s"] = (
                duration_s
                if prev is None
                else _LATENCY_ALPHA * duration_s + (1 - _LATENCY_ALPHA) * prev
            )
            s["consecutive_failures"] = 0
            s["successes"] += 1

    def _record_failure(self, ref: str) -> None:
        with self._lock:
            s = self._stat(ref)
            s["consecutive_failures"] += 1
            s["failovers"] += 1

    def _breaker_open_refs(self) -> set[str]:
        """Model ids whose circuit is currently OPEN (best effort)."""
        breaker = self._circuit_breaker
        status_fn = getattr(breaker, "status", None)
        if not callable(status_fn):
            return set()
        try:
            status = status_fn()
        except Exception:  # fail-open: never let introspection break calls
            return set()
        if not isinstance(status, dict):
            return set()
        return {
            str(model_id)
            for model_id, info in status.items()
            if isinstance(info, dict) and info.get("state") == "open"
        }

    def _discovered_refs(self) -> list[str]:
        """Auto-discovered usable refs, cached for 30s to avoid DB churn."""
        if self._list_refs is None:
            return []
        now = time.monotonic()
        cached = self._discovered_cache
        if cached is not None and now - cached[0] < 30:
            return list(cached[1])
        try:
            refs = [r for r in (self._list_refs() or []) if r]
        except Exception as exc:  # fail-open
            log.debug("Provider failover: ref discovery failed: %s", exc)
            refs = []
        self._discovered_cache = (now, refs)
        return list(refs)

    def _all_known_refs(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for ref in (*self._explicit_fallbacks, *self._discovered_refs()):
            if ref not in seen:
                seen.add(ref)
                ordered.append(ref)
        return ordered

    def _identify_current_ref(self, request: Any) -> str | None:
        """Match the bound model object to a known ref via factory identity.

        The harness router builds models through the shared factory cache,
        so ``model_builder(ref) is request.model`` identifies the ref
        without parsing provider-specific attributes.
        """
        current = getattr(request, "model", None)
        if current is None or self._model_builder is None:
            return None
        for ref in self._all_known_refs():
            try:
                if self._model_builder(ref) is current:
                    return ref
            except Exception:
                continue
        return None

    def _order_candidates(self, candidates: list[str]) -> list[str]:
        """Order by health first, then by tracked latency (fastest first)."""
        open_ids = self._breaker_open_refs()
        with self._lock:
            snapshot = {
                ref: (
                    self._stats.get(ref, {}).get("consecutive_failures", 0),
                    self._stats.get(ref, {}).get("ewma_latency_s"),
                )
                for ref in candidates
            }

        def sort_key(ref: str) -> tuple[int, float]:
            failures, latency = snapshot[ref]
            model_id = ref.partition("/")[2] or ref
            unhealthy = failures >= self._unhealthy_after or model_id in open_ids
            # Unknown latency sorts after known latency within the same
            # health bucket (None -> +inf).
            return (1 if unhealthy else 0, latency if latency is not None else float("inf"))

        return sorted(candidates, key=sort_key)

    def _slow_bypass_candidate(
        self, primary_ref: str | None, fallbacks: list[str]
    ) -> str | None:
        """Return a faster healthy candidate if the primary is too slow.

        Returns None when slow bypass is disabled (slow_threshold=0), when
        the primary has no tracked latency yet, when the primary is not
        slower than the threshold, or when no healthy faster candidate
        exists. Never returns an unhealthy candidate.
        """
        if self._slow_threshold <= 0 or not primary_ref or not fallbacks:
            return None
        open_ids = self._breaker_open_refs()
        with self._lock:
            primary_latency = self._stats.get(primary_ref, {}).get("ewma_latency_s")
            primary_failures = self._stats.get(primary_ref, {}).get(
                "consecutive_failures", 0
            )
            candidates_info = [
                (
                    ref,
                    self._stats.get(ref, {}).get("ewma_latency_s"),
                    self._stats.get(ref, {}).get("consecutive_failures", 0),
                )
                for ref in fallbacks
            ]
        if primary_latency is None or primary_latency <= self._slow_threshold:
            return None
        # Primary is slow; find the fastest HEALTHY candidate that is
        # meaningfully faster (at least 2x faster to avoid flapping).
        best: str | None = None
        best_latency: float = float("inf")
        for ref, latency, failures in candidates_info:
            if latency is None:
                continue
            model_id = ref.partition("/")[2] or ref
            if failures >= self._unhealthy_after or model_id in open_ids:
                continue
            if latency < best_latency and latency * 2 < primary_latency:
                best = ref
                best_latency = latency
        return best

    def _retry_backoff_s(self, cycle: int) -> float:
        """Backoff seconds before retry cycle N (1-based). Doubles, capped."""
        backoff = self._retry_backoff_base * (2 ** (cycle - 1))
        return min(backoff, _RETRY_BACKOFF_CAP_S)

    def _swap_model(self, request: Any, ref: str) -> bool:
        """Point ``request.model`` at the fallback ref. False on build error."""
        if self._model_builder is None:
            return False
        try:
            request.model = self._model_builder(ref)
        except Exception as exc:
            log.warning(
                "Provider failover: cannot build model for ref %r: %s -- skipping",
                ref,
                exc,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # core failover loop (shared by sync/async paths)
    # ------------------------------------------------------------------

    def _plan_attempts(self, request: Any) -> tuple[str | None, list[str]]:
        """Return (primary_ref_or_None, ordered fallback refs)."""
        primary_ref = self._identify_current_ref(request)
        known = self._all_known_refs()
        fallbacks = [r for r in known if r != primary_ref]
        return primary_ref, self._order_candidates(fallbacks)

    def _plan_attempts_with_slow_bypass(
        self, request: Any
    ) -> tuple[str | None, list[str], str | None]:
        """Return (primary_ref, ordered attempts, slow_bypassed_ref).

        When the primary is slower than ``slow_threshold`` and a healthy,
        much faster candidate exists, the fast candidate is moved to the
        front of the attempt list (the slow primary is still tried later
        in the cycle if the fast one fails).
        """
        primary_ref, fallbacks = self._plan_attempts(request)
        bypassed: str | None = None
        fast = self._slow_bypass_candidate(primary_ref, fallbacks)
        if fast is not None:
            # Move the fast candidate to the front; primary stays in the
            # list so a fast-candidate failure still falls back to it.
            fallbacks = [fast] + [r for r in fallbacks if r != fast]
            bypassed = fast
            with self._lock:
                primary_latency = self._stats.get(primary_ref or "", {}).get(
                    "ewma_latency_s"
                )
            log.info(
                "Provider failover: primary %r is slow (EWMA %.1fs > %.1fs); "
                "trying faster %r first",
                primary_ref,
                primary_latency or 0.0,
                self._slow_threshold,
                fast,
            )
            emit_routing_event(
                "slow",
                model=primary_ref,
                to_model=fast,
                reason="slow",
                latency_s=primary_latency,
                detail=(
                    f"Primary {primary_ref} is slow "
                    f"({primary_latency:.1f}s > {self._slow_threshold:.0f}s); "
                    f"trying faster {fast}"
                ),
            )
        return primary_ref, fallbacks, bypassed

    async def _run_cycle(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
        primary_ref: str | None,
        fallbacks: list[str],
        cycle: int,
    ) -> Any:
        """Run one failover cycle. Returns result or raises FailoverExhaustedError."""
        # Attempt 1 is always the primary (already bound on the request),
        # unless slow bypass reordered the list.
        attempts: list[tuple[str, Any]] = [(primary_ref or _model_id_from_request(request), None)]
        for ref in fallbacks:
            if len(attempts) >= self._max_attempts:
                break
            attempts.append((ref, ref))

        errors: list[tuple[str, BaseException]] = []
        for index, (label, ref) in enumerate(attempts):
            if ref is not None and not self._swap_model(request, ref):
                continue
            start = time.perf_counter()
            try:
                result = await handler(request)
            except Exception as exc:  # noqa: BLE001 - any model-call failure triggers failover
                duration = time.perf_counter() - start
                self._record_failure(label)
                errors.append((label, exc))
                if index + 1 < len(attempts):
                    nxt = attempts[index + 1][0]
                    log.warning(
                        "Provider failover: model %r failed after %.1fs "
                        "(%s: %s); trying %r (attempt %d/%d, cycle %d)",
                        label,
                        duration,
                        type(exc).__name__,
                        exc,
                        nxt,
                        index + 2,
                        len(attempts),
                        cycle,
                    )
                    emit_routing_event(
                        "switched",
                        from_model=label,
                        to_model=nxt,
                        reason="failed",
                        latency_s=duration,
                        detail=f"{label} failed ({type(exc).__name__}); trying {nxt}",
                        cycle=cycle,
                    )
                continue
            duration = time.perf_counter() - start
            self._record_success(label, duration)
            emit_routing_event(
                "selected",
                model=label,
                latency_s=duration,
                cycle=cycle,
            )
            if index > 0:
                log.info(
                    "Provider failover: recovered on %r in %.1fs "
                    "(primary %r failed, cycle %d)",
                    label,
                    duration,
                    primary_ref or _model_id_from_request(request),
                    cycle,
                )
            return result

        raise FailoverExhaustedError(errors)

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        if not self._enabled or self._model_builder is None:
            return await handler(request)

        cycle = 0
        last_errors: list[tuple[str, BaseException]] = []
        while True:
            cycle += 1
            # Check cycle bound for non-interactive contexts (cron/inbox).
            if self._max_cycles > 0 and cycle > self._max_cycles:
                log.error(
                    "Provider failover: max cycles (%d) reached; giving up",
                    self._max_cycles,
                )
                raise FailoverExhaustedError(last_errors)

            primary_ref, fallbacks, _bypassed = self._plan_attempts_with_slow_bypass(
                request
            )
            try:
                return await self._run_cycle(request, handler, primary_ref, fallbacks, cycle)
            except FailoverExhaustedError as exc:
                last_errors = exc.attempts
                # Single-cycle mode (or sync path): surface immediately.
                if not self._persistent_retry:
                    raise
                # Persistent retry: backoff then a fresh cycle. Only the
                # user cancelling the stream (CancelledError during sleep)
                # stops the loop.
                backoff = self._retry_backoff_s(cycle)
                log.warning(
                    "Provider failover: cycle %d exhausted (%d candidates failed); "
                    "retrying in %.0fs (persistent retry; user stop cancels)",
                    cycle,
                    len(last_errors),
                    backoff,
                )
                emit_routing_event(
                    "retrying",
                    reason="all_failed",
                    cycle=cycle,
                    next_retry_in_s=backoff,
                    detail=(
                        f"All {len(last_errors)} candidates failed in cycle {cycle}; "
                        f"retrying in {backoff:.0f}s"
                    ),
                )
                # NOTE: asyncio.CancelledError is a BaseException and is NOT
                # caught here -- user stop during backoff cancels cleanly.
                await asyncio.sleep(backoff)
                # Loop continues: fresh cycle, primary tried first again
                # (automatic recovery when the provider is healthy).

    def wrap_model_call(self, request: Any, handler: Callable[[Any], Any]) -> Any:
        # NOTE: sync path stays single-cycle (no persistent retry): there is
        # no cancellation mechanism in the sync path, so an unbounded loop
        # could hang the worker. LangChain agents run async in practice.
        if not self._enabled or self._model_builder is None:
            return handler(request)
        primary_ref, fallbacks, _bypassed = self._plan_attempts_with_slow_bypass(
            request
        )
        attempts: list[tuple[str, Any]] = [(primary_ref or _model_id_from_request(request), None)]
        for ref in fallbacks:
            if len(attempts) >= self._max_attempts:
                break
            attempts.append((ref, ref))

        errors: list[tuple[str, BaseException]] = []
        for index, (label, ref) in enumerate(attempts):
            if ref is not None and not self._swap_model(request, ref):
                continue
            start = time.perf_counter()
            try:
                result = handler(request)
            except Exception as exc:  # noqa: BLE001 - any model-call failure triggers failover
                duration = time.perf_counter() - start
                self._record_failure(label)
                errors.append((label, exc))
                if index + 1 < len(attempts):
                    nxt = attempts[index + 1][0]
                    log.warning(
                        "Provider failover: model %r failed after %.1fs "
                        "(%s: %s); trying %r (attempt %d/%d)",
                        label,
                        duration,
                        type(exc).__name__,
                        exc,
                        nxt,
                        index + 2,
                        len(attempts),
                    )
                    emit_routing_event(
                        "switched",
                        from_model=label,
                        to_model=nxt,
                        reason="failed",
                        latency_s=duration,
                        detail=f"{label} failed ({type(exc).__name__}); trying {nxt}",
                    )
                continue
            duration = time.perf_counter() - start
            self._record_success(label, duration)
            emit_routing_event(
                "selected",
                model=label,
                latency_s=duration,
            )
            if index > 0:
                log.info(
                    "Provider failover: recovered on %r in %.1fs "
                    "(primary %r failed)",
                    label,
                    duration,
                    primary_ref or _model_id_from_request(request),
                )
            return result

        raise FailoverExhaustedError(errors)


__all__ = [
    "FailoverExhaustedError",
    "ProviderFailoverMiddleware",
]
