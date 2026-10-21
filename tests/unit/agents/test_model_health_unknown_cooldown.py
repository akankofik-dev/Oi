from __future__ import annotations

from oi.infra.agents.providers.health import ModelHealthRegistry


class _Clock:
    def __init__(self) -> None:
        self.now = 500.0

    def __call__(self) -> float:
        return self.now

    def advance(self, s: float) -> None:
        self.now += s


def test_unknown_failures_open_short_circuit_after_threshold() -> None:
    clock = _Clock()
    health = ModelHealthRegistry(clock=clock, unknown_threshold=3, unknown_cooldown_s=30.0)
    ref = "prov/model"
    health.record_unknown_failure(ref)
    health.record_unknown_failure(ref)
    assert health.is_routable(ref) is True
    health.record_unknown_failure(ref)
    assert health.is_routable(ref) is False
    clock.advance(31)
    assert health.is_routable(ref) is True


def test_success_resets_unknown_count() -> None:
    health = ModelHealthRegistry(clock=_Clock(), unknown_threshold=3)
    ref = "prov/model"
    health.record_unknown_failure(ref)
    health.record_unknown_failure(ref)
    health.record_success(ref)
    health.record_unknown_failure(ref)
    health.record_unknown_failure(ref)
    assert health.is_routable(ref) is True
