# GRANDEC NEXT 7.0 — Independent Release Audit Report (PR #151)

- **Branch Audited:** `feat/grandec-next-7-0-platform-refinement`
- **Pull Request:** https://github.com/bestwayec/lms/pull/151
- **Baseline Compared Against:** `main @ e0447e1` (`v2.11.0`)
- **Audit Scope:** All 64 modified/added files across the prior 11 commits plus post-audit hardening fixes and regression tests.

---

## 1. Confirmed Findings Identified & Fixed During Independent Audit

1. **High Security Defect — TMA Test API Cookie-Session CSRF Bypass (`apps/telegram_app/test_api.py`)**
   - **Finding:** `tma_test_start_view`, `tma_test_answer_view`, `tma_test_submit_view`, and `tma_attempt_result_view` were decorated with `@csrf_exempt` while `_jwt_auth` checked `request.user.is_authenticated` **before** validating a Bearer JWT header. Because `/tma/api/auth/` calls `django.contrib.auth.login(request, user)`, an active `sessionid` cookie allowed unsafe POST requests without `Authorization: Bearer` or `X-CSRFToken`.
   - **Fix:** Updated `_jwt_auth` / `_auth_user_or_error` to evaluate `JWTAuthentication().authenticate(request)` first, and enforce `SessionAuthentication().enforce_csrf(request)` (returning HTTP `403` on failure) whenever a Django session user authenticates without a Bearer token on unsafe methods.
   - **Regression Test:** `TmaTestApiCsrfAndSubmitTests` in [tests/test_next7_audit_regressions.py](../../tests/test_next7_audit_regressions.py).

2. **High Functional Defect — TMA Timer StrictMode Double-Submit & Broken Retry (`frontend/src/pages/tma/TestFlow.tsx`)**
   - **Finding:** (a) Timed auto-submit invoked `void doSubmit(...)` directly inside the `setRemaining((prev) => ...)` state updater, causing duplicate submission invocations under React StrictMode and triggering `oxlint` `react(refs)` warnings. (b) Clicking `tma_retry` ("Qayta topshirish") on the result view returned to `phase = 'info'` while retaining the completed `start.attempt_id` instead of calling `TmaApi.startTest(testId)` for a new active attempt.
   - **Fix:** Moved timed auto-submit outside the state updater into a dedicated `useEffect` guarded by `autoSubmittedRef`; introduced `attemptNonce` state triggered by retry so a fresh attempt is started cleanly; resolved all 3 `oxlint` warnings in `TestFlow.tsx`.
   - **Verification:** Verified end-to-end in Chromium Playwright (`tma_exam_submit_e2e_score` -> `100%` -> `tma_exam_retry_starts_fresh_attempt`).

3. **Medium Defect — Malformed Bot Callback Crashes, `center_admin` Role & Broken Hash WebApp URL (`apps/notifications/bot/handlers.py`, `apps/notifications/bot/group_assistant.py`)**
   - **Finding:** (a) Callback branches `adm_appr_tchr_`, `adm_rej_tchr_`, `publish_feedback_`, `reject_feedback_` (`handlers.py`) and `tch_inv_`, `tch_appr_`, `tch_rej_` (`group_assistant.py`) parsed trailing IDs with unguarded `int(data.removeprefix(...))`, throwing `ValueError` on malformed payloads. (b) `_is_verified_teacher` omitted `center_admin`. (c) `tch_create` used hash route `/tma/#/teacher/studio` on a `BrowserRouter` SPA instead of `/tma/`.
   - **Fix:** Replaced raw `int(...)` parsing with safe integer helpers returning a clean alert on invalid payloads; added `center_admin` to `_is_verified_teacher`; updated TMA Mini App button URL to `/tma/`. Also verified independently that `/newmock` (`newmock_handler` & `menu_teacher_newmock`) already enforces `@require_role("TEACHER")` via `tests/test_telegram_bot_features.py` and `tests/test_next7_audit_regressions.py`.
   - **Regression Test:** `BotCallbackMalformedAndRoleTests` in [tests/test_next7_audit_regressions.py](../../tests/test_next7_audit_regressions.py).

4. **Medium Reliability Defect — Group Creation Idempotency Stale Cache (`apps/webapi/views_school.py`)**
   - **Finding:** `groups_view` keyed the 60-second `X-Idempotency-Key` cache strictly on `user_id:idem_key` without hashing `(name, subject)` or verifying the cached `StudentGroup` still existed, allowing reuse of a key after group deletion or payload changes to return stale/deleted group metadata.
   - **Fix:** Hash `{user.id}:{idem_key}:{name}:{subject}`, verify `StudentGroup.objects.filter(id=cached_data["id"], teacher=request.user).exists()`, and wrap group uniqueness check + creation in `transaction.atomic()` with `IntegrityError` handling.
   - **Regression Test:** `GroupIdempotencyAuditTests` in [tests/test_next7_audit_regressions.py](../../tests/test_next7_audit_regressions.py).

5. **Minor UI/Contrast Fixes — TMA Dark `<h3>` & Profile Admin Badge (`frontend/src/pages/tma/Tma.css`, `ProfileTab.tsx`)**
   - **Finding:** Generic `<h3>` elements inside TMA Dark Mode (such as `ClassroomTab` empty state) inherited light `#0F172A` from `html.light h3` in `theme.css`; `ProfileTab.tsx` rendered `'🎓 Student'` badge for `admin`/`superadmin` users.
   - **Fix:** Added high-specificity `.tma-root.is-dark h1, h2, h3 { color: var(--tma-ink); }` cleanly separated from `.tma-h3`, and updated `ProfileTab.tsx` to display `'👑 Admin'` for admin accounts.

