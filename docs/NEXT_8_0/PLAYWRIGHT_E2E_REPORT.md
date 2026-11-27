# GRANDEC NEXT 8.0 — Chromium Playwright E2E Verification Report

## Environment
- **Backend**: Live Django (`config.settings.e2e`, SQLite migrated cleanly across all 21 Django apps, seeded with Student, Teacher, and Admin fixtures).
- **Frontend**: Live Vite dev/preview proxy (`http://127.0.0.1:5173` -> `http://127.0.0.1:8000`).
- **Browser**: Headless Chromium via Python Playwright (`sync_playwright`).

## Role Flows & Authenticity
All accounts authenticated through the real React `/login` SPA form (`form.form` -> `POST /api/auth/login/` -> `200 OK`):

| Role | Route | Result | Measured Navigation + Settled Load (ms) |
| :--- | :--- | :--- | :--- |
| Student | `/english` | Rendered authenticated English Center | `2824.0` |
| Student | `/essays/studio` | Rendered Writing Studio 3.0 | `3921.4` |
| Student | `/speaking` | Rendered AI Speaking Simulator topics | `1461.3` |
| Student | `/vocabulary` | Rendered Flashcard Deck & Vocab Studio | `2388.0` |
| Student | `/grammar` | Rendered 10-topic Grammar Studio | `1880.2` |
| Student | `/tma` | Rendered Telegram Mini App Home & English card | `1644.5` |
| Teacher | `/teacher/english` | Rendered `"English Ustoz Ish Joyi"` | `3086.3` |
| Admin | `/panel` | Rendered `"Admin paneli"` + AI Gateway card | `2150.6` |

## Responsive Viewport & Theme Matrix (12 Checks on `/english`)
Tested across all 6 required widths in both **Light** and **Dark** modes:

| Width x Height | Light Theme Horizontal Overflow | Dark Theme Horizontal Overflow |
| :--- | :--- | :--- |
| `360 x 800` | `false` | `false` |
| `390 x 844` | `false` | `false` |
| `768 x 1024` | `false` | `false` |
| `1024 x 768` | `false` | `false` |
| `1366 x 768` | `false` | `false` |
| `1920 x 1080` | `false` | `false` |

## Runtime Error Telemetry
- **Browser `console.error` count**: `0`
- **Uncaught `pageerror` exceptions**: `0`
- **HTTP `5xx` server responses**: `0`
