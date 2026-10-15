"""Static connector catalog — bundled presets for HTTP MCP services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from oi.i18n import tr

AuthKind = Literal[
    "personal_token",
    "oauth2",
    "auth_code",
    "api_key",
    "imap_app_password",
    "session_cookie",
    "api_credentials",
    "custom_fields",
]

CredentialFieldType = Literal["text", "password", "url", "tags"]
RemoteTransport = Literal["raw_http", "streamable_http", "sse"]
McpMode = Literal["remote", "gateway", "internal"]
ConnectorCategory = Literal[
    "office",
    "knowledge",
    "travel",
    "productivity",
    "media",
    "professional",
    "self_hosted",
]


@dataclass(frozen=True)
class ConnectorCredentialField:
    key: str
    label: str
    field_type: CredentialFieldType = "text"
    required: bool = True
    placeholder: str | None = None
    help: str | None = None
    secret: bool = False


@dataclass(frozen=True)
class ConnectorCatalogEntry:
    kind: str
    name: str
    description: str
    auth_kind: AuthKind
    doc_url: str
    icon: str
    color: str
    phase: Literal["available", "coming_soon"]
    # remote: harness talks to the vendor URL.
    # gateway: in-process Python adapter; harness config is a name-only placeholder.
    # internal: Oi-hosted HTTP MCP at /api/internal/mcp; harness loads via HTTP.
    mcp_mode: McpMode
    category: ConnectorCategory
    quick_auth_url: str | None = None
    login_url: str | None = None
    guide_url: str | None = None
    manual_url: str | None = None
    auth_hint: str | None = None
    # Optional allowlist of tool names exposed to the LLM.
    # None means no restriction (all tools from the MCP server are available).
    allowed_tools: tuple[str, ...] | None = None
    # Catalog-driven remote MCP OAuth (Notion / Ardot / Linear…):
    # when auth_kind=oauth2 + mcp_mode=remote/internal and issuer + mcp_url are set,
    # Oi uses DCR + PKCE against oauth_issuer and talks to mcp_url.
    oauth_issuer: str | None = None
    mcp_url: str | None = None
    oauth_resource: str | None = None
    oauth_scopes: str | None = None
    mcp_user_agent: str | None = None
    credential_fields: tuple[ConnectorCredentialField, ...] = ()
    remote_transport: RemoteTransport = "raw_http"


def is_inprocess_gateway(entry: ConnectorCatalogEntry) -> bool:
    """Harness injects Python adapter tools; config is a name-only placeholder."""
    return entry.mcp_mode == "gateway"


def uses_internal_http_mcp(entry: ConnectorCatalogEntry) -> bool:
    """Harness loads Oi-hosted HTTP MCP at ``/api/internal/mcp``."""
    return entry.mcp_mode == "internal"


def is_mcp_oauth_remote(entry: ConnectorCatalogEntry) -> bool:
    """True when this catalog entry is a dynamic-OAuth MCP connector (remote or internal HTTP)."""
    return (
        entry.auth_kind == "oauth2"
        and entry.mcp_mode in {"remote", "internal"}
        and bool(entry.oauth_issuer)
        and bool(entry.mcp_url)
    )


def mcp_oauth_remote_kinds() -> frozenset[str]:
    return frozenset(e.kind for e in _CATALOG if is_mcp_oauth_remote(e))


def get_mcp_oauth_remote(kind: str) -> ConnectorCatalogEntry | None:
    entry = get_catalog_entry(kind)
    if entry is None or not is_mcp_oauth_remote(entry):
        return None
    return entry


_CATALOG: tuple[ConnectorCatalogEntry, ...] = (
    ConnectorCatalogEntry(
        kind="tencent-docs",
        name="腾讯文档",
        description="Baca tulis Dokumen Tencent, spreadsheet pintar, dan berkas ruang kerja",
        auth_kind="personal_token",
        doc_url="https://developer.cloud.tencent.com/mcp/server/11803",
        icon="tencent-docs",
        color="#0052d9",
        phase="available",
        mcp_mode="remote",
        category="office",
        quick_auth_url="https://docs.qq.com/open/auth/mcp.html",
        guide_url="https://developer.cloud.tencent.com/mcp/server/11803",
        manual_url="https://docs.qq.com/open/auth/mcp.html",
        auth_hint="Buka halaman otorisasi MCP untuk masuk, salin Token di halaman lalu tempel di bawah",
        allowed_tools=(
            "create_smartcanvas_by_mdx",
            "smartcanvas.read",
            "smartcanvas.edit",
            "smartcanvas.find",
            "manage.create_file",
            "scrape_url",
            "manage.export_file",
            "manage.search_file",
            "manage.set_privilege",
            "manage.folder_list",
        ),
    ),
    ConnectorCatalogEntry(
        kind="tencent-ima",
        name="腾讯 IMA",
        description="Baca tulis, pencarian, dan pengelolaan catatan serta basis pengetahuan",
        auth_kind="api_key",
        doc_url="https://qclaw.qq.com/docs/206424375046045696",
        icon="tencent-ima",
        color="#07c160",
        phase="available",
        mcp_mode="gateway",
        category="knowledge",
        quick_auth_url="https://ima.qq.com/agent-interface",
        manual_url="https://ima.qq.com/agent-interface",
        auth_hint="Klik 'Buka halaman otorisasi' untuk mendapatkan API Key dan Client ID di IMA (API Key hanya ditampilkan sekali)",
    ),
    ConnectorCatalogEntry(
        kind="tencent-meeting",
        name="腾讯会议",
        description="Pengelolaan, pencarian, perekaman rapat, dan notulen pintar",
        auth_kind="personal_token",
        doc_url="https://meeting.tencent.com/ai-skill.html",
        icon="tencent-meeting",
        color="#006eff",
        phase="available",
        mcp_mode="remote",
        category="office",
        quick_auth_url="https://meeting.tencent.com/ai-skill.html",
        guide_url="https://meeting.tencent.com/ai-skill.html",
        manual_url="https://meeting.tencent.com/ai-skill.html",
        auth_hint="Buka halaman otorisasi untuk masuk ke Tencent Meeting, salin Token di halaman lalu tempel di bawah",
    ),
    ConnectorCatalogEntry(
        kind="tencent-news",
        name="腾讯新闻",
        description="Pencarian berita dan langganan topik hangat",
        auth_kind="api_key",
        doc_url="https://news.qq.com/exchange?scene=appkey",
        icon="tencent-news",
        color="#1485ee",
        phase="available",
        mcp_mode="gateway",
        category="media",
        quick_auth_url="https://news.qq.com/exchange?scene=appkey",
        guide_url="https://qclaw.qq.com/docs/207612064014921728/",
        manual_url="https://news.qq.com/exchange?scene=appkey",
        auth_hint="Masuk ke halaman Skills Tencent News untuk membuat API Key lalu tempel di bawah (satu akun hanya satu Key)",
    ),
    ConnectorCatalogEntry(
        kind="wechat-reading",
        name="微信读书",
        description="Sinkronisasi rak buku dan catatan bacaan",
        auth_kind="api_key",
        doc_url="https://weread.qq.com/r/weread-skills",
        icon="wechat-reading",
        color="#1aad19",
        phase="available",
        mcp_mode="gateway",
        category="media",
        quick_auth_url="https://weread.qq.com/r/weread-skills",
        auth_hint="Masuk ke https://weread.qq.com/r/weread-skills untuk mendapatkan API Key berawalan wrk- lalu tempel di bawah",
    ),
    ConnectorCatalogEntry(
        kind="tencent-lexiang",
        name="腾讯乐享",
        description="Pencarian, pembacaan, pembuatan basis pengetahuan, dan pengelolaan dokumen",
        auth_kind="api_key",
        doc_url="https://qclaw.qq.com/docs/211858629271314432",
        icon="tencent-lexiang",
        color="#00c1de",
        phase="available",
        mcp_mode="remote",
        category="office",
        quick_auth_url="https://lexiangla.com/ai/claw",
        guide_url="https://qclaw.qq.com/docs/211858629271314432",
        manual_url="https://lexiangla.com/mcp",
        auth_hint="Buka halaman kredensial Lexiang untuk masuk, salin identitas perusahaan (company_from) dan token akses, isi masing-masing di bawah",
    ),
    ConnectorCatalogEntry(
        kind="tencent-weiyun",
        name="腾讯微云",
        description="MCP resmi: daftar, unggah, unduh, bagikan cloud drive, dan kelola berkas",
        auth_kind="personal_token",
        doc_url="https://www.weiyun.com/act/openclaw",
        icon="tencent-weiyun",
        color="#00a4ff",
        phase="available",
        mcp_mode="remote",
        category="office",
        quick_auth_url="https://www.weiyun.com/act/openclaw",
        guide_url="https://www.weiyun.com/act/openclaw",
        manual_url="https://www.weiyun.com/act/openclaw",
        auth_hint="Buka halaman konfigurasi Skill Weiyun untuk masuk, salin MCP Token lalu tempel di bawah",
        allowed_tools=(
            "weiyun.list",
            "weiyun.list_by_category",
            "weiyun.download",
            "weiyun.delete",
            "weiyun.upload",
            "weiyun.gen_share_link",
            "weiyun.rename_file",
            "weiyun.rename_dir",
            "weiyun.create_dir",
            "weiyun.move_dir",
            "weiyun.move_file",
            "check_skill_update",
        ),
    ),
    ConnectorCatalogEntry(
        kind="qq-mail",
        name="个人邮箱",
        description="Hubungkan QQ Mail, NetEase Mail, Gmail, dll melalui IMAP/SMTP",
        auth_kind="imap_app_password",
        doc_url="https://mail.qq.com/",
        icon="qq-mail",
        color="#12b7f5",
        phase="available",
        mcp_mode="gateway",
        category="productivity",
        manual_url="https://mail.qq.com/",
        auth_hint="Pilih penyedia email, aktifkan IMAP/SMTP di pengaturan email dan buat kode otorisasi lalu isi di bawah",
    ),
    ConnectorCatalogEntry(
        kind="qq-music",
        name="QQ 音乐",
        description="Cari lagu, tangga lagu, daftar putar, dan laporan dengar",
        auth_kind="api_key",
        doc_url="https://y.qq.com/n/ryqq_v2/qqmusic_skills",
        icon="qq-music",
        color="#31c27c",
        phase="available",
        mcp_mode="gateway",
        category="media",
        quick_auth_url="https://y.qq.com/n/ryqq_v2/qqmusic_skills",
        manual_url="https://y.qq.com/n/ryqq_v2/qqmusic_skills",
        auth_hint="Masuk ke halaman Skills QQ Music untuk membuat API Key berawalan qmk- lalu tempel di bawah",
    ),
    ConnectorCatalogEntry(
        kind="fliggy",
        name="飞猪",
        description="Pencarian pintar tiket pesawat, hotel, tempat wisata, dan rencana perjalanan",
        auth_kind="api_key",
        doc_url="https://flyai.open.fliggy.com/#playground",
        icon="fliggy",
        color="#ffc700",
        phase="available",
        mcp_mode="gateway",
        category="travel",
        quick_auth_url="https://flyai.open.fliggy.com/console",
        guide_url="https://qclaw.qq.com/docs/208142370404184064.html",
        manual_url="https://flyai.open.fliggy.com/console",
        auth_hint="Masuk ke konsol platform terbuka Fliggy AI untuk mendapatkan API Key lalu tempel di bawah",
    ),
    ConnectorCatalogEntry(
        kind="baidu-map",
        name="百度地图",
        description="Pencarian tempat, perencanaan rute, dan cek cuaca",
        auth_kind="api_key",
        doc_url="https://lbs.baidu.com/apiconsole/agentplan",
        icon="baidu-map",
        color="#3385ff",
        phase="available",
        mcp_mode="gateway",
        category="travel",
        quick_auth_url="https://lbs.baidu.com/apiconsole/agentplan",
        guide_url="https://lbsyun.baidu.com/products/agentplan",
        manual_url="https://lbs.baidu.com/apiconsole/agentplan",
        auth_hint="Dapatkan Token di konsol Agent Plan Baidu Map (berawalan sk-ap-) lalu tempel di bawah",
    ),
    ConnectorCatalogEntry(
        kind="ctrip-wendao",
        name="携程问道",
        description="Rekomendasi tanya jawab hotel, tiket pesawat, dan rencana perjalanan",
        auth_kind="api_key",
        doc_url="http://t.ctrip.cn/28J6RhL",
        icon="ctrip-wendao",
        color="#2577e3",
        phase="available",
        mcp_mode="gateway",
        category="travel",
        quick_auth_url="http://t.ctrip.cn/28J6RhL",
        guide_url="https://qclaw.qq.com/docs/208231741261246464.html",
        manual_url="http://t.ctrip.cn/28J6RhL",
        auth_hint=(
            "Buka halaman otorisasi Ctrip Wendao untuk mendapatkan Token lalu tempel di bawah (upstream tidak memvalidasi Token invalid, pastikan salinan lengkap)"
        ),
    ),
    ConnectorCatalogEntry(
        kind="meituan-travel",
        name="美团旅游助手",
        description="Tanya jawab hotel, tiket pesawat, tiket kereta, tempat wisata, dan rencana perjalanan",
        auth_kind="api_key",
        doc_url="https://developer.meituan.com/hotel-travel-skill",
        icon="meituan-travel",
        color="#ffc300",
        phase="available",
        mcp_mode="gateway",
        category="travel",
        quick_auth_url="https://developer.meituan.com/zh/v2/dev/token",
        guide_url="https://developer.meituan.com/hotel-travel-skill",
        manual_url="https://developer.meituan.com/zh/v2/dev/token",
        auth_hint=(
            "Dapatkan Token di halaman developer pribadi Meituan lalu tempel di bawah"
            "(Probe hanya memvalidasi format; ketersediaan nyata diverifikasi saat pemanggilan chat)"
        ),
    ),
    ConnectorCatalogEntry(
        kind="didi",
        name="滴滴",
        description="Estimasi/pesan kendaraan online, pencarian tempat, dan perencanaan rute perjalanan",
        auth_kind="api_key",
        doc_url="https://mcp.didichuxing.com/api",
        icon="didi",
        color="#ff6400",
        phase="available",
        mcp_mode="remote",
        category="travel",
        quick_auth_url="https://mcp.didichuxing.com",
        guide_url="https://mcp.didichuxing.com/api",
        manual_url="https://mcp.didichuxing.com",
        auth_hint="Buka konsol developer Didi untuk masuk dan aktifkan MCP Key pribadi, salin lalu tempel di bawah",
        remote_transport="streamable_http",
    ),
    ConnectorCatalogEntry(
        kind="yuandian",
        name="元典",
        description="Peraturan hukum, dokumen kasus, info perusahaan, dan deteksi halusinasi hukum",
        auth_kind="api_key",
        doc_url="https://open.chineselaw.com/profile",
        icon="yuandian",
        color="#1a56db",
        phase="available",
        mcp_mode="gateway",
        category="professional",
        quick_auth_url="https://open.chineselaw.com/profile",
        guide_url="https://open.chineselaw.com/llms.txt",
        manual_url="https://open.chineselaw.com/profile",
        auth_hint="Masuk ke platform terbuka Yuandian untuk mendapatkan API Key berawalan sk_ lalu tempel di bawah",
    ),
    ConnectorCatalogEntry(
        kind="qcc",
        name="企查查",
        description="OAuth sekali klik atau tempel API Key untuk akses lima kategori data: perusahaan, risiko, kekayaan intelektual, operasional, serta direksi & komisaris",
        auth_kind="oauth2",
        doc_url="https://agent.qcc.com/",
        icon="qcc",
        color="#008CFF",
        phase="available",
        mcp_mode="internal",
        category="professional",
        quick_auth_url="https://agent.qcc.com/",
        guide_url="https://agent.qcc.com/guide",
        manual_url="https://agent.qcc.com/",
        auth_hint="OAuth sekali klik tersedia jika ada HTTPS publik atau localhost; jika tidak, buka halaman otorisasi untuk mendapatkan API Key lalu tempel. Cakupan pencarian mengikuti izin akun.",
        oauth_issuer="https://agent.qcc.com",
        mcp_url="https://agent.qcc.com/mcp/company/stream",
        oauth_resource="https://agent.qcc.com/mcp/company/stream",
        oauth_scopes="mcp:tools",
        remote_transport="streamable_http",
    ),
    ConnectorCatalogEntry(
        kind="tencent-ardot",
        name="腾讯设计 Ardot",
        description="MCP resmi platform desain Tencent: baca tulis desain, sistem desain, dan ekspor",
        auth_kind="oauth2",
        doc_url="https://docs.ardot.tencent.com/ardot-mcp/introduction.html",
        icon="tencent-ardot",
        color="#8b5cf6",
        phase="available",
        mcp_mode="remote",
        category="office",
        guide_url="https://docs.ardot.tencent.com/ardot-mcp.html",
        auth_hint="Klik 'Otorisasi sekali klik' untuk menyelesaikan login Ardot (otomatis tersimpan jika berhasil), atau tempel Token manual sesuai dokumen",
        oauth_issuer="https://ardot.tencent.com",
        mcp_url="https://ardot.tencent.com/mcp",
        oauth_resource="https://ardot.tencent.com/mcp",
    ),
    ConnectorCatalogEntry(
        kind="youdao-note",
        name="有道云笔记",
        description="MCP resmi: buat, cari, rapikan, dan kelola catatan",
        auth_kind="personal_token",
        doc_url="https://qclaw.qq.com/docs/207508177113886720",
        icon="youdao-note",
        color="#00c853",
        phase="available",
        mcp_mode="remote",
        category="knowledge",
        quick_auth_url="https://mopen.163.com/#/dashboard",
        guide_url="https://qclaw.qq.com/docs/207508177113886720",
        manual_url="https://mopen.163.com/#/dashboard",
        auth_hint="Klik 'Buka halaman otorisasi' untuk masuk ke platform MCP, buat API Key di manajemen API lalu tempel di bawah",
    ),
    ConnectorCatalogEntry(
        kind="notion",
        name="Notion",
        description="MCP resmi: cari, baca tulis halaman dan database",
        auth_kind="oauth2",
        doc_url="https://developers.notion.com/docs/mcp",
        icon="notion",
        color="#000000",
        phase="available",
        mcp_mode="remote",
        category="knowledge",
        guide_url="https://developers.notion.com/guides/mcp/get-started-with-mcp",
        auth_hint="Klik 'Otorisasi sekali klik' untuk menyelesaikan login Notion (otomatis tersimpan jika berhasil), atau dapatkan Token manual sesuai dokumen resmi",
        oauth_issuer="https://mcp.notion.com",
        mcp_url="https://mcp.notion.com/mcp",
        mcp_user_agent="oi-connector/0.1",
    ),
    ConnectorCatalogEntry(
        kind="openalex",
        name="OpenAlex",
        description="MCP resmi: cari literatur akademik, kutipan, entitas riset, dan analisis statistik",
        auth_kind="oauth2",
        doc_url="https://help.openalex.org/access/connector/",
        icon="openalex",
        color="#1f6feb",
        phase="available",
        mcp_mode="remote",
        category="knowledge",
        guide_url="https://help.openalex.org/access/connector/",
        auth_hint="Klik 'Otorisasi sekali klik' untuk masuk ke OpenAlex (di desktop gunakan browser sistem); pencarian akan memakai API Key dan budget harianmu sendiri.",
        oauth_issuer="https://mcp.openalex.org",
        mcp_url="https://mcp.openalex.org/mcp",
        oauth_resource="https://mcp.openalex.org/mcp",
        oauth_scopes="openalex:query",
        remote_transport="streamable_http",
    ),
    ConnectorCatalogEntry(
        kind="dida365",
        name="滴答清单",
        description="MCP resmi: tugas, daftar, kebiasaan, dan catatan fokus",
        auth_kind="oauth2",
        doc_url="https://help.dida365.com/articles/7438132116019216384",
        icon="dida365",
        color="#e74c3c",
        phase="available",
        mcp_mode="remote",
        category="productivity",
        guide_url="https://help.dida365.com/articles/7438132116019216384",
        manual_url="https://dida365.com",
        auth_hint="Klik 'Otorisasi sekali klik' untuk menyelesaikan login (otomatis tersimpan jika berhasil), atau buat Token di versi web 'Avatar → Pengaturan → Akun & Keamanan → Kata sandi API' lalu tempel",
        oauth_issuer="https://dida365.com",
        mcp_url="https://mcp.dida365.com",
        oauth_resource="https://mcp.dida365.com/",
        oauth_scopes="tasks:read tasks:write",
    ),
    ConnectorCatalogEntry(
        kind="feishu-cli",
        name="飞书 CLI",
        description="Kelola dokumen, tabel multidimensi, kalender, dan pesan via lark-cli resmi (perlu CLI terpasang di host)",
        auth_kind="api_key",
        doc_url="https://github.com/larksuite/cli",
        icon="feishu-cli",
        color="#3370ff",
        phase="available",
        mcp_mode="gateway",
        category="office",
        guide_url="https://open.feishu.cn/document/mcp_open_tools/feishu-cli/set-up-lark-cli-for-ai-agents-in-openclaw_hermes.md",
        manual_url="https://open.feishu.cn/app",
        auth_hint="Isi App ID dan App Secret aplikasi Feishu; pencarian dokumen perlu klik 'Otorisasi Masuk' lagi",
    ),
    ConnectorCatalogEntry(
        kind="wecom-cli",
        name="企业微信 CLI",
        description="Kelola dokumen, jadwal, dan pesan via wecom-cli resmi (perlu CLI terpasang di host)",
        auth_kind="api_key",
        doc_url="https://github.com/WecomTeam/wecom-cli",
        icon="wecom-cli",
        color="#2f7bf6",
        phase="available",
        mcp_mode="gateway",
        category="office",
        guide_url="https://open.work.weixin.qq.com/help2/pc/21676",
        manual_url="https://open.work.weixin.qq.com/help2/pc/cat?doc_id=21677",
        auth_hint="Isi Bot ID dan Secret robot pintar koneksi panjang; host harus sudah memasang @wecom/cli (wecom-cli)",
    ),
    ConnectorCatalogEntry(
        kind="agently-cli",
        name="Agent Mail",
        description="Gunakan email Agent independen via Agent Mail CLI resmi (perlu CLI terpasang di host)",
        auth_kind="custom_fields",
        doc_url="https://github.com/Tencent/AgentlyMail",
        icon="agently-cli",
        color="#0052d9",
        phase="available",
        mcp_mode="gateway",
        category="office",
        guide_url="https://help.agent.qq.com/detail/0/1092",
        manual_url="https://agent.qq.com/",
        auth_hint="Simpan konektor dulu, lalu selesaikan otorisasi kode perangkat; setiap instance mengikat email secara independen",
    ),
    ConnectorCatalogEntry(
        kind="weknora",
        name="WeKnora",
        description="Hubungkan basis pengetahuan privat WeKnora, sediakan pencarian baca-saja dan baca dokumen",
        auth_kind="custom_fields",
        doc_url="https://github.com/Tencent/WeKnora",
        icon="weknora",
        color="#0052d9",
        phase="available",
        mcp_mode="gateway",
        category="knowledge",
        guide_url="https://github.com/Tencent/WeKnora/blob/main/docs/api/README.md",
        auth_hint="Isi alamat layanan WeKnora; API Key dan Tenant ID diisi sesuai pengaturan autentikasi deployment.",
        credential_fields=(
            ConnectorCredentialField(
                key="base_url",
                label="Alamat layanan",
                field_type="url",
                placeholder="http://127.0.0.1:8080 atau https://weknora.example.com",
                help="Otomatis dilengkapi jika belum mengandung /api/v1",
            ),
            ConnectorCredentialField(
                key="api_key",
                label="API Key",
                field_type="password",
                required=False,
                placeholder="sk-... (boleh kosong untuk deployment tanpa autentikasi)",
                secret=True,
            ),
            ConnectorCredentialField(
                key="tenant_id",
                label="Tenant ID",
                required=False,
                help="Diisi saat API Key tingkat platform perlu menentukan ruang kerja",
            ),
            ConnectorCredentialField(
                key="knowledge_base_ids",
                label="ID basis pengetahuan default",
                field_type="tags",
                required=False,
                placeholder="kb-123, kb-456",
                help="Jika kosong, cari semua basis pengetahuan yang terlihat oleh kredensial saat ini",
            ),
        ),
    ),
    ConnectorCatalogEntry(
        kind="dify",
        name="Dify",
        description="Hubungkan layanan MCP dari aplikasi atau alur kerja Dify yang sudah dipublikasi",
        auth_kind="custom_fields",
        doc_url="https://docs.dify.ai/",
        icon="dify",
        color="#1c64f2",
        phase="available",
        mcp_mode="remote",
        category="self_hosted",
        auth_hint="Aktifkan MCP di titik akses aplikasi Dify, lalu tempel URL Server MCP yang lengkap.",
        credential_fields=(
            ConnectorCredentialField(
                key="mcp_url",
                label="MCP Server URL",
                field_type="url",
                placeholder="https://dify.example.com/mcp/server/<server_code>/mcp",
                help="URL lengkap berisi identitas akses, akan disimpan terenkripsi sebagai rahasia",
                secret=True,
            ),
        ),
        remote_transport="streamable_http",
    ),
)


def list_catalog() -> list[ConnectorCatalogEntry]:
    return list(_CATALOG)


def get_catalog_entry(kind: str) -> ConnectorCatalogEntry | None:
    for entry in _CATALOG:
        if entry.kind == kind:
            return entry
    return None


def catalog_entry_to_dict(
    entry: ConnectorCatalogEntry, *, oauth_ready: bool = False, locale: str = "en"
) -> dict[str, object]:
    from oi.infra.connectors.oauth import oauth_mode_for_kind  # noqa: PLC0415

    oauth_mode = oauth_mode_for_kind(entry.kind)
    return {
        "kind": entry.kind,
        "name": entry.name,
        "description": tr("connector.agently.description", locale)
        if entry.kind == "agently-cli"
        else entry.description,
        "auth_kind": entry.auth_kind,
        "doc_url": entry.doc_url,
        "icon": entry.icon,
        "color": entry.color,
        "phase": entry.phase,
        "mcp_mode": entry.mcp_mode,
        "category": entry.category,
        "quick_auth_url": entry.quick_auth_url,
        "login_url": entry.login_url,
        "guide_url": entry.guide_url or entry.doc_url,
        "manual_url": entry.manual_url or entry.guide_url or entry.doc_url,
        "auth_hint": tr("connector.agently.auth_hint", locale)
        if entry.kind == "agently-cli"
        else entry.auth_hint,
        "oauth_mode": oauth_mode,
        "oauth_ready": oauth_ready,
        "credential_fields": [
            {
                "key": field.key,
                "label": field.label,
                "field_type": field.field_type,
                "required": field.required,
                "placeholder": field.placeholder,
                "help": field.help,
                "secret": field.secret,
            }
            for field in entry.credential_fields
        ],
        "supports_quick_auth": entry.phase == "available" and entry.auth_kind != "api_credentials",
    }
