# Dashboard Oi — Source TypeScript

Source code dashboard web Oi (React 18 + TypeScript + Vite).

Struktur ini mengikuti pola Octop asli:
- `dashboard/` = **source** TypeScript (direktori ini)
- `src/oi/dashboard/` = **hasil build** (jangan edit langsung!)

## Prasyarat

- Node.js 18+ (`node --version`)
- npm 9+

## Instalasi

```bash
cd dashboard
npm ci
```

## Perintah

| Perintah              | Fungsi                                              |
|-----------------------|-----------------------------------------------------|
| `npm run build`       | Typecheck (`tsc -b`) + build production via Vite    |
| `npm run build:docker`| Build tanpa typecheck (lebih cepat)                 |
| `cd dashboard && npx tsc -b` | Typecheck saja                            |
| `npm run lint`        | ESLint                                                |
| `npm test`            | Vitest                                                |

## Build untuk Oi

Hasil build harus disalin ke `src/oi/dashboard/` (direktori build artifact
yang di-serve oleh backend FastAPI):

```bash
cd dashboard
DASHBOARD_OUTDIR=/path/to/oi-agent/src/oi/dashboard npm run build
```

Catatan: `vite.config.ts` mendukung env `DASHBOARD_OUTDIR` untuk override
output directory (default: `../src/octop/dashboard` peninggalan upstream).

## Bahasa

Dashboard memakai i18next. Bundle bahasa ada di `src/locales/`:
- `id.json` — Bahasa Indonesia (default)
- `en.json` — English (fallback)
- `zh.json` — Mandarin

Default locale diatur di `src/utils/localePrefs.ts` (`normalizeUiLocale`
return `"id"` bila tidak ada preferensi).

## Jangan

- Jangan edit `src/oi/dashboard/` langsung — itu build artifact.
- Jangan commit `node_modules/` atau `dist/`.
