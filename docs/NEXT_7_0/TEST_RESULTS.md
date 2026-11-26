# GRANDEC NEXT 7.0 — Verification & Test Results

All checks below were executed cleanly **after** the final code commit (`ed8fb65`) on branch `feat/grandec-next-7-0-platform-refinement`.

---

## 1. Backend Quality, Integrity & Pytest Suite

```powershell
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
$env:DJANGO_SETTINGS_MODULE='config.settings.test'; $env:SECRET_KEY='test-secret-key'; pytest -q
```

| Check | Outcome | Observed Metrics |
| :--- | :--- | :--- |
| `ruff check .` | PASS | `All checks passed!` (`0` warnings/errors) |
| `python manage.py check` | PASS | `System check identified no issues (0 silenced).` |
| `makemigrations --check --dry-run` | PASS | `No changes detected` |
| `pytest -q` (SQLite test settings) | PASS | **`2026 passed, 14 skipped, 272 subtests passed`** in `210.73s` (`0 failed`) |

### Skipped Tests Breakdown (14 total — Environment-Gated Only)
- **13 PostgreSQL Concurrency / Row-Lock / Advisory-Lock Tests:** Skipped automatically when executed with SQLite (`config.settings.test`); these run on PostgreSQL CI (`config.settings.postgres_test`) across `test_attendance_concurrency.py`, `test_essay_async_grading.py`, `test_homework_integrity.py`, `test_invitation_concurrency.py`, `test_stage3b_membership_history.py`, `test_subscription_usage_quota.py`, `test_teacher_telegram_assignment.py`, `test_telegram_attendance_journey.py`, and `test_telegram_security_evolution.py`.
- **1 Font Dependency Test:** `tests/test_smart_import_pro.py:64` skipped (`needs DejaVuSans for a Unicode text PDF`).

---

## 2. Frontend Static Analysis, Unit Suite & Production Build

```powershell
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
```

| Check | Outcome | Observed Metrics |
| :--- | :--- | :--- |
| `oxlint src` | PASS | **`0 warnings and 0 errors`** (196 files, 116 rules in `3.5s`) |
| `node --test tests/*.test.ts` | PASS | **`34 passed, 0 failed`** across 4 test suites (`1249.85ms`) |
| `tsc -b && vite build` | PASS | **`✓ built in 5.85s`**, zero TypeScript or bundler errors |

---

## 3. Real-Django + Chromium Playwright E2E Verification

Executed against compiled `frontend/dist/` served single-origin alongside live Django WSGI + ephemeral SQLite DB across `desktop_1920`, `desktop_1366`, `laptop_1024`, `tablet_768`, `mobile_390`, and `mobile_360`.

- **Result:** **`E2E Passed: 39, Failed: 0, ConsoleErrors: 0`**
- **Verified Flows & Assertions:**
  - Landing Light & Dark horizontal overflow check (`scrollWidth == innerWidth`) on `360px`, `390px`, `768px`, `1024px`, `1366px`, `1920px`.
  - Admin Login, `/panel` document `<title>` sync, absence of student `SubjectSwitcher` (`.tb-subject`, `.seg`), dark-mode Audience Audit modal backdrop (`bg != rgb(255, 255, 255)`), `/panel/tests` & `/panel/users` layout.
  - Teacher `/groups` & `/tests/create` multi-viewport overflow checks (`360–1920px`), `SmartTestCreate` mobile `Editor`/`Preview` tabs visible at `390px`.
  - Real API group archive & restore roundtrip on `/groups`: clicking overflow menu `"Guruhni arxivlash"` updates backend status and renders `"Arxivlangan"` badge; clicking `"Guruhni faollashtirish"` restores active state with zero console errors or HTML-in-JSON responses.
  - Telegram Mini App (`/tma`) signed `initData` auth in both Light (`390x844`) and Dark (`390x844`) schemes plus verified Admin role badge/quick-action layout (`0` overflow).

### Captured Visual Evidence (`docs/NEXT_7_0/screenshots/`)
- `landing_light_1366.png`, `landing_dark_1366.png`
- `panel_dashboard_dark_1366.png`, `panel_tests_audit_dark_1366.png`, `panel_users_dark_1366.png`
- `teacher_groups_dark_1366.png`, `smart_test_create_dark_1366.png`, `smart_test_create_dark_390.png`
- `tma_light_390.png`, `tma_dark_390.png`, `tma_admin_dark_390.png`
