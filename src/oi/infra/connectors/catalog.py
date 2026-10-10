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
<<<<<<< HEAD
        description="读写腾讯文档、智能表格与空间文件",
=======
        description="Baca tulis Dokumen Tencent, spreadsheet pintar, dan berkas ruang kerja",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="打开 MCP 授权页登录，复制页面上的 Token 并粘贴到下方",
=======
        auth_hint="Buka halaman otorisasi MCP untuk masuk, salin Token di halaman lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        description="笔记与知识库读写、检索与管理",
=======
        description="Baca tulis, pencarian, dan pengelolaan catatan serta basis pengetahuan",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="api_key",
        doc_url="https://qclaw.qq.com/docs/206424375046045696",
        icon="tencent-ima",
        color="#07c160",
        phase="available",
        mcp_mode="gateway",
        category="knowledge",
        quick_auth_url="https://ima.qq.com/agent-interface",
        manual_url="https://ima.qq.com/agent-interface",
<<<<<<< HEAD
        auth_hint="点击「打开授权页」在 IMA 中获取 API Key 与 Client ID（API Key 仅展示一次）",
=======
        auth_hint="Klik 'Buka halaman otorisasi' untuk mendapatkan API Key dan Client ID di IMA (API Key hanya ditampilkan sekali)",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="tencent-meeting",
        name="腾讯会议",
<<<<<<< HEAD
        description="会议管理、查询、录制与智能纪要",
=======
        description="Pengelolaan, pencarian, perekaman rapat, dan notulen pintar",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="打开授权页登录腾讯会议，复制页面上的 Token 并粘贴到下方",
=======
        auth_hint="Buka halaman otorisasi untuk masuk ke Tencent Meeting, salin Token di halaman lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="tencent-news",
        name="腾讯新闻",
<<<<<<< HEAD
        description="新闻搜索与热点订阅",
=======
        description="Pencarian berita dan langganan topik hangat",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="登录腾讯新闻 Skills 页生成 API Key 并粘贴到下方（每个账号仅一个 Key）",
=======
        auth_hint="Masuk ke halaman Skills Tencent News untuk membuat API Key lalu tempel di bawah (satu akun hanya satu Key)",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="wechat-reading",
        name="微信读书",
<<<<<<< HEAD
        description="书架同步与读书笔记",
=======
        description="Sinkronisasi rak buku dan catatan bacaan",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="api_key",
        doc_url="https://weread.qq.com/r/weread-skills",
        icon="wechat-reading",
        color="#1aad19",
        phase="available",
        mcp_mode="gateway",
        category="media",
        quick_auth_url="https://weread.qq.com/r/weread-skills",
<<<<<<< HEAD
        auth_hint="登录 https://weread.qq.com/r/weread-skills 获取 wrk- 开头的 API Key 后粘贴到下方",
=======
        auth_hint="Masuk ke https://weread.qq.com/r/weread-skills untuk mendapatkan API Key berawalan wrk- lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="tencent-lexiang",
        name="腾讯乐享",
<<<<<<< HEAD
        description="知识库检索、阅读、创建与文档管理",
=======
        description="Pencarian, pembacaan, pembuatan basis pengetahuan, dan pengelolaan dokumen",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="打开乐享凭证页登录，复制企业标识（company_from）与访问令牌，分别填入下方",
=======
        auth_hint="Buka halaman kredensial Lexiang untuk masuk, salin identitas perusahaan (company_from) dan token akses, isi masing-masing di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="tencent-weiyun",
        name="腾讯微云",
<<<<<<< HEAD
        description="官方 MCP：网盘列表、上传、下载、分享与文件管理",
=======
        description="MCP resmi: daftar, unggah, unduh, bagikan cloud drive, dan kelola berkas",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="打开微云 Skill 配置页登录，复制 MCP Token 并粘贴到下方",
=======
        auth_hint="Buka halaman konfigurasi Skill Weiyun untuk masuk, salin MCP Token lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        description="通过 IMAP/SMTP 连接 QQ 邮箱、网易邮箱、Gmail 等",
=======
        description="Hubungkan QQ Mail, NetEase Mail, Gmail, dll melalui IMAP/SMTP",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="imap_app_password",
        doc_url="https://mail.qq.com/",
        icon="qq-mail",
        color="#12b7f5",
        phase="available",
        mcp_mode="gateway",
        category="productivity",
        manual_url="https://mail.qq.com/",
<<<<<<< HEAD
        auth_hint="选择邮箱服务商，在邮箱设置中开启 IMAP/SMTP 并生成授权码后填入下方",
