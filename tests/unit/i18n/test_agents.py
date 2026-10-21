"""Tests for agents i18n domain."""

from __future__ import annotations

from oi.i18n.domains.agents import (
    AGENT_START_TIMEOUT,
    MODEL_REF_UNAVAILABLE,
    NO_MODELS_CONFIGURED,
    agent_error_message,
    agent_state_label,
)




def test_agent_state_label_failed_en() -> None:
    assert agent_state_label("failed", "en") == "Start failed"


def test_agent_state_label_unknown_state_passthrough() -> None:
    assert agent_state_label("custom", "en") == "custom"










def test_classify_no_enabled_models() -> None:
    from oi.i18n.domains.agents import classify_agent_start_error_message

    assert (
        classify_agent_start_error_message("No enabled models found in providers")
        == NO_MODELS_CONFIGURED
    )


def test_classify_unknown_provider() -> None:
    from oi.i18n.domains.agents import classify_agent_start_error_message

    msg = "Unknown provider 'missing' in model ref 'missing/gpt-4'"
    assert classify_agent_start_error_message(msg) == MODEL_REF_UNAVAILABLE
