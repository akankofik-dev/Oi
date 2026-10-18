#!/usr/bin/env bash
#
# install-oi.sh — Install Oi di VPS baru, satu perintah langsung jalan.
#
# Cara pakai:
#   curl -sSL https://raw.githubusercontent.com/akankofik-dev/Oi/main/install-oi.sh | bash
#   atau:
#   bash install-oi.sh
#
# Yang dilakukan:
#   1. Install system dependencies (python3 + venv + curl + git, Ubuntu/Debian)
#   2. Bikin virtual environment ~/oi-venv
#   3. Install packages (oi-memory, oi-gateway, oi-browser, oi-harness + deps,
#      oi dari branch optimasi-chat via git — termasuk modul optimasi chat
#      dan dashboard fix; override dengan OI_SOURCE=wheel untuk release stabil)
#   4. Init Oi (skip kalau ~/.oi sudah ada)
#   5. Aktifkan flag optimasi chat (permanen, di ~/.oi/config.json)
#   6. Jalanin oi run di $OI_HOST:8088 (default 127.0.0.1; OI_HOST=0.0.0.0 untuk akses luar)
#
set -euo pipefail

OI_VERSION="1.0.6"
OI_WHEEL_URL="https://github.com/akankofik-dev/Oi/releases/download/v${OI_VERSION}/oi-${OI_VERSION}-py3-none-any.whl"
# SHA-256 wheel yang diharapkan (kosong = verifikasi dilewati).
# Isi dengan hash resmi release bila tersedia, mis. OI_WHEEL_SHA256="abc123...".
OI_WHEEL_SHA256="${OI_WHEEL_SHA256:-5e24191fbb2364a58726a3549e459d570becc520b8413fe279a0b7d3f433ee92}"
VENV_DIR="$HOME/oi-venv"
OI_PORT="8088"
# Bind address server. Default 127.0.0.1 (hanya localhost).
# Isi 0.0.0.0 supaya bisa diakses dari luar, mis:
#   curl -sSL https://raw.githubusercontent.com/akankofik-dev/Oi/main/install-oi.sh | OI_HOST=0.0.0.0 bash
OI_HOST="${OI_HOST:-127.0.0.1}"
OI_LOG="$HOME/oi-install.log"

# >>> DISPLAY ENGINE START >>>
# ===========================================================================
# Tampilan RACING — DISPLAY ONLY, tidak mengubah logic install.
# Step aktif menampilkan "comet bar" animasi yang menyapu bolak-balik
# dengan warna tiap package, sementara output verbose lari ke $OI_LOG.
# Animasi & warna mati otomatis kalau bukan TTY / NO_COLOR / TERM=dumb.
# ===========================================================================

_C_RESET=""; _C_BOLD=""; _C_DIM=""
_C_GREEN=""; _C_BLUE=""; _C_AMBER=""; _C_RED=""; _C_TEAL=""; _C_MAUVE=""
_CAN_TTY=0
_HAS_UTF8=0

if [ -t 2 ] && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then
    _CAN_TTY=1
    _C_RESET='\033[0m'
    _C_BOLD='\033[1m'
    _C_DIM='\033[2m'
    _C_GREEN='\033[38;5;108m'   # sage green
    _C_BLUE='\033[38;5;67m'     # steel blue
    _C_AMBER='\033[38;5;179m'   # muted amber
    _C_RED='\033[38;5;131m'     # terracotta
    _C_TEAL='\033[38;5;73m'     # muted teal
    _C_MAUVE='\033[38;5;139m'   # muted mauve
fi

case "$(locale charmap 2>/dev/null || echo ASCII)" in
    *[Uu][Tt][Ff]*8*|*UTF8*) _HAS_UTF8=1 ;;
esac

if [ "$_HAS_UTF8" = 1 ]; then
    _G_OK="✓"; _G_ACTIVE="●"; _G_FAIL="✗"; _G_ELL="…"
else
    _G_OK="[ok]"; _G_ACTIVE="*"; _G_FAIL="[fail]"; _G_ELL="..."
fi

_time_now() {
    if [ -n "${EPOCHREALTIME:-}" ]; then
        printf '%.0f' "$EPOCHREALTIME"
    else
        date +%s
    fi
}

