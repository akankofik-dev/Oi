# Oi

> Oi based on Octop — Oi adalah rebrand dari [TencentCloud/Octop](https://github.com/TencentCloud/Octop), dengan struktur yang diselaraskan dengan upstream.

Asisten AI self-hosted yang lebih pintar — multi-user, multi-agent. Dashboard full Bahasa Indonesia.

## Install

```bash
git clone https://github.com/akankofik-dev/Oi.git
cd Oi
bash install-oi.sh
```

Itu aja. Script-nya otomatis: install Python 3.12+ → bikin venv → install semua dependency → jalanin server di `http://127.0.0.1:8088`.

Kenapa `git clone` (bukan `curl | bash`)? Biar jalan di semua mesin — nggak butuh `curl`, dan selalu narik kode terbaru (nggak kena cache CDN).

Untuk akses dari luar (VPS), ganti baris terakhir jadi:

```bash
OI_HOST=0.0.0.0 bash install-oi.sh
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
oi run --host 127.0.0.1 --port 8088   # jalanin server
```

## Butuh bantuan?

Buka [Issues](https://github.com/akankofik-dev/Oi/issues).

## Lisensi

MIT — lihat [LICENSE](LICENSE).
