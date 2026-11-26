# GRANDEC NEXT 7.0 — Repository Audit & Baseline

- **Date:** 2026-11-26
- **Branch:** `feat/grandec-next-7-0-platform-refinement`
- **Base Commit:** `e0447e16956404192a30fde6c6de9ba16c3ef07c` (`main`, `v2.11.0`, integrating PRs #134–#150)
- **Production Deployment Reference:** `https://grandec.uz` (`v2.11.0`, image `ghcr.io/bestwayec/lms:sha-e0447e1`)
- **Screenshot Note:** The user prompt references supplied screenshots that were not attached inside this conversation payload; every listed defect was verified directly against the repository source code and reproduced locally via backend/browser test harnesses.

---

## 1. Architecture Inventory

### Backend (`Django 5.2` + `DRF` + `SimpleJWT` + `Channels` + `Celery 5.6.3`)
- **Apps:** `accounts`, `arena`, `attendance`, `billing`, `bot`, `certificates`, `core`, `courses`, `essays`, `games`, `groups`, `notifications`, `organizations`, `panel`, `payments`, `results`, `speaking`, `subscriptions`, `telegram_app`, `tests`, `tuition`, `vocabulary`, `web`, `webapi`, `weekly_reports`.
- **Auth & Sessions (`config/settings/base.py`, `apps/accounts/`):**
  - DRF `DEFAULT_AUTHENTICATION_CLASSES = [JWTAuthentication, SessionAuthentication]`.
  - SimpleJWT `ACCESS_TOKEN_LIFETIME = 60m`, `REFRESH_TOKEN_LIFETIME = 7d`, `ROTATE_REFRESH_TOKENS = True`, `BLACKLIST_AFTER_ROTATION = True`.
  - Session endpoints (`SessionLoginView`, `RegisterView`, `PasswordReset*`, `TelegramWidgetAuthView`) explicitly clear `authentication_classes = []`, whereas `tma_auth_view` (`apps/telegram_app/views.py`) only applies `@csrf_exempt` and leaves `SessionAuthentication` active while calling `login(request, user)` without `get_token(request)`.
- **URL Routing (`config/urls.py` & `deploy/nginx/nginx-ssl.conf`):**
  - Production Nginx routes `/api/`, `/essays/api/`, `/arena/api/`, `/subscribe/api/`, `/tma/api/`, `/healthz/`, `/ws/`, `/static/`, `/media/` to Django and falls back everything else to React SPA `/app/spa/index.html`.
  - Django `config/urls.py` ends with `path("<path:resource>", serve_spa_shell, name="spa-shell-deep")`, which has NO negative lookahead guarding `/api/`, `/tma/api/`, `/essays/api/`, etc. Any unmatched API path returns HTTP `200 OK` `text/html` (`index.html`).

### Frontend (`React` + `TypeScript` + `Vite 8` + `Tailwind` + `lucide-react`)
- **API Clients:**
  - `frontend/src/lib/api.ts`: Centralized `api<T>()` + `sessionApi<T>()` + `uploadApi<T>()`. `api<T>()` returns `(await res.json()) as T` on `res.ok` without verifying `Content-Type` is JSON (`application/json`), causing `Unexpected token '<', "<!doctype "... is not valid JSON` whenever HTML is returned. No mutation idempotency-key support or request correlation ID logging.
  - `frontend/src/pages/tma/api.ts`: Wraps `api()` for `/tma/api/*` and `/api/classroom/*`.
  - `frontend/src/lib/essays-arena.ts` & `frontend/src/utils/offlineExam.ts`: Raw `fetch()` wrappers outside `api<T>()`.
- **Theme & Styling (`frontend/index.html`, `frontend/src/index.css`, `frontend/src/theme/ThemeContext.tsx`, `frontend/src/pages/tma/Tma.css`):**
  - Duplicate CSS variable definitions inside `frontend/src/index.css` (lines 6–123 vs 284–320), plus legacy hardcoded `#f8fafc`, `#ffffff`, `#fff1f2`, `#f0f9ff`, `#1c1c1c` rules across `PanelTests.tsx`, `PanelUsers.tsx`, `SmartTestCreate.tsx`, `StudentGroupDetail.tsx`, `TestDetail.tsx`, and `index.css`.
  - `ThemeContext.tsx` ignores `system` preference (`theme === 'dark' ? 'dark' : 'light'`) and `index.html` + `ThemeContext.tsx` delete legacy `localStorage.getItem('theme') === 'dark'`.
  - `Tma.css` & `Tma.tsx` hardcode Light Mode colors (`#FFFFFF`, `#F8FAFC`, `#0F172A`) regardless of Telegram `colorScheme` or GRANDEC theme.
- **Workspaces & Navigation (`Layout.tsx`, `Navbar.tsx`, `SubjectSwitcher.tsx`, `BottomNav.tsx`, `SEO.tsx`):**
  - `Navbar.tsx` and `Layout.tsx` render `<SubjectSwitcher />` (and student `PlanBadge` / `PRO` pill / student links) for Global Admin (`isAdmin`) and Teachers.
  - Only 8 pages use `<SEO>`, so navigating from `/login` to `/panel`, `/dashboard`, `/groups`, `/tests/create`, `/teacher`, etc. leaves `document.title` stuck on `"Tizimga kirish | GRANDEC 2.0"`.
  - Desktop sidebar lacks a collapsible mode; mobile top bar lacks a direct navigation drawer button; `Groups.tsx` cards cram badges and buttons on single flex rows causing horizontal wrap/overflow.
- **Telegram Bot (`apps/notifications/bot/handlers.py`):**
  - Role dispatchers (`_admin_main_menu_keyboard`, `_teacher_main_menu_keyboard`, `_student_main_menu_keyboard`) work, but Admin menu is missing Users/Teachers/Centers/Groups/Tests/Notifications/TMA actions, Teacher menu omits Gradebook/Test assignment/Group Telegram connect shortcuts and links `Web kabinet` to `/login` instead of `/teacher`, and callback queries / `edit_or_reply` need systematic audit for idempotency & stale-button recovery.

---

## 2. Baseline Verification Results (Pre-Edit, `main @ e0447e1`)

| Check | Command | Result | Notes |
| :--- | :--- | :--- | :--- |
| Backend Lint | `ruff check .` | **PASS** | 0 errors |
| Django System Check | `DJANGO_SETTINGS_MODULE=config.settings.test SECRET_KEY=test-secret-key python manage.py check` | **PASS** | 0 issues |
| Django Migrations Check | `python manage.py makemigrations --check --dry-run` | **PASS** | No pending migrations |
| Frontend Lint | `npm --prefix frontend run lint` | **PASS** | 0 warnings, 0 errors (`oxlint`, 193 files) |
| Frontend Unit Tests | `npm --prefix frontend test` | **PASS** | 28/28 passed (4 suites, `node --test`) |
| Frontend Production Build | `npm --prefix frontend run build` | **PASS** | `tsc -b && vite build` succeeded in 5.28s |
| Backend Test Suite (SQLite) | `DJANGO_SETTINGS_MODULE=config.settings.test SECRET_KEY=test-secret-key pytest -q` | **2011 passed, 4 failed, 14 skipped** (220.67s) | 13 skipped require PostgreSQL row/advisory locks; 1 skipped requires `DejaVuSans` font; 4 failed ONLY on Windows NTFS `os.stat(path).st_mode & 0o777 == 0o600` (returns `0o666` on Windows, green on Linux CI). |