# --- racing animation (display only) ---
# Step aktif: SATU BARIS "comet bar" menyapu bolak-balik (kepala terang + ekor
# redup) dengan warna package-nya sendiri + spinner braille.
# Update via \r (carriage return) saja — TANPA cursor-up multi-baris, sehingga
# aman di semua terminal (frame tidak akan numpuk).
# Jalan di background selama perintah asli dieksekusi diam-diam (output -> $OI_LOG).
# Loop berhenti graceful via flag file (bukan kill).
_ANIM_PID=""
_ANIM_FLAG=""

_anim_frame() {  # _anim_frame <indent> <label> <color> <spintext> <pos> <dir> <findex>
    # SATU BARIS SAJA: step + comet bar + spinner braille.
    # Update via \r (carriage return) — TIDAK pakai cursor-up multi-baris,
    # jadi aman di semua terminal termasuk yang tidak mendukung CUU
    # (frame tidak akan pernah numpuk).
    local indent="$1" label="$2" color="$3" spintext="$4" pos="$5" dir="$6" findex="$7"
    local width=18 i frame h1 h2 h3 trk sp
    if [ "$_HAS_UTF8" = 1 ]; then
        h1="█"; h2="▓"; h3="▒"; trk="░"
        case $((findex % 10)) in
            0) sp="⠋";; 1) sp="⠙";; 2) sp="⠹";; 3) sp="⠸";; 4) sp="⠼";;
            5) sp="⠴";; 6) sp="⠦";; 7) sp="⠧";; 8) sp="⠇";; *) sp="⠏";;
        esac
    else
        h1="#"; h2="+"; h3="="; trk="-"
        case $((findex % 4)) in
            0) sp="|";; 1) sp="/";; 2) sp="-";; *) sp="\\";;
        esac
    fi
    frame=""
    for ((i=0; i<width; i++)); do
        if   [ "$i" -eq "$pos" ]; then frame="${frame}${h1}"
        elif [ "$i" -eq "$((pos-dir))" ]; then frame="${frame}${h2}"
        elif [ "$i" -eq "$((pos-2*dir))" ]; then frame="${frame}${h3}"
        else frame="${frame}${trk}"; fi
    done
    # \r + clear-line lalu gambar ulang baris yang SAMA — tanpa \n, tanpa cursor-up.
    printf '\r\033[K%s%b%s%b %s  %b%s%b %b%s%b %b%s%b' \
        "$indent" "$color" "$_G_ACTIVE" "$_C_RESET" \
        "$label" "$color" "$frame" "$_C_RESET" \
        "$color" "$sp" "$_C_RESET" \
        "$_C_DIM" "$spintext" "$_C_RESET" >&2
}

_anim_loop() {  # _anim_loop <indent> <label> <color> <spintext> <flag> — jalan di background
    local indent="$1" label="$2" color="$3" spintext="$4" flag="$5"
    local width=18 pos=0 dir=1 findex=0
    while [ -f "$flag" ]; do
        _anim_frame "$indent" "$label" "$color" "$spintext" "$pos" "$dir" "$findex"
        sleep 0.08
        pos=$((pos+dir))
        if [ "$pos" -ge "$((width-1))" ]; then dir=-1; fi
        if [ "$pos" -le 0 ]; then dir=1; fi
        findex=$((findex+1))
    done
}

_anim_start() {  # pakai _S_INDENT _S_LABEL _S_COLOR _S_SPIN
    if [ "$_CAN_TTY" != 1 ]; then return 0; fi
    _anim_stop
    _ANIM_FLAG="${OI_LOG}.anim"
    : > "$_ANIM_FLAG"
    _anim_loop "$_S_INDENT" "$_S_LABEL" "$_S_COLOR" "$_S_SPIN" "$_ANIM_FLAG" &
    _ANIM_PID=$!
}

_anim_stop() {
    if [ -n "${_ANIM_PID:-}" ]; then
        rm -f "${_ANIM_FLAG:-${OI_LOG}.anim}" 2>/dev/null || true
        wait "$_ANIM_PID" 2>/dev/null || true
        _ANIM_PID=""; _ANIM_FLAG=""
    fi
    return 0
}
trap '_anim_stop' EXIT

_anim_clear() {  # hapus baris animasi aktif (SATU baris); kursor tetap di baris itu
    printf '\r\033[K' >&2
}

# --- step engine (display only) ---
_S_INDENT="  "; _S_LABEL=""; _S_T0=0; _S_COLOR=""; _S_SPIN=""
_STEP_HINT=""

