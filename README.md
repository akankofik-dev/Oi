# Oi

Asisten AI self-hosted yang lebih pintar — multi-user, multi-agent. Dashboard full Bahasa Indonesia.

## Install (satu perintah)

```bash
curl -sSL https://raw.githubusercontent.com/akankofik-dev/Oi/main/install-oi.sh | bash
```

Itu aja. Script-nya otomatis: install Python 3.12 → bikin venv → install semua dependency → jalanin server di `http://127.0.0.1:8088`.

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
oi run --host 127.0.0.1 --port 8088   # jalanin server
```

## Butuh bantuan?

Buka [Issues](https://github.com/akankofik-dev/Oi/issues).

## Lisensi

MIT — lihat [LICENSE](LICENSE).
