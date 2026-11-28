# GRANDEC NEXT 8.0 — Test Execution Results

## 1. Backend Full Suite (SQLite — `config.settings.test`)
- **Command**: `pytest -q` (`task-8495`, executed after final Python edits)
- **Result**: **`2058 passed, 14 skipped, 272 subtests passed` (`0 failed`)** in `192.60s`.
- **Skipped tests breakdown**:
  - 13 PostgreSQL row-lock concurrency tests (`skipIf(vendor != "postgresql")`) — executed separately against real PostgreSQL 17.11 below (`0` skipped).
  - 1 DejaVuSans Unicode PDF font test (`tests/test_smart_import_pro.py:64`).

## 2. Backend Real PostgreSQL 17.11 Suite (`config.settings.postgres_test`)
- **Command**: `pytest tests/test_next8_*.py tests/test_attendance_concurrency.py tests/test_essay_async_grading.py tests/test_homework_integrity.py tests/test_invitation_concurrency.py tests/test_stage3b_membership_history.py tests/test_subscription_usage_quota.py tests/test_teacher_telegram_assignment.py tests/test_telegram_attendance_journey.py tests/test_telegram_security_evolution.py tests/test_omr_speaking_gamification.py tests/test_english_exam_evidence_converter.py tests/test_teacher_studio.py tests/test_essay_studio.py -q -p no:cacheprovider` (`task-8519`, against local PostgreSQL 17.11 `127.0.0.1:5432`)
- **Result**: **`247 passed, 0 failed, 0 skipped`** in `229.37s`.

## 3. Code Quality, Migrations & Django System Check
- **Ruff (`ruff check .`)**: `All checks passed!` (`0` errors, `task-8538`).
- **Django Check (`manage.py check`)**: `System check identified no issues (0 silenced).` (`task-8495`, `task-8519`).
- **Migration Check (`manage.py makemigrations --check --dry-run`)**: `No changes detected` (`task-8495`, `task-8538`).

## 4. Frontend Lint, Unit Tests, TypeScript & Build (`task-8514`, after final `.tsx`/`.css` edit)
- **Oxlint (`npm run lint`)**: `0 warnings and 0 errors` (`203` files, `116` rules).
- **Node Unit Suite (`npm test`)**: `34 passed, 0 failed` across 4 suites.
- **TypeScript + Vite Production Build (`tsc -b && vite build`)**: `3194 modules transformed`, built in **`2.62s`**, zero errors.

## 5. Chromium Playwright Real-Backend E2E (`task-8528`, after final frontend + backend edits)
- **Result**: **`0` failed, `console_errors: []`, `page_errors: []`, `server_5xx: []`**.
- **Full 4-Skill Mock Journeys Verified**: **IELTS Academic**, **IELTS General Training**, and **CEFR Multilevel** end-to-end (`Student SPA login -> Listening -> Reading -> Writing -> Chromium fake-mic WebM/Opus Speaking capture & PyAV upload -> Submit -> Pending_Grading -> Logout draft key scrub -> Teacher Workspace Writing/Speaking review -> Auto-Finalization -> Gradebook parity -> Student Certificate Card`).
- **Studios Verified**: Writing Studio (`/essays/studio`) Draft Save & Reload restoration, Speaking Practice (`/speaking/practice/<id>`), Vocabulary Studio (`/vocabulary`), Grammar Studio (`/grammar`), Teacher Workspace (`/teacher/english`), Admin Panel (`/panel`), and TMA (`/tma`).
- **Viewports x Themes (`360px`, `390px`, `768px`, `1024px`, `1366px`, `1920px`)**: `overflows: []`, Admin Dark Mode `.admin-action` `rgb(22, 32, 51)` + `/english` `360px` search `12px` clear gap + Dark Mode button legibility confirmed via fresh screenshots (`docs/NEXT_8_0/screenshots/`).
