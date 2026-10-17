"""L3: smart auto-router — intent classification + latency-aware routing.

:class:`SmartAutoRouter` decides which agent should handle an incoming message:

* :func:`classify_intent` — cheap heuristic classifier over four intents
  (greeting / short / complex / coding). No ML dependency; pure stdlib.
* :class:`LatencyTracker` — exponential moving average of per-agent
  turn latency, so routing can prefer the fastest capable agent.
* :class:`ThreadContextStore` — conversation context keyed by *thread*, not
  by agent, so switching agents mid-thread never loses context.
* Routing decision engine with three modes: ``off`` (never route),
  ``suggest`` (return a suggestion the caller may ignore), ``auto``
  (return the chosen agent directly).

The router only *suggests or selects*; it never mutates agent state.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Intent(str, Enum):
    GREETING = "greeting"
    SHORT = "short"
    COMPLEX = "complex"
    CODING = "coding"


_ROUTER_MODES = frozenset({"off", "suggest", "auto"})

_GREETING_RE = re.compile(
    r"^(hi|halo|hello|hey|pagi|siang|sore|malam|assalamualaikum|"
    r"selamat\s+(pagi|siang|sore|malam)|thanks|terima kasih|makasih|bye|dadah)\b",
    re.IGNORECASE,
)

_CODING_RE = re.compile(
    r"(```|def |class |import |function|=>|{.*}|;|\(\)|"
    r"\b(code|kode|koding|ngoding|fungsi|pemrograman|script|debug|error|"
    r"traceback|exception|compile|refactor|coding|"
    r"function|variable|api|regex|sql|query|deploy)\b)",
    re.IGNORECASE,
)

_COMPLEX_HINT_RE = re.compile(
    r"\b(jelaskan|analisis|bandingkan|buatkan|rancang|design|research|"
    r"riset|strategi|langkah-langkah|step by step|kenapa|bagaimana|"
    r"mengapa|what|why|how|explain|compare|plan)\b",
    re.IGNORECASE,
)


def classify_intent(text: str) -> Intent:
    """Heuristic intent classification (fast, dependency-free)."""
    stripped = (text or "").strip()
    if not stripped:
        return Intent.SHORT
    if _GREETING_RE.search(stripped) and len(stripped) < 60:
        return Intent.GREETING
    if _CODING_RE.search(stripped):
        return Intent.CODING
    words = len(stripped.split())
    if words > 40 or _COMPLEX_HINT_RE.search(stripped):
        return Intent.COMPLEX
    return Intent.SHORT


@dataclass
class LatencyTracker:
    """Per-agent EMA of turn latency (seconds). Lower is faster.

    Fed from real turn timings by ``processor.py`` (both the IM ``__call__``
    and WS ``iter_turn_chunks`` paths record turn duration via
    ``integration.record_turn_latency`` when the ``auto_router`` flag is ON).
    Until data accrues, :meth:`fastest` returns None and routing keeps the
    current agent — a safe no-op.

    Memory-safe: at most ``max_agents`` entries are kept; when the cap is
    hit the entry with the oldest last-update is evicted.
    """

    alpha: float = 0.3
    max_agents: int = 256
    _ema: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _seen: dict[str, float] = field(default_factory=dict, init=False, repr=False)

    def record(self, agent_id: str, seconds: float) -> None:
        if seconds < 0:
            return
        prev = self._ema.get(agent_id)
        self._ema[agent_id] = seconds if prev is None else (
            self.alpha * seconds + (1 - self.alpha) * prev
        )
        self._seen[agent_id] = time.time()
        while len(self._ema) > self.max_agents:
            oldest = min(self._seen.items(), key=lambda kv: kv[1])[0]
            self._ema.pop(oldest, None)
            self._seen.pop(oldest, None)

    def latency(self, agent_id: str) -> float | None:
        return self._ema.get(agent_id)

    def fastest(self, candidates: list[str]) -> str | None:
        known = [(self._ema[a], a) for a in candidates if a in self._ema]
        if not known:
            return None
        return min(known)[1]


@dataclass
class ThreadContextStore:
    """Conversation context bound to the *thread*, surviving agent switches.

    Stored per thread: a small summary plus the last user intent. Agents read
    this instead of relying on their own (agent-scoped) memory when a thread
    hops between agents.

    Memory-safe: at most ``max_threads`` entries are kept (oldest evicted
    first) and entries older than ``ttl_seconds`` are pruned on write, so
    long-lived processes cannot accumulate one entry per thread forever.
    """

    max_threads: int = 512
    ttl_seconds: float = 24 * 3600.0
    _store: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)

    def _prune_locked(self) -> None:
        now = time.time()
        stale = [
            tid
            for tid, entry in self._store.items()
            if now - float(entry.get("updated_at", now)) > self.ttl_seconds
        ]
        for tid in stale:
            self._store.pop(tid, None)
        while len(self._store) >= self.max_threads:
            oldest = min(
                self._store.items(),
                key=lambda kv: float(kv[1].get("updated_at", 0)),
            )[0]
            self._store.pop(oldest, None)

    def update(
        self,
        thread_id: str,
        *,
        summary: str | None = None,
        intent: Intent | None = None,
        agent_id: str | None = None,
    ) -> None:
        self._prune_locked()
        entry = self._store.setdefault(thread_id, {})
        if summary is not None:
            entry["summary"] = summary
        if intent is not None:
            entry["intent"] = intent.value
        if agent_id is not None:
            entry["last_agent_id"] = agent_id
        entry["updated_at"] = time.time()

    def get(self, thread_id: str) -> dict[str, Any]:
        return dict(self._store.get(thread_id, {}))

    def clear(self, thread_id: str) -> None:
        self._store.pop(thread_id, None)


@dataclass(frozen=True)
class RoutingDecision:
    """Outcome of one routing evaluation."""

    #: Chosen agent id, or None when no routing applies.
    agent_id: str | None
    intent: Intent
    #: "off" | "suggest" | "auto"
    mode: str
    reason: str
    #: True when the caller should treat agent_id as advisory only.
    advisory: bool


@dataclass
class SmartAutoRouter:
    """Intent + latency aware agent routing with off/suggest/auto modes."""

    mode: str = "suggest"
    latency_tracker: LatencyTracker = field(default_factory=LatencyTracker)
    context_store: ThreadContextStore = field(default_factory=ThreadContextStore)
    #: intent -> preferred agent id (operator-configured routing table).
    intent_agents: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in _ROUTER_MODES:
            raise ValueError(f"mode must be one of {sorted(_ROUTER_MODES)}")

    def set_mode(self, mode: str) -> None:
        if mode not in _ROUTER_MODES:
            raise ValueError(f"mode must be one of {sorted(_ROUTER_MODES)}")
        # dataclass is not frozen; attribute assignment is fine.
        object.__setattr__(self, "mode", mode)

    def route(
        self,
        text: str,
        *,
        thread_id: str,
        current_agent_id: str | None = None,
        candidates: list[str] | None = None,
    ) -> RoutingDecision:
        """Evaluate routing for an incoming message (pure decision, no I/O)."""
        intent = classify_intent(text)
        self.context_store.update(thread_id, intent=intent, agent_id=current_agent_id)

        if self.mode == "off":
            return RoutingDecision(
                agent_id=None,
                intent=intent,
                mode=self.mode,
                reason="router disabled",
                advisory=True,
            )

        preferred = self.intent_agents.get(intent.value)
        target = preferred
        reason = f"intent={intent.value}"
        if target is None and candidates:
            # No intent mapping: prefer the fastest known candidate, else stay.
            fastest = self.latency_tracker.fastest(candidates)
            if fastest is not None and fastest != current_agent_id:
                target = fastest
                reason += f"; fastest-known={fastest}"

        if target is None or target == current_agent_id:
            return RoutingDecision(
                agent_id=current_agent_id,
                intent=intent,
                mode=self.mode,
                reason=f"{reason}; keep current agent",
                advisory=self.mode == "suggest",
            )
        return RoutingDecision(
            agent_id=target,
            intent=intent,
            mode=self.mode,
            reason=reason,
            advisory=self.mode == "suggest",
        )

    def record_latency(self, agent_id: str, seconds: float) -> None:
        self.latency_tracker.record(agent_id, seconds)
