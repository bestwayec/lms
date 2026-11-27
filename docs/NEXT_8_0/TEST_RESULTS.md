# GRANDEC NEXT 8.0 — Test Execution Results

## 1. Backend Full Suite (SQLite — `config.settings.test`)
- **Command**: `pytest -q` (`task-7722`, executed after final code fixes)
- **Result**: **`2054 passed, 14 skipped, 272 subtests passed` (`0 failed`)** in `191.79s`.
- **Skipped tests breakdown**:
  - 13 PostgreSQL row-lock concurrency tests (`skipIf(vendor != "postgresql")`) — executed separately against real PostgreSQL 17.11 below.
  - 1 DejaVuSans Unicode PDF font test (`tests/test_smart_import_pro.py:64`).

## 2. Backend Real PostgreSQL 17.11 Suite (`config.settings.postgres_test`)
- **Command**: `pytest tests/test_next8_*.py tests/test_essay_async_grading.py tests/test_attendance_concurrency.py tests/test_homework_integrity.py tests/test_invitation_concurrency.py tests/test_subscription_usage_quota.py tests/test_telegram_security_evolution.py -q` (`task-7752`, against local PostgreSQL 17.11 `127.0.0.1:5432`)
- **Result**: **`162 passed, 0 failed, 0 skipped`** in `221.52s`.

## 3. Code Quality, Migrations & Django System Check
- **Ruff (`ruff check apps/ tests/`)**: `All checks passed!` (`ruff 0.16.7`, 0 errors).
- **Django Check (`manage.py check`)**: `System check identified no issues (0 silenced).`
- **Migration Check (`manage.py makemigrations --check --dry-run`)**: `No changes detected`.

## 4. Frontend Lint, Unit Tests, TypeScript & Build (`task-7722`)
- **Oxlint (`npm run lint`)**: `0 warnings and 0 errors` (`203 files`, `116 rules`).
- **Node Unit Suite (`npm test`)**: `34 passed, 0 failed` across 4 suites.
- **TypeScript + Vite Production Build (`tsc -b && vite build`)**: `3194 modules transformed`, built in `7.07s`.

## 5. Chromium Playwright Real-Backend E2E (`task-7751`)
- **Result**: `0 failed`, `console_errors: []`, `page_errors: []`, `http_5xx: []`.
- **Viewports x Themes (`360px`, `390px`, `768px`, `1024px`, `1366px`, `1920px` in Light & Dark)**: `12/12` checks passed with `horizontal_overflow: false`.
- **Interactive Flows Verified**: Real SPA login for Student, Teacher, and Admin; Reading Exam interface (`/english-exam/<attemptId>`), Writing Studio (`/essays/studio`), Vocabulary Studio (`/vocabulary`), Grammar Studio (`/grammar`), Speaking Topics (`/speaking`), Telegram Mini App (`/tma`), Teacher English Workspace (`/teacher/english`), and Admin Panel AI Metrics (`/panel`).
- **Visual Evidence**: 10 screenshots archived under `docs/NEXT_8_0/screenshots/`.
