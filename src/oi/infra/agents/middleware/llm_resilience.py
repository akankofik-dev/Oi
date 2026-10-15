"""LLM resilience primitives: fail-fast error types for model calls.

This module defines the exception types used by the model-call retry path
to distinguish *fail-fast* errors (which must propagate directly to the user)
from transient errors (which are converted into a model-visible retry prompt).

The module was missing from the tree while
:func:`oi.infra.agents.manager._model_retry_on_failure` already imported it,
so any model-call failure crashed with ``ModuleNotFoundError`` instead of
being handled. The classes below match the contract that importer expects.
"""

from __future__ import annotations


class CircuitOpenError(RuntimeError):
    """Raised when the circuit breaker for a model/provider is open.

    Fail-fast: the provider is known-dead (cooldown active), so retrying
    immediately is pointless. Propagates directly to the user instead of
    becoming a confusing retry prompt.
    """


class LlmTimeoutError(TimeoutError):
    """Raised when a single LLM call exceeds its configured timeout.

    Fail-fast: surfaces the timeout to the user instead of being swallowed
    into a generic retry loop.
    """