_step_begin() {  # _step_begin <indent> <label> [active-color] [spinner-text]
    _S_INDENT="$1"; _S_LABEL="$2"; _S_COLOR="${3:-$_C_BLUE}"; _S_SPIN="${4:-Memasang${_G_ELL}}"
    _S_T0=$(_time_now)
    if [ "$_CAN_TTY" = 1 ]; then
        # frame pertama digambar sinkron (satu baris langsung ada),
        # lalu loop animasi menimpa baris yang sama via \r
        _anim_frame "$_S_INDENT" "$_S_LABEL" "$_S_COLOR" "$_S_SPIN" 0 1 0
        _anim_start
    fi
}

_step_end() {  # _step_end [done-color] — hentikan animasi, cetak baris final
    local color="${1:-$_C_GREEN}"
    local dt=$(( $(_time_now) - _S_T0 ))
    _anim_stop
    if [ "$_CAN_TTY" = 1 ]; then
        _anim_clear
    fi
    printf '%s%b%s%b %s %b(%ss)%b\n' "$_S_INDENT" "$color" "$_G_OK" "$_C_RESET" "$_S_LABEL" "$_C_DIM" "$dt" "$_C_RESET" >&2
    _S_LABEL=""
}

_step_fail() {  # _step_fail — hentikan animasi, gambar ulang baris sebagai gagal
    local dt=$(( $(_time_now) - _S_T0 ))
    _anim_stop
    if [ "$_CAN_TTY" = 1 ]; then
        _anim_clear
    fi
    printf '%s%b%s%b %s %b(%ss)%b\n' "$_S_INDENT" "$_C_RED" "$_G_FAIL" "$_C_RESET" "$_S_LABEL" "$_C_DIM" "$dt" "$_C_RESET" >&2
    _S_LABEL=""
}

# _quiet <cmd...> — jalan diam-diam ke log; gagal -> tampil ✗ + hint + tail log + exit
_quiet() {
    local rc=0
    "$@" >>"$OI_LOG" 2>&1 || rc=$?
    if [ "$rc" -eq 0 ]; then
        return 0
    fi
    _step_fail
    if [ -n "$_STEP_HINT" ]; then
        printf '%b%s%b\n' "$_C_AMBER" "$_STEP_HINT" "$_C_RESET" >&2
        _STEP_HINT=""
    fi
    printf '%bDetail error (tail %s):%b\n' "$_C_DIM" "$OI_LOG" "$_C_RESET" >&2
    tail -n 15 "$OI_LOG" >&2 || true
    exit "$rc"
}

# _pkg <name> <color> <pip-args...> — install satu package dengan warna sendiri
_pkg() {
    local name="$1" color="$2"; shift 2
    _STEP_HINT=""
    _step_begin "    " "$name" "$color"
    _quiet pip install "$@"
    _step_end "$color"
}

_banner() {
    local -a _logo _box
    if [ "$_HAS_UTF8" = 1 ]; then
        _logo=(
" ██████╗ ██╗"
"██╔═══██╗██║"
"██║   ██║██║"
"██║   ██║██║"
"╚██████╔╝██║"
" ╚═════╝ ╚═╝"
        )
        _box=(
"╭────────────────────────────────╮"
"│  Oi - Asisten AI self-hosted.  │"
"│  Multi-user & multi-agent,     │"
"│  berjalan penuh di server Anda.│"
"│  Chat, skill & otomatisasi AI. │"
"╰────────────────────────────────╯"
        )
    else
        _logo=(
"  ___  _"
" / _ \(_)"
"| | | |_"
"| | | | |"
"| |_| | |"
" \___/|_|"
        )
        _box=(
"+--------------------------------+"
"|  Oi - Asisten AI self-hosted.  |"
"|  Multi-user & multi-agent,     |"
"|  berjalan penuh di server Anda.|"
"|  Chat, skill & otomatisasi AI. |"
"+--------------------------------+"
        )
    fi
    local i
    for i in 0 1 2 3 4 5; do
        printf '%b%s%b  %b%s%b\n' \
            "$_C_BLUE$_C_BOLD" "${_logo[$i]}" "$_C_RESET" \
            "$_C_DIM" "${_box[$i]}" "$_C_RESET" >&2
    done
    printf '  %bOi Installer%b %bv%s%b\n\n' "$_C_BOLD" "$_C_RESET" "$_C_DIM" "$OI_VERSION" "$_C_RESET" >&2
}
# <<< DISPLAY ENGINE END <<<