---

## 2. Performance & Bundle Comparison (`main @ e0447e1` vs Audited Branch)

Measured using isolated `main` worktree `vite build` (`3.80s`) vs audited PR branch `vite build` (`3.12s`):

| Metric / Asset | `main` (`e0447e1`) | PR #151 (Audited) | Delta |
| :--- | :--- | :--- | :--- |
| `dist/index.html` | `5.12 kB` (`1.54 kB` gzip) | `5.38 kB` (`1.69 kB` gzip) | `+0.15 kB` gzip (inline zero-FOUC theme bootstrap) |
| `dist/assets/index-*.css` | `230.23 kB` (`40.19 kB` gzip) | `239.87 kB` (`41.90 kB` gzip) | `+1.71 kB` gzip (semantic tokens + UI primitives) |
| `dist/assets/index-*.js` | `292.59 kB` (`87.75 kB` gzip) | `308.31 kB` (`91.34 kB` gzip) | `+3.59 kB` gzip (`httpClient`, `routeTitle`, shared UI components) |
| `dist/assets/Tma-*.css` | `10.29 kB` (`2.60 kB` gzip) | `13.04 kB` (`3.18 kB` gzip) | `+0.58 kB` gzip (Light/Dark/ThemeParams CSS) |
| `dist/assets/Tma-*.js` | `18.58 kB` (`5.45 kB` gzip) | `21.47 kB` (`6.02 kB` gzip) | `+0.57 kB` gzip (Admin/Teacher role views & theme handling) |
| `dist/assets/PanelUsers-*.js` | `13.41 kB` (`3.67 kB` gzip) | `12.83 kB` (`3.49 kB` gzip) | `-0.18 kB` gzip |
| `dist/assets/Groups-*.js` | `37.63 kB` (`9.43 kB` gzip) | `37.45 kB` (`9.50 kB` gzip) | `+0.07 kB` gzip |
| `dist/assets/SmartTestCreate-*.js` | `35.44 kB` (`10.65 kB` gzip) | `38.90 kB` (`11.26 kB` gzip) | `+0.61 kB` gzip (mobile tabs & draft recovery) |
| Lazy locale & chart splits (`_virtual_i18n-*`, `vendor-charts`) | Preserved | Preserved | Unchanged |

Backend query/cache regression suite (`tests/test_grandec_8_3_performance.py`): **5/5 passed** (zero N+1 query regressions; TMA test cache invalidates immediately on group archive/removal).

---

## 3. Independent Post-Fix Verification Matrix

| Gate | Command | Result |
| :--- | :--- | :--- |
| Audit Regression Suite | `pytest tests/test_next7_audit_regressions.py -q` | **4 passed, 0 failed** |
| Backend Lint | `ruff check .` | **All checks passed!** |
| Django Checks & Migrations | `python manage.py check && python manage.py makemigrations --check --dry-run` | **0 issues / No changes detected** |
| Full Backend Suite | `pytest -q` (`DJANGO_SETTINGS_MODULE=config.settings.test`) | **2030 passed, 14 env-skipped, 272 subtests passed (`0` failed)** |
| Frontend Lint | `npm --prefix frontend run lint` (`oxlint src`) | **0 warnings and 0 errors** (196 files, 116 rules) |
| Frontend Unit Tests | `npm --prefix frontend test` (`node --test tests/*.test.ts`) | **34 passed, 0 failed** (4 suites) |
| Frontend Build | `npm --prefix frontend run build` (`tsc -b && vite build`) | **Built in 3.12s (`0` errors)** |
| Chromium Playwright E2E | `run_next7_playwright_e2e.py` (compiled `dist` + real Django WSGI) | **41 passed, 0 failed, 0 console errors** |
| GitHub CI / Postgres / Nginx / Security | Verified against PR #151 head commit via `gh pr checks` | See PR #151 status checks |

---

## 4. Real-Device Verification Limitations (Disclosed Explicitly)

- **Native Telegram Android & iOS Mobile Clients:** Physical Telegram mobile WebView binaries (`Telegram Android` / `Telegram iOS`) and live push/webhook roundtrips against `@uz_essaygrader_bot` cannot execute from this local headless Windows environment.
  - Telegram Mini App rendering, HMAC-SHA256 `initData` authentication, Dark/Light `colorScheme`, responsive `390x844` layout, exam submission, and retry flows were verified in **real Chromium Playwright** against compiled `frontend/dist/` with a mocked `window.Telegram.WebApp` bridge and live Django backend.
  - Telegram Bot callbacks, RBAC enforcement, and regex dispatch were verified deterministically with `python-telegram-bot` update/query mocks against real Django ORM models (`tests/test_next7_phase8_bot_roles.py`, `tests/test_next7_audit_regressions.py`, `tests/test_telegram_bot_features.py`).
- **PostgreSQL & Nginx Environment-Gated Local Skips:** Local Windows `pytest` ran against SQLite (13 PostgreSQL row/advisory-lock tests + 1 `DejaVuSans` font test skipped locally); full PostgreSQL concurrency tests and Nginx private-media checks run inside **GitHub Actions CI**.
