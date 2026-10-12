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
#   1. Install system dependencies (python3.12 + venv + curl + git, Ubuntu/Debian)
#   2. Bikin virtual environment ~/oi-venv
#   3. Install packages (oi-memory, oi-gateway, oi-browser, oi-harness + deps, oi)
#   4. Init Oi (skip kalau ~/.oi sudah ada)
#   5. Jalanin oi run di 127.0.0.1:8088
#
set -euo pipefail

OI_VERSION="1.0.6"
OI_WHEEL_URL="https://github.com/akankofik-dev/Oi/releases/download/v${OI_VERSION}/oi-${OI_VERSION}-py3-none-any.whl"
VENV_DIR="$HOME/oi-venv"
OI_PORT="8088"
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
# Install — logic sama persis seperti sebelumnya, hanya tampilan yang berubah.
# Output verbose (apt/pip) disembunyikan ke $OI_LOG, hanya status bersih tampil.
# ===========================================================================

: > "$OI_LOG"
_banner

# [1/5] System dependencies
_STEP_HINT="Pastikan Ubuntu/Debian dan sudo tersedia."
_step_begin "  " "Installing system dependencies"
_quiet sudo apt update -qq
_quiet sudo apt install -y -qq python3.12 python3.12-venv curl git
_step_end
_STEP_HINT=""

# [2/5] Virtual environment
_step_begin "  " "Creating virtual environment"
if [ ! -d "$VENV_DIR" ]; then
    _quiet python3.12 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
_quiet pip install --upgrade pip
_step_end

# [3/5] Packages — tiap package punya warna loading sendiri
printf '  %bInstalling packages%b\n' "$_C_DIM" "$_C_RESET" >&2
_pkg "oi-memory"      "$_C_MAUVE" "oi-memory @ git+https://github.com/akankofik-dev/oi-memory.git@v1.0.0"
_pkg "oi-gateway"     "$_C_TEAL"  "oi-gateway @ git+https://github.com/akankofik-dev/oi-gateway.git@v1.0.0"
_pkg "oi-browser"     "$_C_BLUE"  "oi-browser @ git+https://github.com/akankofik-dev/oi-browser.git@v1.0.2"
# oi-harness: depend ke oi-memory & oi-browser (ga ada di PyPI)
# Install --no-deps, lalu install deps PyPI-nya manual
_pkg "oi-harness"     "$_C_AMBER" --no-deps "oi-harness @ git+https://github.com/akankofik-dev/oi-harness.git@v1.0.1"
_pkg "oi-harness deps" "$_C_GREEN" \
    "deepagents>=0.7,<0.8" "httpx>=0.27" "langchain-anthropic>=1.5.4,<2.0" \
    "langchain-core>=1.5.0,<2.0" "langchain-mcp-adapters>=0.3.0" \
    "langchain-openai>=1.2.2,<2.0" "langchain>=1.3.14,<2.0" \
    "langgraph-checkpoint-sqlite>=2.0" "langgraph>=1.0,<2.0" \
    "markdownify>=0.13" "mcp>=1.27.1,<3" "pyyaml>=6.0" \
    "agent-client-protocol>=0.9.0" "cos-python-sdk-v5>=1.9" "psutil>=5.9" "wcmatch>=8.0"
# Note: [all] extra sebagian sudah di atas; deepagents-backends opsional, skip kalau gagal
_pkg "oi $OI_VERSION" "$_C_GREEN" --force-reinstall "$OI_WHEEL_URL"

# [4/5] Init (skip kalau sudah ada)
_step_begin "  " "Initializing Oi"
_skipped=""
if [ ! -d "$HOME/.oi" ]; then
    _quiet oi init --yes --admin-username admin
else
    _skipped=1
fi
_step_end
if [ -n "$_skipped" ]; then
    printf '    %b%s%b\n' "$_C_DIM" "~/.oi sudah ada, init dilewati." "$_C_RESET" >&2
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
# Fallback: matikan SEMUA proses 'oi run' yang masih jalan (mis. start manual tanpa PID file).
for _p in $(pgrep -f "oi run" 2>/dev/null || true); do
    if [ "$_p" != "$$" ]; then
        printf '  %b%s (PID %s)%s%b\n' "$_C_DIM" "Menghentikan proses oi run sisa" "$_p" "$_G_ELL" "$_C_RESET" >&2
        kill "$_p" 2>/dev/null || true
    fi
done
sleep 2
for _p in $(pgrep -f "oi run" 2>/dev/null || true); do
    if [ "$_p" != "$$" ]; then
        kill -9 "$_p" 2>/dev/null || true
    fi
done

_step_begin "  " "Starting server"
nohup oi run --host 127.0.0.1 --port "$OI_PORT" > "$HOME/oi-server.log" 2>&1 &
echo $! > "$OI_PID_FILE"
# Health check: coba 12x dengan interval 5 detik (total 60 detik).
# Server butuh waktu untuk startup, jangan lapor gagal terlalu cepat.
_HEALTH_OK=0
for _i in $(seq 1 12); do
    sleep 5
    if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$OI_PORT/" 2>/dev/null | grep -q "200\|302"; then
        _HEALTH_OK=1
        break
    fi
done

if [ "$_HEALTH_OK" = "1" ]; then
    _step_end
    printf '\n' >&2
    printf '  %b%s%b Oi berjalan di %bhttp://127.0.0.1:%s%b\n' "$_C_GREEN" "$_G_OK" "$_C_RESET" "$_C_BOLD" "$OI_PORT" "$_C_RESET" >&2
    printf '\n' >&2
    printf '  %bAkses luar localhost:%b\n' "$_C_DIM" "$_C_RESET" >&2
    printf '    cloudflared tunnel --url http://127.0.0.1:%s\n\n' "$OI_PORT" >&2
    printf '  %bLog install: %s%b\n' "$_C_DIM" "$OI_LOG" "$_C_RESET" >&2
else
    _step_fail
    printf '%bWARNING:%b Server mungkin belum jalan. Cek log: tail -50 %s/oi-server.log\n' "$_C_AMBER" "$_C_RESET" "$HOME" >&2
fi
