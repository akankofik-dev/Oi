"""Unit tests for the fast-lane decision helper (optimizations/fast_lane)."""

from oi.infra.optimizations.auto_router import Intent
from oi.infra.optimizations.fast_lane import decide_fast_lane

FAST_REF = "fast-provider/fast-model"


def test_greeting_uses_fast_model():
    d = decide_fast_lane("halo bro", thread_used_tools=False, fast_model_ref=FAST_REF)
    assert d.use_fast_model is True
    assert d.intent is Intent.GREETING
    assert d.model_ref == FAST_REF


def test_short_message_uses_fast_model():
    d = decide_fast_lane("ok", thread_used_tools=False, fast_model_ref=FAST_REF)
    assert d.use_fast_model is True
    assert d.intent is Intent.SHORT


def test_coding_stays_on_full_model():
    d = decide_fast_lane(
        "tolong bikinin fungsi python buat sorting",
        thread_used_tools=False,
        fast_model_ref=FAST_REF,
    )
    assert d.use_fast_model is False
    assert d.intent is Intent.CODING


def test_complex_stays_on_full_model():
    d = decide_fast_lane(
        "jelaskan strategi marketing untuk startup",
        thread_used_tools=False,
        fast_model_ref=FAST_REF,
    )
    assert d.use_fast_model is False
    assert d.intent is Intent.COMPLEX


def test_thread_that_used_tools_stays_on_full_model():
    d = decide_fast_lane("halo bro", thread_used_tools=True, fast_model_ref=FAST_REF)
    assert d.use_fast_model is False
    assert "tools" in d.reason


def test_no_fast_model_configured_never_fast():
    d = decide_fast_lane("halo bro", thread_used_tools=False, fast_model_ref=None)
    assert d.use_fast_model is False
    assert d.model_ref is None
