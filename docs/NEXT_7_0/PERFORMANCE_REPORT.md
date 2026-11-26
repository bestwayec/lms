# GRANDEC NEXT 7.0 — Performance & Bundle Report

## 1. Frontend Production Bundle Metrics (`tsc -b && vite build`)

Measured on clean production build (`vite v8.3.8`, built in **`5.85s`**, `3187` modules transformed):

| Asset / Chunk | Raw Size | Gzip Size | Notes |
| :--- | :--- | :--- | :--- |
| `dist/index.html` | `5.38 kB` | `1.69 kB` | Includes inline early Light/Dark/System theme bootstrap (zero FOUC) |
| `dist/assets/index-CWb8ay6Q.css` | `239.87 kB` | `41.90 kB` | Core unified tokens, layouts & UI primitives (`styles/ui.css`) |
| `dist/assets/Tma-BElZQl1k.css` | `13.00 kB` | `3.17 kB` | Dedicated lazy-loaded TMA Light/Dark + Telegram ThemeParams stylesheet |
| `dist/assets/index-DcV1yrN3.js` | `308.31 kB` | `91.35 kB` | Main shell, router, auth/theme contexts & core HTTP client |
| `dist/assets/react-vendor-DmwtmMFm.js` | `291.78 kB` | `93.43 kB` | Shared React + React Router vendor chunk |
| `dist/assets/vendor-charts-CBwqmzkW.js` | `382.60 kB` | `108.66 kB` | Async chart vendor chunk (loaded only on analytics routes) |
| `dist/assets/Landing-Ce8s9BN5.js` | `107.29 kB` | `20.52 kB` | Route-split Landing bundle |
| `dist/assets/SmartTestCreate-BQkfHXuH.js` | `38.90 kB` | `11.26 kB` | Lazy-loaded Smart Test Builder |
| `dist/assets/Groups-B6wkaH8b.js` | `37.45 kB` | `9.50 kB` | Lazy-loaded Classroom/Groups manager |
| `dist/assets/PanelDashboard-rA4Svs8V.js` | `25.30 kB` | `5.67 kB` | Lazy-loaded Admin Dashboard |
| `dist/assets/PanelTests-BlOEUXYV.js` | `21.08 kB` | `5.80 kB` | Lazy-loaded Admin Tests Center |
| `dist/assets/PanelUsers-D5dFAyZO.js` | `12.83 kB` | `3.49 kB` | Lazy-loaded Admin Users table |
| `dist/assets/Tma-DgRJYxGF.js` | `21.47 kB` | `6.02 kB` | Lazy-loaded TMA entry + sub-tabs (`TestFlow`, `ProfileTab`, `TestsTab`) |
| `dist/assets/_virtual_i18n-en-C0jpoiZi.js` | `148.07 kB` | `49.00 kB` | On-demand English locale chunk |
| `dist/assets/_virtual_i18n-ru-JYhwtpii.js` | `218.67 kB` | `60.69 kB` | On-demand Russian locale chunk |

### Key Performance Safeguards Preserved & Added
- Lazy route splitting keeps Admin, Teacher (`Groups`, `SmartTestCreate`), Charting (`vendor-charts`), and Telegram Mini App (`Tma`) bundles decoupled from initial landing load.
- Non-Uzbek locales (`ru`, `en`) remain split into virtual on-demand chunks (`_virtual_i18n-*`).
- Duplicate-submit & in-flight locks (`saving`, `lifecycleBusyId`, `inflightInitData` keyed by current `initData` string) eliminate redundant API writes on rapid taps.
- `SmartTestCreate.tsx` drafts persist locally (`localStorage`) without unnecessary background draft-API churn, and `TestFlow.tsx` preserves answer selections in `sessionStorage` to recover from transient network drops without restarting attempts.
