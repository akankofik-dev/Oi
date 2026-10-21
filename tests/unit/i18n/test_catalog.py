"""tests/unit/i18n/test_catalog.py"""

from __future__ import annotations

import pytest

from oi.i18n import all_keys_for_locale, tr
from oi.infra.gateway.slash.catalog import CATALOG, category_label


def test_en_and_id_share_same_keys():
    en_keys = all_keys_for_locale("en")
    id_keys = all_keys_for_locale("id")
    assert en_keys == id_keys
    assert "errors.AGENT_NAME_TAKEN" in en_keys


def test_tr_locales_and_removed_zh_fallback():
    assert tr("slash.help.title", "en") == "Available commands"
    assert tr("slash.help.title", "id") == "Perintah yang tersedia"
    # zh was removed as a UI locale; it now resolves to Indonesian.
    assert tr("slash.help.title", "zh") == "Perintah yang tersedia"


def test_tr_interpolation():
    text = tr("slash.error.unknown_command", "en", name="foo")
    assert "/foo" in text


def test_tr_missing_key_raises():
    with pytest.raises(KeyError):
        tr("slash.no.such.key", "en")


def test_catalog_labels_match_json():
    for spec in CATALOG:
        assert spec.label_en == tr(f"slash.catalog.{spec.name}.label", "en")
        assert spec.label_zh == tr(f"slash.catalog.{spec.name}.label", "zh")


def test_category_labels():
    assert category_label("core", "en") == "Core"
    assert category_label("core", "id") == "Inti"