# ===========================================================================
# FIX: false-positive health check — helper kill/start/health yang benar.
# Server yang dijalankan manual TANPA PID file tidak terbunuh oleh kill via
# PID file -> bind gagal ("address already in use") tapi health check tetap
# sukses karena server LAMA yang menjawab -> installer lapor "Oi berjalan"
# padahal versi baru tidak pernah start. Helper di bawah menutup lubang itu:
# pastikan port bebas SEBELUM start, dan health check hanya sukses bila PID
# yang baru di-start yang menjawab.
# ===========================================================================

_oi_port_busy() {  # _oi_port_busy <port> -> return 0 kalau port sedang di-listen
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -ltn 2>/dev/null | awk -v p="$port" '
            NR > 1 { n = split($4, a, ":"); if (a[n] == p) { found = 1; exit } }
            END { exit !found }'
    else
        # fallback kalau ss tidak ada: coba konek TCP (bash /dev/tcp)
        (exec 3<>"/dev/tcp/127.0.0.1/${port}") 2>/dev/null
    fi
}

_oi_ensure_port_free() {  # _oi_ensure_port_free <port> -> 0 kalau port bebas (dibunuh bila perlu)
    local port="$1" tries=0
    if ! _oi_port_busy "$port"; then
        return 0
    fi
    printf '  %bPort %s masih dipakai — menghentikan pemegang port%s%b\n' \
        "$_C_AMBER" "$port" "$_G_ELL" "$_C_RESET" >&2
    # fuser -k hanya membunuh pemegang port tsb (presisi, tanpa collateral);
    # pkill -f "oi run" hanya fallback kalau fuser tidak tersedia.
    if command -v fuser >/dev/null 2>&1; then
        fuser -k "${port}/tcp" >/dev/null 2>&1 || true
    else
        pkill -f "oi run" 2>/dev/null || true
    fi
    # Tunggu hingga port benar-benar bebas, maks ~10 detik.
    while _oi_port_busy "$port" && [ "$tries" -lt 20 ]; do
        sleep 0.5
        tries=$((tries + 1))
    done
    ! _oi_port_busy "$port"
}

_oi_health_ok() {  # _oi_health_ok <port> <pid> -> 0 hanya bila PID tsb hidup DAN endpoint sehat
    local port="$1" pid="$2" body code
    kill -0 "$pid" 2>/dev/null || return 1
    body="$(curl -s --max-time 3 "http://127.0.0.1:${port}/api/health" 2>/dev/null || true)"
    if printf '%s' "$body" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
        return 0
    fi
    # Fallback untuk build tanpa /api/health: root dashboard menjawab 200/302.
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 \
        "http://127.0.0.1:${port}/" 2>/dev/null || true)"
    [ "$code" = "200" ] || [ "$code" = "302" ]
}

# ===========================================================================
# Install — logic sama persis seperti sebelumnya, hanya tampilan yang berubah.
# Output verbose (apt/pip) disembunyikan ke $OI_LOG, hanya status bersih tampil.
# ===========================================================================

: > "$OI_LOG"
_banner

# [1/5] System dependencies — fleksibel: jalan di Ubuntu/Debian (apt),
# Termux (pkg), dengan/tanpa sudo, Python >= 3.12 apa pun yang tersedia.
# Prinsip: deteksi dulu, install hanya yang kurang, gagal dengan pesan jelas.
_STEP_HINT="Butuh OS berbasis apt (Ubuntu/Debian) atau pkg (Termux), dan Python >= 3.12."
_step_begin "  " "Installing system dependencies"

# --- sudo: pakai kalau ada; kalau tidak ada, jalan langsung (asumsi root,
# seperti di proot). Perilaku di sistem bersudo tidak berubah. ---
if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; else SUDO=""; fi

# --- Package manager: apt (Debian/Ubuntu) atau pkg (Termux). ---
if command -v apt-get >/dev/null 2>&1; then
    PKG_MGR="apt"
elif command -v pkg >/dev/null 2>&1; then
    PKG_MGR="pkg"
else
    _step_fail
    printf '%bGAGAL:%b Tidak ada apt (Debian/Ubuntu) atau pkg (Termux). OS tidak didukung.\n' "$_C_RED" "$_C_RESET" >&2
    exit 1
fi

# --- Python >= 3.12: cari yang sudah terpasang dulu. ---
# Urutan: versi eksplisit baru -> lama, lalu python3 generik (dicek versinya).
_oi_py_ok() {  # _oi_py_ok <bin> -> 0 bila Python >= 3.12
    "$1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" 2>/dev/null
}
OI_PYTHON=""
for _py in python3.14 python3.13 python3.12 python3; do
    if command -v "$_py" >/dev/null 2>&1 && _oi_py_ok "$_py"; then
        OI_PYTHON="$_py"
        break
    fi