=======
        auth_hint="Pilih penyedia email, aktifkan IMAP/SMTP di pengaturan email dan buat kode otorisasi lalu isi di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="qq-music",
        name="QQ 音乐",
<<<<<<< HEAD
        description="搜歌、排行榜、歌单与听歌报告",
=======
        description="Cari lagu, tangga lagu, daftar putar, dan laporan dengar",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="api_key",
        doc_url="https://y.qq.com/n/ryqq_v2/qqmusic_skills",
        icon="qq-music",
        color="#31c27c",
        phase="available",
        mcp_mode="gateway",
        category="media",
        quick_auth_url="https://y.qq.com/n/ryqq_v2/qqmusic_skills",
        manual_url="https://y.qq.com/n/ryqq_v2/qqmusic_skills",
<<<<<<< HEAD
        auth_hint="登录 QQ 音乐 Skills 页生成 qmk- 开头的 API Key 并粘贴到下方",
=======
        auth_hint="Masuk ke halaman Skills QQ Music untuk membuat API Key berawalan qmk- lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="fliggy",
        name="飞猪",
<<<<<<< HEAD
        description="机票、酒店、景点与行程智能搜索",
=======
        description="Pencarian pintar tiket pesawat, hotel, tempat wisata, dan rencana perjalanan",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="登录飞猪 AI 开放平台控制台获取 API Key 并粘贴到下方",
=======
        auth_hint="Masuk ke konsol platform terbuka Fliggy AI untuk mendapatkan API Key lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="baidu-map",
        name="百度地图",
<<<<<<< HEAD
        description="地点检索、路线规划与天气查询",
=======
        description="Pencarian tempat, perencanaan rute, dan cek cuaca",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="在百度地图 Agent Plan 控制台获取 Token（sk-ap- 开头）并粘贴到下方",
=======
        auth_hint="Dapatkan Token di konsol Agent Plan Baidu Map (berawalan sk-ap-) lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="ctrip-wendao",
        name="携程问道",
<<<<<<< HEAD
        description="酒店、机票与行程问答推荐",
=======
        description="Rekomendasi tanya jawab hotel, tiket pesawat, dan rencana perjalanan",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
            "打开携程问道授权页获取 Token 并粘贴到下方（上游不校验无效 Token，请确认复制完整）"
=======
            "Buka halaman otorisasi Ctrip Wendao untuk mendapatkan Token lalu tempel di bawah (upstream tidak memvalidasi Token invalid, pastikan salinan lengkap)"
