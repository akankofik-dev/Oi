# Changelog Oi

## [1.0.6] — 2026-10-10

- Dashboard full Bahasa Indonesia (bebas Mandarin di UI)
- Browser default Google (hapus hardcoded Tencent Cloud URL)
- Fix deteksi versi (`importlib.metadata` baca paket `oi`)
- Installer satu perintah yang disederhanakan
- Update checker via GitHub Releases (prioritas), fallback PyPI dinonaktifkan untuk keamanan
- Remote Desktop: dependency `mss`/`pynput` diperbaiki
- Pin deterministik `boto3`/`botocore`/`aiobotocore` selaras (cegah pip resolver hang)
- `mss`/`pynput` dipindah ke dependensi inti
- `install-oi.sh`: pin `oi-browser` ke tag `@v1.0.1`; stop server via PID file (bukan `pkill -f`)
- oi-browser 1.0.1, `requires-python >=3.12`; perbaiki typo classifier Python 3.2 → 3.12

## [1.0.2] — 2026-10-09

- Rename distribusi `oi-agent` → `oi` (memperbaiki bug versi `vunknown`)
- `__version__` dibaca via `importlib.metadata`

## [1.0.5] — 2026-10-10

- Fix Tencent homepage di dashboard JS (ganti ke Google)

## [1.0.4] — 2026-10-10

- Tombol upgrade unduh wheel langsung dari GitHub Releases (bukan via pip/PyPI)

## [1.0.3] — 2026-10-10

- Update checker cek GitHub Releases dulu, fallback PyPI
