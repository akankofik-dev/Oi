"""Built-in connector catalog is JSON-backed and bilingual."""

from __future__ import annotations

from pathlib import Path

from oi.infra.connectors.catalog import (
    catalog_entry_to_dict,
    get_catalog_entry,
    list_catalog,
)


def test_catalog_localizes_name_description_and_fields() -> None:
    entry = get_catalog_entry("weknora")
    assert entry is not None
    id_ = catalog_entry_to_dict(entry, locale="id")
    en = catalog_entry_to_dict(entry, locale="en")
    assert id_["name"] == "WeKnora"
    assert id_["description"] == (
        "Hubungkan basis pengetahuan privat WeKnora, sediakan pencarian "
        "baca-saja dan baca dokumen"
    )
    assert en["description"] == (
        "Connect a private WeKnora knowledge base for read-only search and document reading"
    )
    id_fields = {item["key"]: item for item in id_["credential_fields"]}
    en_fields = {item["key"]: item for item in en["credential_fields"]}
    assert id_fields["base_url"]["label"] == "Alamat layanan"
    assert en_fields["base_url"]["label"] == "Service URL"
    assert id_fields["base_url"]["help"] == (
        "Otomatis dilengkapi jika belum mengandung /api/v1"
    )
    assert "appends /api/v1" in str(en_fields["base_url"]["help"])


def test_every_catalog_entry_has_en_and_id_copy() -> None:
    for entry in list_catalog():
        assert entry.name.en.strip()
        assert entry.name.id.strip()
        assert entry.description.en.strip()
        assert entry.description.id.strip()
        id_ = catalog_entry_to_dict(entry, locale="id")
        en = catalog_entry_to_dict(entry, locale="en")
        assert id_["name"] == entry.name.id
        assert en["name"] == entry.name.en
        assert id_["description"] == entry.description.id
        assert en["description"] == entry.description.en
        if entry.auth_hint is not None:
            assert id_["auth_hint"] == entry.auth_hint.id
            assert en["auth_hint"] == entry.auth_hint.en
        for field in entry.credential_fields:
            assert field.label.en.strip()
            assert field.label.id.strip()


def _docs_catalog_table_rows(text: str) -> list[tuple[str, str, str, str, str, str]]:
    header = "| Kind | Name | Nama | Category | Auth | MCP mode |"
    start = text.find(header)
    assert start >= 0, "docs/connectors.md is missing the catalog table header"
    rows: list[tuple[str, str, str, str, str, str]] = []
    for line in text[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 6:
            break
        kind = cells[0].strip("`")
        rows.append((kind, cells[1], cells[2], cells[3], cells[4], cells[5]))
    return rows


def test_docs_catalog_table_matches_json() -> None:
    docs = Path(__file__).resolve().parents[3] / "docs" / "connectors.md"
    text = docs.read_text(encoding="utf-8")
    expected = [
        (
            entry.kind,
            entry.name.en,
            entry.name.id,
            entry.category,
            entry.auth_kind,
            entry.mcp_mode,
        )
        for entry in list_catalog()
    ]
    assert _docs_catalog_table_rows(text) == expected