done

# --- Kalau belum ada Python >= 3.12, coba install. ---
if [ -z "$OI_PYTHON" ]; then
    if [ "$PKG_MGR" = "pkg" ]; then
        # Termux: paket `python` selalu >= 3.12 (3.13+ saat ini).
        _quiet pkg install -y python git
        OI_PYTHON="python"
    else
        # apt: coba python3.12 dulu (Ubuntu 24.04), lalu python3.13 (25.10),
        # lalu python3 generik (distro default). Yang gagal dilewati, bukan
        # menggagalkan install — pengecekan versi di bawah yang memutuskan.
        _quiet $SUDO apt-get update -qq || true
        for _cand in python3.12 python3.13 python3; do
            if $SUDO apt-get install -y -qq "$_cand" "$_cand-venv" curl git >>"$OI_LOG" 2>&1; then
                if command -v "$_cand" >/dev/null 2>&1 && _oi_py_ok "$_cand"; then
                    OI_PYTHON="$_cand"
                    break
                fi
            fi
        done
    fi
fi

# --- Validasi akhir: harus ada Python >= 3.12, kalau tidak gagal jelas. ---
if [ -z "$OI_PYTHON" ] || ! _oi_py_ok "$OI_PYTHON"; then
    _step_fail
    printf '%bGAGAL:%b Python >= 3.12 tidak ditemukan.\n' "$_C_RED" "$_C_RESET" >&2
    printf '  Ubuntu 22.04 / Debian 12: install manual python3.12 (mis. PPA deadsnakes),\n' >&2
    printf '  lalu jalankan ulang installer.\n' >&2
    exit 1
fi

# --- Install paket pelengkap (curl, git, venv) sesuai package manager. ---
if [ "$PKG_MGR" = "pkg" ]; then
    # Termux: venv sudah termasuk di paket `python`; tidak ada paket -venv terpisah.
    # clang: compiler untuk package yang harus build dari source (mis. evdev di aarch64).
    _quiet pkg install -y curl git clang
else
    # apt: paket venv mengikuti nama binary python (python3.12-venv, dst).
    # Kalau binary-nya `python3` generik, paketnya `python3-venv`.
    # Build tools: beberapa dependensi (mis. evdev) tidak punya wheel pre-built
    # untuk aarch64 (HP/Raspberry Pi) dan harus compile dari source. Tanpa ini,
    # install di ARM gagal padahal di x86_64 (VPS) lancar karena ada wheel.
    _quiet $SUDO apt-get update -qq || true
    _quiet $SUDO apt-get install -y -qq "$OI_PYTHON-venv" "$OI_PYTHON-dev" build-essential linux-libc-dev curl git
fi
printf '  %bPython: %s%b\n' "$_C_DIM" "$OI_PYTHON" "$_C_RESET" >&2
_step_end
_STEP_HINT=""

# [2/5] Virtual environment
_step_begin "  " "Creating virtual environment"
if [ ! -d "$VENV_DIR" ]; then
    _quiet "$OI_PYTHON" -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
_quiet pip install --upgrade pip
_step_end

# [3/5] Packages — tiap package punya warna loading sendiri
printf '  %bInstalling packages%b\n' "$_C_DIM" "$_C_RESET" >&2
_pkg "oi-memory"      "$_C_MAUVE" "oi-memory @ git+https://github.com/akankofik-dev/oi-memory.git@v1.0.0"
_pkg "oi-gateway"     "$_C_TEAL"  "oi-gateway @ git+https://github.com/akankofik-dev/oi-gateway.git@v1.0.0"
_pkg "oi-browser"     "$_C_BLUE"  --force-reinstall "oi-browser @ git+https://github.com/akankofik-dev/oi-browser.git@v1.0.2"
# oi-harness: depend ke oi-memory & oi-browser (ga ada di PyPI)
# Install --no-deps, lalu install deps PyPI-nya manual
_pkg "oi-harness"     "$_C_AMBER" --no-deps "oi-harness @ git+https://github.com/akankofik-dev/oi-harness.git@v1.0.7"
_pkg "oi-harness deps" "$_C_GREEN" \
    "deepagents>=0.7,<0.8" "httpx>=0.27" "langchain-anthropic>=1.5.4,<2.0" \
    "langchain-core>=1.5.0,<2.0" "langchain-mcp-adapters>=0.3.0" \
    "langchain-openai>=1.2.2,<2.0" "langchain>=1.3.14,<2.0" \
    "langgraph-checkpoint-sqlite>=2.0" "langgraph>=1.0,<2.0" \
    "markdownify>=0.13" "mcp>=1.27.1,<2" "pyyaml>=6.0" \
    "pydantic>=2.6,<2.14" "tenacity>=8.2.3,<9.2.0" "websockets>=13.0,<16" \
    "agent-client-protocol>=0.9.0" "cos-python-sdk-v5>=1.9" "psutil>=5.9" "wcmatch>=8.0"
