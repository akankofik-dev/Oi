# Oi

Asisten AI self-hosted yang lebih pintar — multi-user, multi-agent. Dashboard full Bahasa Indonesia.

## Install

### Prerequisites

- Linux (Ubuntu/Debian)
- `git` dan `bash`
- Akses sudo untuk install dependensi sistem (Python, venv, `curl`, `git`) — skrip akan menginstall yang belum ada.

### 1. Install

```bash
git clone https://github.com/akankofik-dev/Oi.git
cd Oi
bash install-oi.sh
```

Skrip ini otomatis: install dependensi sistem → bikin venv di `~/oi-venv` → install semua dependency → inisialisasi → jalanin server.

Untuk akses dari luar (VPS), ganti baris terakhir jadi:

```bash
OI_HOST=0.0.0.0 bash install-oi.sh
```

### 2. Initialize

Inisialisasi dijalankan otomatis oleh `install-oi.sh` (dilewati kalau `~/.oi` sudah ada). Tidak ada langkah manual.

### 3. Run

Server dijalankan otomatis oleh `install-oi.sh` di `http://127.0.0.1:8088` (atau `http://0.0.0.0:8088` kalau `OI_HOST=0.0.0.0`). Untuk menjalankan lagi secara manual:

```bash
source ~/oi-venv/bin/activate
oi run --host 127.0.0.1 --port 8088  # jalanin server
```

## Akses dari Luar

Server default hanya listen di `127.0.0.1` (localhost). Untuk akses dari luar, gunakan tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8088
```

Buka URL trycloudflare yang muncul.

## Update

Klik **Cek Pembaruan** di dashboard (Pengaturan Aplikasi), atau manual:

```bash
source ~/oi-venv/bin/activate
pip install --force-reinstall --no-deps "https://github.com/akankofik-dev/Oi/releases/latest/download/oi-1.0.6-py3-none-any.whl"
```

Ganti `1.0.6` dengan versi terbaru dari [Releases](https://github.com/akankofik-dev/Oi/releases).

## Perintah dasar

```bash
source ~/oi-venv/bin/activate
oi run --host 127.0.0.1 --port 8088  # jalanin server
```

## Butuh bantuan?

Buka [Issues](https://github.com/akankofik-dev/Oi/issues).

## Lisensi

MIT — lihat [LICENSE](LICENSE).
