"""Fast lane for simple chat turns.

Implements the "simple chats should be cheap" idea as a *decision-only*
helper built on the project's real intent classifier
(:func:`oi.infra.optimizations.auto_router.classify_intent`).

The fast lane never skips the harness loop. History recording, HITL
checks and tool permissions inside ``GlobalProcessor`` stay exactly as
they are for every turn; the only thing this decision may change is
*which model ref* serves the turn.

Wiring: ``GlobalProcessor._apply_auto_router`` consults
:func:`decide_fast_lane` (via ``OptimizationManager.fast_lane_decision``)
when the ``fast_lane`` chat flag is on and ``fast_lane_model`` is
configured, and logs the decision in suggest mode. The decision is not
applied yet: serving a turn from the fast model is a separate step.
With the flag off (the default) this module has no effect on behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass

from oi.infra.optimizations.auto_router import Intent, classify_intent

#: Intents that may be served by the fast model. CODING and COMPLEX turns
#: always stay on the agent's configured model.
_FAST_INTENTS = frozenset({Intent.GREETING, Intent.SHORT})


@dataclass(frozen=True)
class FastLaneDecision:
    """Outcome of one fast-lane decision."""

    use_fast_model: bool
    intent: Intent
    model_ref: str | None
    reason: str


def decide_fast_lane(
    text: str,
    *,
    thread_used_tools: bool,
    fast_model_ref: str | None,
) -> FastLaneDecision:
    """Decide whether *text* may be served by the fast model.

    A turn qualifies only when all of these hold:

    * a fast model ref is configured (``fast_model_ref`` is not empty),
    * the thread has never used tools (a thread that already needed
      tools may need them again, so it stays on the full model), and
    * the classified intent is simple (greeting or short).
    """
    intent = classify_intent(text)
    if not fast_model_ref:
        return FastLaneDecision(False, intent, None, "no fast model configured")
    if thread_used_tools:
        return FastLaneDecision(False, intent, None, "thread already used tools")
    if intent not in _FAST_INTENTS:
        return FastLaneDecision(
            False, intent, None, f"intent {intent.value} needs the full model"
        )
    return FastLaneDecision(
        True, intent, fast_model_ref, f"simple intent {intent.value}"
    )