# Note: [all] extra sebagian sudah di atas; deepagents-backends opsional, skip kalau gagal
# oi: install dari source Git (branch main, sudah termasuk optimasi chat +
# dashboard fix). Bisa dioverride:
#   OI_SOURCE=wheel  -> pakai release wheel 1.0.6 stabil (perilaku lama)
#   OI_BRANCH=<nama> -> pakai branch lain
OI_SOURCE="${OI_SOURCE:-git}"
OI_BRANCH="${OI_BRANCH:-main}"
if [ "$OI_SOURCE" = "wheel" ]; then
    _step_begin "    " "oi $OI_VERSION (wheel)" "$_C_GREEN"
    OI_WHEEL_FILE="${TMPDIR:-/tmp}/oi-${OI_VERSION}-py3-none-any.whl"
    _STEP_HINT="Gagal mengunduh wheel Oi dari GitHub release."
    _quiet curl -sSL -o "$OI_WHEEL_FILE" "$OI_WHEEL_URL"
    _STEP_HINT=""
    if [ -n "$OI_WHEEL_SHA256" ]; then
        _STEP_HINT="SHA-256 wheel tidak cocok — file unduhan mungkin korup atau diganti. Install DIBATALKAN."
        _quiet bash -c 'printf "%s  %s\n" "$0" "$1" | sha256sum -c - >/dev/null' "$OI_WHEEL_SHA256" "$OI_WHEEL_FILE"
        _STEP_HINT=""
    fi
    _STEP_HINT=""
    _quiet pip install --force-reinstall "$OI_WHEEL_FILE"
    rm -f "$OI_WHEEL_FILE"
    _step_end "$_C_GREEN"
else
    _STEP_HINT="Gagal install oi dari GitHub branch $OI_BRANCH."
    _pkg "oi ($OI_BRANCH)" "$_C_GREEN" --force-reinstall "oi @ git+https://github.com/akankofik-dev/Oi.git@$OI_BRANCH"
    _STEP_HINT=""
fi

# [3b/5] Pulihkan Snap Chromium kalau /tmp/snap-private-tmp basi (recovery saja).
# Direktori /tmp/snap-private-tmp yang basi membuat Chromium dari Snap gagal start
# ("unexpected ownership / permissions", returncode=1). chown/chmod TERBUKTI tidak
# mempan di VPS - yang mempan: hapus direktori basi + restart snapd, lalu Snap
# membuatnya ulang dengan benar. Hanya jalan bila snapd dan snap chromium ada,
# direktori basi ada, DAN `chromium --version` gagal; selain itu tidak disentuh.
# Idempoten dan tidak menggagalkan installer.
if command -v snap >/dev/null 2>&1 \
    && snap list 2>/dev/null | grep -q '^chromium[[:space:]]' \
    && [ -d /tmp/snap-private-tmp ]; then
    _chromium_bin="$(command -v chromium 2>/dev/null || command -v chromium-browser 2>/dev/null || echo /snap/bin/chromium)"
    if ! "$_chromium_bin" --version >/dev/null 2>&1; then
        _snap_fix_sudo=""
        if [ "$(id -u)" -ne 0 ]; then _snap_fix_sudo="sudo"; fi
        printf ' %b%s%b /tmp/snap-private-tmp basi - memulihkan Snap Chromium%s\n' \
            "$_C_AMBER" "$_G_ACTIVE" "$_C_RESET" "$_G_ELL" >&2
        $_snap_fix_sudo rm -rf /tmp/snap-private-tmp || true
        if command -v systemctl >/dev/null 2>&1; then
            $_snap_fix_sudo systemctl restart snapd >>"$OI_LOG" 2>&1 || true
            sleep 3
        fi
        if "$_chromium_bin" --version >/dev/null 2>&1; then
            printf ' %b%s%b Snap Chromium pulih.\n' "$_C_GREEN" "$_G_OK" "$_C_RESET" >&2
        else
            printf ' %b%s%b Chromium masih gagal start - browser Oi mungkin tidak jalan.\n' \
                "$_C_AMBER" "$_G_FAIL" "$_C_RESET" >&2
            printf ' %bCek manual: /snap/bin/chromium --version%b\n' "$_C_DIM" "$_C_RESET" >&2
        fi
    fi
