from __future__ import annotations

from types import SimpleNamespace

from oi.infra.agents.providers.quota import QuotaLedger, parse_rate_limit_hint


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _exc_with_headers(headers: dict[str, str], message: str = "429 rate limited") -> Exception:
    exc = RuntimeError(message)
    exc.response = SimpleNamespace(headers=headers)  # type: ignore[attr-defined]
    return exc


def test_unknown_model_is_available() -> None:
    ledger = QuotaLedger(clock=_Clock())
    assert ledger.is_available("prov/model") is True


def test_retry_after_parks_model_until_reset() -> None:
    clock = _Clock()
    ledger = QuotaLedger(clock=clock)
    hint = ledger.learn_from_exception(
        "prov/model", _exc_with_headers({"retry-after": "30"})
    )
    assert hint is not None and hint.retry_after_s == 30.0
    assert ledger.is_available("prov/model") is False
    clock.advance(31)
    assert ledger.is_available("prov/model") is True


def test_rpm_ceiling_learned_from_headers_blocks_at_limit() -> None:
    clock = _Clock()
    ledger = QuotaLedger(clock=clock)
    ledger.learn_from_exception(
        "prov/model", _exc_with_headers({"x-ratelimit-limit-requests": "3"})
    )
    for _ in range(3):
        assert ledger.is_available("prov/model") is True
        ledger.record_request("prov/model")
    assert ledger.is_available("prov/model") is False
    clock.advance(61)
    assert ledger.is_available("prov/model") is True


def test_learned_ceiling_only_tightens() -> None:
    ledger = QuotaLedger(clock=_Clock())
    ledger.learn_from_exception(
        "prov/model", _exc_with_headers({"x-ratelimit-limit-requests": "100"})
    )
    ledger.learn_from_exception(
        "prov/model", _exc_with_headers({"x-ratelimit-limit-requests": "250"})
    )
    snap = ledger.snapshot("prov/model")
    assert snap["rpm_ceiling"] == 100


def test_message_phrasing_hint_parsed() -> None:
    hint = parse_rate_limit_hint(
        RuntimeError("Rate limit reached for model. Please try again in 20s.")
    )
    assert hint is not None and hint.retry_after_s == 20.0
    hint_min = parse_rate_limit_hint(RuntimeError("too many requests, try again in 2 minutes"))
    assert hint_min is not None and hint_min.retry_after_s == 120.0


def test_no_hint_returns_none_and_restricts_nothing() -> None:
    ledger = QuotaLedger(clock=_Clock())
    assert ledger.learn_from_exception("prov/model", RuntimeError("boom")) is None
    assert ledger.is_available("prov/model") is True
