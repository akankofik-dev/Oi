"""Voice probe / Tencent error copy."""

from __future__ import annotations

import httpx

from oi.i18n.domains.voice import (
    format_voice_probe_error,
    realtime_error_message,
    tencent_api_language,
)


def test_tencent_secret_id_is_localized() -> None:
    exc = RuntimeError("AuthFailure.SecretIdNotFound: The SecretId is not found.")
    assert format_voice_probe_error(exc, "en") == (
        "SecretId was not found. Check that the key is correct."
    )
    assert format_voice_probe_error(exc, "id") == "SecretId tidak ditemukan. Periksa bahwa kunci sudah benar."


def test_unknown_provider_text_is_kept() -> None:
    exc = RuntimeError("SomeVendor.NewCode: unexplained boom")
    assert format_voice_probe_error(exc, "id") == "SomeVendor.NewCode: unexplained boom"


def test_http_and_network_errors_are_localized() -> None:
    request = httpx.Request("POST", "https://asr.tencentcloudapi.com/")
    response = httpx.Response(500, request=request)
    status = httpx.HTTPStatusError("server error", request=request, response=response)
    assert format_voice_probe_error(status, "id") == "provider mengembalikan HTTP 500"
    assert format_voice_probe_error(httpx.ConnectError("boom"), "id") == "kesalahan jaringan: ConnectError"


def test_tencent_api_language_header() -> None:
    assert tencent_api_language("id") == "en-US"
    assert tencent_api_language("en") == "en-US"
    assert tencent_api_language(None) is None


def test_realtime_error_codes_are_localized() -> None:
    assert realtime_error_message(4003, "id") == "Pengenalan ucapan realtime belum diaktifkan untuk akun Tencent Cloud ini."
    assert realtime_error_message(4004, "en") == (
        "The Tencent Cloud realtime speech recognition resource pack is exhausted."
    )
    # 5001 / 5002 是同一个偶发故障文案
    assert realtime_error_message(5002, "id") == "Layanan Tencent Cloud sedang tidak tersedia sementara. Coba lagi sebentar."


def test_unknown_realtime_code_falls_back() -> None:
    assert realtime_error_message(4999, "id") == "Pengenalan ucapan realtime gagal. Coba lagi sebentar."
    assert realtime_error_message(None, "en") == (
        "Realtime speech recognition failed. Retry in a moment."
    )