fi

# [4/5] Init (skip kalau sudah ada)
_step_begin "  " "Initializing Oi"
_skipped=""
if [ ! -d "$HOME/.oi" ]; then
    # Default Oi: JANGAN bikin admin user di sini. Setup wizard di web UI
    # yang bikin admin saat pertama buka dashboard. Kalau ~/.oi sudah ada
    # (udah pernah setup), wizard otomatis dilewati -> langsung login.
    _quiet oi init --yes --skip-admin
else
    _skipped=1
fi
_step_end
if [ -n "$_skipped" ]; then
    printf '    %b%s%b\n' "$_C_DIM" "~/.oi sudah ada, init dilewati." "$_C_RESET" >&2
fi

# [4b/5] Aktifkan flag optimasi chat secara permanen di ~/.oi/config.json.
# Ditulis via python agar JSON tidak rusak. Idempoten: aman dijalankan ulang.
_step_begin "  " "Mengaktifkan optimasi chat"
if [ -f "$HOME/.oi/config.json" ]; then
    if "$VENV_DIR/bin/python" - << 'PYEOF' >>"$OI_LOG" 2>&1; then
import json, os
p = os.path.expanduser("~/.oi/config.json")
with open(p) as f:
    cfg = json.load(f)
cfg["chat"] = {
    "batch_db_writes": True,
    "async_history": True,
    "mmap_history": True,
    "provider_prewarm": True,
    "smart_context_switch": True,
    "semantic_compress": True,
    "auto_router": True,
    "auto_router_mode": "suggest",
}
with open(p, "w") as f:
    json.dump(cfg, f, indent=2)
print("chat flags written")
PYEOF
        _step_end
    else
        _step_fail
        printf '%bGAGAL:%b Tidak bisa menulis flag optimasi ke ~/.oi/config.json. Cek %s\n' "$_C_RED" "$_C_RESET" "$OI_LOG" >&2
        exit 1
    fi
else
    _step_fail
    printf '%bGAGAL:%b ~/.oi/config.json tidak ditemukan setelah init.\n' "$_C_RED" "$_C_RESET" >&2
    exit 1
fi

# [5/5] Server — bereskan server lama dulu (info redup), baru start yang baru.
# Stop pakai PID file, bukan `pkill -f` yang berisiko membunuh proses lain.
OI_PID_FILE="$HOME/.oi/run.pid"
if [ -f "$OI_PID_FILE" ]; then
    OLD_PID="$(cat "$OI_PID_FILE" 2>/dev/null || true)"
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        if ps -p "$OLD_PID" -o args= 2>/dev/null | grep -q "oi run"; then
            printf '  %b%s (PID %s)%s%b\n' "$_C_DIM" "Menghentikan server lama" "$OLD_PID" "$_G_ELL" "$_C_RESET" >&2
            kill "$OLD_PID" 2>/dev/null || true
            sleep 2
            kill -9 "$OLD_PID" 2>/dev/null || true
        else
            printf '  %b%s%b\n' "$_C_DIM" "PID file basi (bukan 'oi run'), lewati." "$_C_RESET" >&2
        fi
    fi
    rm -f "$OI_PID_FILE"
fi

_step_begin "  " "Starting server"

# Port HARUS bebas dulu: server manual tanpa PID file tidak terjangkau kill
# via PID file di atas — kalau port masih dipakai, start baru gagal bind
# ("address already in use") dan health check lama akan sukses PALSU.
# Kalau di-bind ke 0.0.0.0, buka port di firewall (ufw) supaya bisa diakses dari luar.
# Best-effort: gagal buka firewall tidak menggagalkan install.
if [ "$OI_HOST" = "0.0.0.0" ] && command -v ufw >/dev/null 2>&1; then
    if ufw status 2>/dev/null | grep -q "Status: active"; then
        printf '  %bMembuka port %s di firewall (ufw)%s%b\n' "$_C_DIM" "$OI_PORT" "$_G_ELL" "$_C_RESET" >&2
        ufw allow "$OI_PORT"/tcp >>"$OI_LOG" 2>&1 || \
            printf '  %bGagal buka firewall otomatis — buka manual: ufw allow %s/tcp%b\n' "$_C_AMBER" "$OI_PORT" "$_C_RESET" >&2
    fi