>>>>>>> 29e22aa (Oi v1.0.6)
        ),
    ),
    ConnectorCatalogEntry(
        kind="meituan-travel",
        name="美团旅游助手",
<<<<<<< HEAD
        description="酒店、机票、火车票、景点与行程问答",
=======
        description="Tanya jawab hotel, tiket pesawat, tiket kereta, tempat wisata, dan rencana perjalanan",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
            "在美团个人开发者页面获取 Token 并粘贴到下方"
            "（探测仅校验格式；真实可用性在对话调用时验证）"
=======
            "Dapatkan Token di halaman developer pribadi Meituan lalu tempel di bawah"
            "(Probe hanya memvalidasi format; ketersediaan nyata diverifikasi saat pemanggilan chat)"
>>>>>>> 29e22aa (Oi v1.0.6)
        ),
    ),
    ConnectorCatalogEntry(
        kind="didi",
        name="滴滴",
<<<<<<< HEAD
        description="网约车预估/叫车、地点检索与出行路线规划",
=======
        description="Estimasi/pesan kendaraan online, pencarian tempat, dan perencanaan rute perjalanan",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="打开滴滴开发者控制台登录并激活个人 MCP Key，复制后粘贴到下方",
=======
        auth_hint="Buka konsol developer Didi untuk masuk dan aktifkan MCP Key pribadi, salin lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
        remote_transport="streamable_http",
    ),
    ConnectorCatalogEntry(
        kind="yuandian",
        name="元典",
<<<<<<< HEAD
        description="法律法规、案例文书、企业信息与法律幻觉检测",
=======
        description="Peraturan hukum, dokumen kasus, info perusahaan, dan deteksi halusinasi hukum",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="登录元典开放平台获取 sk_ 开头的 API Key 并粘贴到下方",
=======
        auth_hint="Masuk ke platform terbuka Yuandian untuk mendapatkan API Key berawalan sk_ lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="qcc",
        name="企查查",
<<<<<<< HEAD
        description="一键 OAuth 或粘贴 API Key，接入企业、风险、知识产权、经营及董监高五类数据",
=======
        description="OAuth sekali klik atau tempel API Key untuk akses lima kategori data: perusahaan, risiko, kekayaan intelektual, operasional, serta direksi & komisaris",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="有公网 HTTPS 或本机 localhost 时可用一键 OAuth；否则打开授权页获取 API Key 后粘贴。查询范围以账户权限为准。",
=======
        auth_hint="OAuth sekali klik tersedia jika ada HTTPS publik atau localhost; jika tidak, buka halaman otorisasi untuk mendapatkan API Key lalu tempel. Cakupan pencarian mengikuti izin akun.",
>>>>>>> 29e22aa (Oi v1.0.6)
        oauth_issuer="https://agent.qcc.com",
        mcp_url="https://agent.qcc.com/mcp/company/stream",
        oauth_resource="https://agent.qcc.com/mcp/company/stream",
        oauth_scopes="mcp:tools",
        remote_transport="streamable_http",
    ),
    ConnectorCatalogEntry(
        kind="tencent-ardot",
        name="腾讯设计 Ardot",
<<<<<<< HEAD
        description="腾讯设计平台官方 MCP：设计稿读写、设计系统与导出",
=======
        description="MCP resmi platform desain Tencent: baca tulis desain, sistem desain, dan ekspor",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="oauth2",
        doc_url="https://docs.ardot.tencent.com/ardot-mcp/introduction.html",
        icon="tencent-ardot",
        color="#8b5cf6",
        phase="available",
        mcp_mode="remote",
        category="office",
        guide_url="https://docs.ardot.tencent.com/ardot-mcp.html",
<<<<<<< HEAD
        auth_hint="点击「一键授权」完成 Ardot 登录（成功后自动保存），或按文档手动粘贴 Token",
=======
        auth_hint="Klik 'Otorisasi sekali klik' untuk menyelesaikan login Ardot (otomatis tersimpan jika berhasil), atau tempel Token manual sesuai dokumen",
>>>>>>> 29e22aa (Oi v1.0.6)
        oauth_issuer="https://ardot.tencent.com",
        mcp_url="https://ardot.tencent.com/mcp",
        oauth_resource="https://ardot.tencent.com/mcp",
    ),
    ConnectorCatalogEntry(
        kind="youdao-note",
        name="有道云笔记",
<<<<<<< HEAD
        description="官方 MCP：笔记创建、搜索、整理与管理",
=======
        description="MCP resmi: buat, cari, rapikan, dan kelola catatan",
>>>>>>> 29e22aa (Oi v1.0.6)
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
<<<<<<< HEAD
        auth_hint="点击「打开授权页」登录 MCP 平台，在 API 管理创建 API Key 并粘贴到下方",
=======
        auth_hint="Klik 'Buka halaman otorisasi' untuk masuk ke platform MCP, buat API Key di manajemen API lalu tempel di bawah",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="notion",
        name="Notion",
<<<<<<< HEAD
        description="官方 MCP：搜索、读写页面与数据库",
=======
        description="MCP resmi: cari, baca tulis halaman dan database",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="oauth2",
        doc_url="https://developers.notion.com/docs/mcp",
        icon="notion",
        color="#000000",
        phase="available",
        mcp_mode="remote",
        category="knowledge",
        guide_url="https://developers.notion.com/guides/mcp/get-started-with-mcp",
<<<<<<< HEAD
        auth_hint="点击「一键授权」完成 Notion 登录（成功后自动保存），或按官方文档手动获取 Token",
=======
        auth_hint="Klik 'Otorisasi sekali klik' untuk menyelesaikan login Notion (otomatis tersimpan jika berhasil), atau dapatkan Token manual sesuai dokumen resmi",
>>>>>>> 29e22aa (Oi v1.0.6)
        oauth_issuer="https://mcp.notion.com",
        mcp_url="https://mcp.notion.com/mcp",
        mcp_user_agent="oi-connector/0.1",
    ),
    ConnectorCatalogEntry(
        kind="openalex",
        name="OpenAlex",
<<<<<<< HEAD
        description="官方 MCP：检索学术文献、引文、研究实体与统计分析",
=======
        description="MCP resmi: cari literatur akademik, kutipan, entitas riset, dan analisis statistik",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="oauth2",
        doc_url="https://help.openalex.org/access/connector/",
        icon="openalex",
        color="#1f6feb",
        phase="available",
        mcp_mode="remote",
        category="knowledge",
        guide_url="https://help.openalex.org/access/connector/",
<<<<<<< HEAD
        auth_hint="点击「一键授权」登录 OpenAlex（桌面端请用系统浏览器）；查询将使用你自己的 API Key 与每日预算。",
=======
        auth_hint="Klik 'Otorisasi sekali klik' untuk masuk ke OpenAlex (di desktop gunakan browser sistem); pencarian akan memakai API Key dan budget harianmu sendiri.",
>>>>>>> 29e22aa (Oi v1.0.6)
        oauth_issuer="https://mcp.openalex.org",
        mcp_url="https://mcp.openalex.org/mcp",
        oauth_resource="https://mcp.openalex.org/mcp",
        oauth_scopes="openalex:query",
        remote_transport="streamable_http",
    ),
    ConnectorCatalogEntry(
        kind="dida365",
        name="滴答清单",
<<<<<<< HEAD
        description="官方 MCP：任务、清单、习惯与专注记录",
=======
        description="MCP resmi: tugas, daftar, kebiasaan, dan catatan fokus",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="oauth2",
        doc_url="https://help.dida365.com/articles/7438132116019216384",
        icon="dida365",
        color="#e74c3c",
        phase="available",
        mcp_mode="remote",
        category="productivity",
        guide_url="https://help.dida365.com/articles/7438132116019216384",
        manual_url="https://dida365.com",
<<<<<<< HEAD
        auth_hint="点击「一键授权」完成登录（成功后自动保存），或在网页版「头像 → 设置 → 账户与安全 → API 口令」创建并粘贴 Token",
=======
        auth_hint="Klik 'Otorisasi sekali klik' untuk menyelesaikan login (otomatis tersimpan jika berhasil), atau buat Token di versi web 'Avatar → Pengaturan → Akun & Keamanan → Kata sandi API' lalu tempel",
>>>>>>> 29e22aa (Oi v1.0.6)
        oauth_issuer="https://dida365.com",
        mcp_url="https://mcp.dida365.com",
        oauth_resource="https://mcp.dida365.com/",
        oauth_scopes="tasks:read tasks:write",
    ),
    ConnectorCatalogEntry(
        kind="feishu-cli",
        name="飞书 CLI",
<<<<<<< HEAD
        description="通过官方 lark-cli 操作文档、多维表格、日历与消息（需主机安装 CLI）",
=======
        description="Kelola dokumen, tabel multidimensi, kalender, dan pesan via lark-cli resmi (perlu CLI terpasang di host)",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="api_key",
        doc_url="https://github.com/larksuite/cli",
        icon="feishu-cli",
        color="#3370ff",
        phase="available",
        mcp_mode="gateway",
        category="office",
        guide_url="https://open.feishu.cn/document/mcp_open_tools/feishu-cli/set-up-lark-cli-for-ai-agents-in-openclaw_hermes.md",
        manual_url="https://open.feishu.cn/app",
<<<<<<< HEAD
        auth_hint="填写飞书应用 App ID 与 App Secret；文档搜索需再点「登录授权」",
=======
        auth_hint="Isi App ID dan App Secret aplikasi Feishu; pencarian dokumen perlu klik 'Otorisasi Masuk' lagi",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="wecom-cli",
        name="企业微信 CLI",
<<<<<<< HEAD
        description="通过官方 wecom-cli 操作文档、日程与消息（需主机安装 CLI）",
=======
        description="Kelola dokumen, jadwal, dan pesan via wecom-cli resmi (perlu CLI terpasang di host)",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="api_key",
        doc_url="https://github.com/WecomTeam/wecom-cli",
        icon="wecom-cli",
        color="#2f7bf6",
        phase="available",
        mcp_mode="gateway",
        category="office",
        guide_url="https://open.work.weixin.qq.com/help2/pc/21676",
        manual_url="https://open.work.weixin.qq.com/help2/pc/cat?doc_id=21677",
<<<<<<< HEAD
        auth_hint="填写长连接智能机器人 Bot ID 与 Secret；主机需已安装 @wecom/cli（wecom-cli）",
=======
        auth_hint="Isi Bot ID dan Secret robot pintar koneksi panjang; host harus sudah memasang @wecom/cli (wecom-cli)",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="agently-cli",
        name="Agent Mail",
<<<<<<< HEAD
        description="通过官方 Agent Mail CLI 使用独立 Agent 邮箱（需主机安装 CLI）",
=======
        description="Gunakan email Agent independen via Agent Mail CLI resmi (perlu CLI terpasang di host)",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="custom_fields",
        doc_url="https://github.com/Tencent/AgentlyMail",
        icon="agently-cli",
        color="#0052d9",
        phase="available",
        mcp_mode="gateway",
        category="office",
        guide_url="https://help.agent.qq.com/detail/0/1092",
        manual_url="https://agent.qq.com/",
<<<<<<< HEAD
        auth_hint="先保存连接器，再完成设备码授权；每个实例独立绑定邮箱",
=======
        auth_hint="Simpan konektor dulu, lalu selesaikan otorisasi kode perangkat; setiap instance mengikat email secara independen",
>>>>>>> 29e22aa (Oi v1.0.6)
    ),
    ConnectorCatalogEntry(
        kind="weknora",
        name="WeKnora",
<<<<<<< HEAD
        description="连接 WeKnora 私有知识库，提供只读检索与文档阅读",
=======
        description="Hubungkan basis pengetahuan privat WeKnora, sediakan pencarian baca-saja dan baca dokumen",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="custom_fields",
        doc_url="https://github.com/Tencent/WeKnora",
        icon="weknora",
        color="#0052d9",
        phase="available",
        mcp_mode="gateway",
        category="knowledge",
        guide_url="https://github.com/Tencent/WeKnora/blob/main/docs/api/README.md",
<<<<<<< HEAD
        auth_hint="填写 WeKnora 服务地址；API Key 与 Tenant ID 按部署的鉴权设置填写。",
        credential_fields=(
            ConnectorCredentialField(
                key="base_url",
                label="服务地址",
                field_type="url",
                placeholder="http://127.0.0.1:8080 或 https://weknora.example.com",
                help="未包含 /api/v1 时会自动补齐",
=======
        auth_hint="Isi alamat layanan WeKnora; API Key dan Tenant ID diisi sesuai pengaturan autentikasi deployment.",
        credential_fields=(
            ConnectorCredentialField(
                key="base_url",
                label="Alamat layanan",
                field_type="url",
                placeholder="http://127.0.0.1:8080 atau https://weknora.example.com",
                help="Otomatis dilengkapi jika belum mengandung /api/v1",
>>>>>>> 29e22aa (Oi v1.0.6)
            ),
            ConnectorCredentialField(
                key="api_key",
                label="API Key",
                field_type="password",
                required=False,
<<<<<<< HEAD
                placeholder="sk-...（无鉴权部署可留空）",
=======
                placeholder="sk-... (boleh kosong untuk deployment tanpa autentikasi)",
>>>>>>> 29e22aa (Oi v1.0.6)
                secret=True,
            ),
            ConnectorCredentialField(
                key="tenant_id",
                label="Tenant ID",
                required=False,
<<<<<<< HEAD
                help="平台级 API Key 需要指定工作空间时填写",
            ),
            ConnectorCredentialField(
                key="knowledge_base_ids",
                label="默认知识库 ID",
                field_type="tags",
                required=False,
                placeholder="kb-123, kb-456",
                help="留空时检索当前凭证可见的全部知识库",
=======
                help="Diisi saat API Key tingkat platform perlu menentukan ruang kerja",
            ),
            ConnectorCredentialField(
                key="knowledge_base_ids",
                label="ID basis pengetahuan default",
                field_type="tags",
                required=False,
                placeholder="kb-123, kb-456",
                help="Jika kosong, cari semua basis pengetahuan yang terlihat oleh kredensial saat ini",
>>>>>>> 29e22aa (Oi v1.0.6)
            ),
        ),
    ),
    ConnectorCatalogEntry(
        kind="dify",
        name="Dify",
<<<<<<< HEAD
        description="连接 Dify 已发布应用或工作流的 MCP 服务",
=======
        description="Hubungkan layanan MCP dari aplikasi atau alur kerja Dify yang sudah dipublikasi",
>>>>>>> 29e22aa (Oi v1.0.6)
        auth_kind="custom_fields",
        doc_url="https://docs.dify.ai/",
        icon="dify",
        color="#1c64f2",
        phase="available",
        mcp_mode="remote",
        category="self_hosted",
<<<<<<< HEAD
        auth_hint="在 Dify 应用的访问点中启用 MCP，然后粘贴完整的 MCP Server URL。",
=======
        auth_hint="Aktifkan MCP di titik akses aplikasi Dify, lalu tempel URL Server MCP yang lengkap.",
>>>>>>> 29e22aa (Oi v1.0.6)
        credential_fields=(
            ConnectorCredentialField(
                key="mcp_url",
                label="MCP Server URL",
                field_type="url",
                placeholder="https://dify.example.com/mcp/server/<server_code>/mcp",
<<<<<<< HEAD
                help="完整 URL 含访问标识，将按密钥加密保存",
=======
                help="URL lengkap berisi identitas akses, akan disimpan terenkripsi sebagai rahasia",
>>>>>>> 29e22aa (Oi v1.0.6)
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
