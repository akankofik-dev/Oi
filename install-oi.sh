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
#   1. Install python3.12 + venv (Ubuntu/Debian)
#   2. Bikin venv ~/oi-venv
#   3. Install 4 sibling packages dari GitHub (oi-harness, oi-gateway, oi-memory, oi-browser)
#   4. Install oi 1.0.6 dari GitHub Releases
#   5. Jalanin oi init (kalau belum)
#   6. Jalanin oi run di 127.0.0.1:8088
#
set -euo pipefail

OI_VERSION="1.0.6"
OI_WHEEL_URL="https://github.com/akankofik-dev/Oi/releases/download/v${OI_VERSION}/oi-${OI_VERSION}-py3-none-any.whl"
VENV_DIR="$HOME/oi-venv"
OI_PORT="8088"

echo "=== [1/6] Install system deps ==="
sudo apt update -qq && sudo apt install -y -qq python3.12 python3.12-venv curl git > /dev/null 2>&1 || {
    echo "Gagal install system deps. Pastikan Ubuntu/Debian dan sudo tersedia."
    exit 1
}

echo "=== [2/6] Bikin venv ==="
if [ ! -d "$VENV_DIR" ]; then
    python3.12 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
pip install --upgrade pip

echo "=== [3/6] Install sibling packages ==="
# oi-memory, oi-gateway, oi-browser: tidak depend ke sibling, install normal
pip install "oi-memory @ git+https://github.com/akankofik-dev/oi-memory.git@v1.0.0"
pip install "oi-gateway @ git+https://github.com/akankofik-dev/oi-gateway.git@v1.0.0"
<<<<<<< HEAD
pip install "oi-browser @ git+https://github.com/akankofik-dev/oi-browser.git@v1.0.1"
=======
pip install "oi-browser @ git+https://github.com/akankofik-dev/oi-browser.git@v1.0.2"
>>>>>>> 29e22aa (Oi v1.0.6)
# oi-harness: depend ke oi-memory & oi-browser (ga ada di PyPI)
# Install --no-deps, lalu install deps PyPI-nya manual
pip install --no-deps "oi-harness @ git+https://github.com/akankofik-dev/oi-harness.git@v1.0.1"
echo "=== [3b/6] Install deps oi-harness dari PyPI ==="
pip install "deepagents>=0.7,<0.8" "httpx>=0.27" "langchain-anthropic>=1.5.4,<2.0" \
    "langchain-core>=1.5.0,<2.0" "langchain-mcp-adapters>=0.3.0" \
    "langchain-openai>=1.2.2,<2.0" "langchain>=1.3.14,<2.0" \
    "langgraph-checkpoint-sqlite>=2.0" "langgraph>=1.0,<2.0" \
    "markdownify>=0.13" "mcp>=1.27.1,<3" "pyyaml>=6.0" \
    "agent-client-protocol>=0.9.0" "cos-python-sdk-v5>=1.9" "psutil>=5.9" "wcmatch>=8.0"
# Note: [all] extra sebagian sudah di atas; deepagents-backends opsional, skip kalau gagal

echo "=== [4/6] Install oi $OI_VERSION ==="
pip install --force-reinstall "$OI_WHEEL_URL"

echo "=== [5/6] Init (skip kalau sudah ada) ==="
if [ ! -d "$HOME/.oi" ]; then
    oi init --yes --admin-username admin
else
    echo "~/.oi sudah ada, skip init."
fi

echo "=== [6/6] Jalanin server ==="
# Stop yang lama kalau ada — pakai PID file, bukan `pkill -f` yang berisiko
# membunuh proses lain yang kebetulan cocok polanya.
OI_PID_FILE="$HOME/.oi/run.pid"
if [ -f "$OI_PID_FILE" ]; then
    OLD_PID="$(cat "$OI_PID_FILE" 2>/dev/null || true)"
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        if ps -p "$OLD_PID" -o args= 2>/dev/null | grep -q "oi run"; then
            echo "Stop server lama (PID $OLD_PID)..."
            kill "$OLD_PID" 2>/dev/null || true
            sleep 2
            kill -9 "$OLD_PID" 2>/dev/null || true
        else
            echo "PID file basi (PID $OLD_PID bukan 'oi run'), lewati."
        fi
    fi
    rm -f "$OI_PID_FILE"
fi
nohup oi run --host 127.0.0.1 --port "$OI_PORT" > "$HOME/oi-server.log" 2>&1 &
echo $! > "$OI_PID_FILE"
sleep 5

if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$OI_PORT/" | grep -q "200\|302"; then
    echo ""
    echo "=== SELESAI! Oi jalan di http://127.0.0.1:$OI_PORT ==="
    echo ""
    echo "Buat akses dari HP, jalanin di terminal lain:"
    echo "  cloudflared tunnel --url http://127.0.0.1:$OI_PORT"
else
    echo "WARNING: Server mungkin belum jalan. Cek log: tail -50 $HOME/oi-server.log"
fi