fi

if ! _oi_ensure_port_free "$OI_PORT"; then
    _step_fail
    printf '%bGAGAL:%b Port %s masih dipakai setelah 10 detik — server lama tidak bisa dihentikan.\n' \
        "$_C_RED" "$_C_RESET" "$OI_PORT" >&2
    printf 'Versi baru TIDAK di-start. Bunuh manual pemegang port lalu jalankan ulang installer:\n' >&2
    printf '  ss -ltnp | grep ":%s "\n' "$OI_PORT" >&2
    printf '  fuser -k %s/tcp   # atau: pkill -f "oi run"\n' "$OI_PORT" >&2
    exit 1
fi

nohup oi run --host "$OI_HOST" --port "$OI_PORT" > "$HOME/oi-server.log" 2>&1 &
OI_SERVER_PID=$!
echo "$OI_SERVER_PID" > "$OI_PID_FILE"

# Health check: retry tiap 2 detik, maks ~30 detik, ke /api/health.
# Sukses HANYA jika PID yang baru di-start masih hidup saat endpoint menjawab
# ok:true — ini menutup false-positive "server lama yang menjawab".
_healthy=0
_tries=0
while [ "$_tries" -lt 15 ]; do
    if _oi_health_ok "$OI_PORT" "$OI_SERVER_PID"; then
        _healthy=1
        break
    fi
    if ! kill -0 "$OI_SERVER_PID" 2>/dev/null; then
        break  # proses baru sudah mati (mis. gagal bind) — jangan tunggu sia-sia
    fi
    sleep 2
    _tries=$((_tries + 1))
done

if [ "$_healthy" = 1 ]; then
    _step_end
    printf '\n' >&2
    if [ "$OI_HOST" = "0.0.0.0" ]; then
        _PUBIP="$(curl -s --max-time 5 ifconfig.me 2>/dev/null || true)"
        if [ -n "$_PUBIP" ]; then
            printf '  %b%s%b Oi berjalan dan bisa diakses dari luar:\n' "$_C_GREEN" "$_G_OK" "$_C_RESET" >&2
            printf '    %bhttp://%s:%s%b\n\n' "$_C_BOLD" "$_PUBIP" "$OI_PORT" "$_C_RESET" >&2
        else
            printf '  %b%s%b Oi berjalan di semua interface, port %s.\n' "$_C_GREEN" "$_G_OK" "$_C_RESET" "$OI_PORT" >&2
            printf '    Akses via http://IP-VPS:%s\n\n' "$OI_PORT" >&2
        fi
        printf '  %bCatatan:%b halaman login sekarang terbuka ke internet.\n' "$_C_AMBER" "$_C_RESET" >&2
        printf '  %bBuka dashboard dan ikuti setup wizard untuk membuat akun admin.%b\n\n' "$_C_DIM" "$_C_RESET" >&2
    else
        printf '  %b%s%b Oi berjalan di %bhttp://127.0.0.1:%s%b\n' "$_C_GREEN" "$_G_OK" "$_C_RESET" "$_C_BOLD" "$OI_PORT" "$_C_RESET" >&2
        printf '\n' >&2
        printf '  %bMau diakses dari luar? Jalankan ulang dengan:%b\n' "$_C_DIM" "$_C_RESET" >&2
        printf '    curl -sSL https://raw.githubusercontent.com/akankofik-dev/Oi/main/install-oi.sh | OI_HOST=0.0.0.0 bash\n\n' >&2
    fi
    printf '  %bOptimasi chat: AKTIF (7 flag, permanen di ~/.oi/config.json)%b\n' "$_C_GREEN" "$_C_RESET" >&2
    printf '  %bLog install: %s%b\n' "$_C_DIM" "$OI_LOG" "$_C_RESET" >&2
else
    _step_fail
    printf '%bGAGAL:%b Server Oi tidak sehat setelah 30 detik (PID %s).\n' \
        "$_C_RED" "$_C_RESET" "$OI_SERVER_PID" >&2
    printf 'Versi baru TIDAK berjalan — JANGAN anggap install berhasil.\n' >&2
    printf 'Cek log server (tail):\n' >&2
    tail -n 20 "$HOME/oi-server.log" >&2 || true
    exit 1
fi
