"""tests/unit/test_slash_help.py"""

from __future__ import annotations

from oi.infra.gateway.slash.catalog import list_specs
from oi.infra.gateway.slash.help import format_help


def test_help_groups_by_category_id():
    text = format_help(list_specs(origin="ui"), "id")
    assert "**Perintah yang tersedia**" in text
    assert "**Inti**" in text
    assert "**Sesi**" in text
    assert "**Sistem**" in text
    assert "`/status`" in text
    assert "`/help`" in text
    # Core section should appear before session section
    assert text.index("Inti") < text.index("Sesi")


def test_help_groups_by_category_en():
    text = format_help(list_specs(origin="ui"), "en")
    assert "**Available commands**" in text
    assert "**Core**" in text
    assert "**Sessions**" in text
    assert text.index("Core") < text.index("Sessions")


def test_sessions_alias_in_catalog():
    from oi.infra.gateway.slash.catalog import spec_for

    assert spec_for("sessions") is not None
    assert spec_for("sessions").name == "list"  # type: ignore[union-attr]
    assert spec_for("models") is not None
    assert spec_for("models").name == "model"  # type: ignore[union-attr]
