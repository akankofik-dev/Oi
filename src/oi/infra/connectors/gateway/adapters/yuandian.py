"""Yuandian (元典) Legal AI gateway — laws, cases, enterprises via Open API."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

import httpx

BASE_URL = "https://open.chineselaw.com/open"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_laws",
        "description": "Pencarian semantik peraturan hukum dan pasal",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pertanyaan hukum bahasa natural atau kata kunci pencarian",
                },
                "return_num": {
                    "type": "integer",
                    "description": "Jumlah hasil, default 10",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_cases",
        "description": "Pencarian semantik putusan pengadilan dan kasus tipikal",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Deskripsi kasus bahasa natural atau kata kunci pencarian",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_enterprises",
        "description": "Cari kandidat perusahaan berdasar nama (dapatkan ID perusahaan / kode kredit sosial terpadu)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Kata kunci nama perusahaan"},
                "top_k": {
                    "type": "integer",
                    "description": "Jumlah kandidat, default 10, maks 50",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "get_enterprise",
        "description": "Cari daftar kandidat detail perusahaan berdasar nama perusahaan",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nama perusahaan, nama lama, atau singkatan saham",
                },
                "num": {
                    "type": "integer",
                    "description": "Jumlah hasil, default 2",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "detect_hallucination",
        "description": "Verifikasi apakah kutipan hukum dalam teks akurat (sekitar 15 detik, mohon tunggu)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Teks asli yang akan diverifikasi (berisi referensi peraturan/nomor kasus)",
                },
            },
            "required": ["text"],
        },
    },
]


def list_tools() -> list[dict[str, Any]]:
    return TOOLS


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    if name == "search_laws":
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        return_num = int(args.get("return_num") or 10)
        return_num = max(1, min(return_num, 45))
        return _request(
            creds,
            "POST",
            "law_vector_search",
            json_body={"query": query, "return_num": return_num},
        )
    if name == "search_cases":
        query = str(args.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        return _request(
            creds,
            "POST",
            "case_vector_search",
            json_body={"query": query},
        )
    if name == "search_enterprises":
        name_q = str(args.get("name") or "").strip()
        if not name_q:
            raise ValueError("name is required")
        top_k = int(args.get("top_k") or 10)
        top_k = max(1, min(top_k, 50))
        return _request(
            creds,
            "GET",
            "rh_enterpriseSearch",
            params={"name": name_q, "top_k": str(top_k)},
        )
    if name == "get_enterprise":
        name_q = str(args.get("name") or "").strip()
        if not name_q:
            raise ValueError("name is required")
        num = int(args.get("num") or 2)
        num = max(1, min(num, 50))
        return _request(
            creds,
            "GET",
            "rh_company_info",
            params={"name": name_q, "num": str(num)},
        )
    if name == "detect_hallucination":
        text = str(args.get("text") or "").strip()
        if not text:
            raise ValueError("text is required")
        return _request(
            creds,
            "POST",
            "hall_detect",
            json_body={"text": text},
            timeout=60.0,
        )
    raise ValueError(f"unknown tool: {name}")


def probe_credentials(creds: dict[str, Any]) -> None:
    _request(
        creds,
        "GET",
        "rh_enterpriseSearch",
        params={"name": "腾讯", "top_k": "1"},
    )


def _api_key(creds: dict[str, Any]) -> str:
    api_key = str(creds.get("api_key") or creds.get("token") or "").strip()
    if not api_key:
        raise ValueError("Isi API Key Yuandian")
    if not api_key.startswith("sk_"):
        raise ValueError("API Key Yuandian harus diawali sk_, salin Key lengkap dari platform terbuka")
    return api_key


def _request(
    creds: dict[str, Any],
    method: str,
    route: str,
    *,
    params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 45.0,
) -> str:
    headers = {
        "X-API-Key": _api_key(creds),
        "Accept": "application/json",
        "User-Agent": "oi-connector/0.1",
    }
    url = f"{BASE_URL}/{route}"
    if params:
        url = f"{url}?{urlencode(params)}"
    with httpx.Client(timeout=timeout) as client:
        if method == "GET":
            r = client.get(url, headers=headers)
        else:
            headers["Content-Type"] = "application/json; charset=utf-8"
            r = client.post(url, headers=headers, json=json_body or {})
        if r.status_code in (401, 403):
            raise ValueError(f"API Key Yuandian tidak valid: HTTP {r.status_code}")
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, dict):
        return str(payload)
    if payload.get("success") is False:
        msg = str(payload.get("message") or payload.get("error_code") or "error")
        if "api" in msg.lower() and "key" in msg.lower():
            raise ValueError(f"API Key Yuandian tidak valid: {msg}")
        raise ValueError(f"Galat antarmuka Yuandian: {msg}")
    code = payload.get("code")
    # OpenAPI success codes include 200 / 201; some endpoints omit code.
    if code is not None and code not in (0, 200, 201, "0", "200", "201"):
        msg = str(payload.get("message") or payload.get("msg") or code)
        low = msg.lower()
        if "api" in low and "key" in low:
            raise ValueError(f"API Key Yuandian tidak valid: {msg}")
        raise ValueError(f"Galat antarmuka Yuandian [{code}]: {msg}")
    return json.dumps(payload, ensure_ascii=False, indent=2)
