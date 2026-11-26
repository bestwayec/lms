# GRANDEC NEXT 7.0 — Security & Authorization Report

## 1. Authentication, Session & CSRF Hardening

- **Telegram Mini App Re-Auth CSRF Recovery (`BUG-002`):**
  - Updated `tma_auth_view` (`apps/telegram_app/views.py`) with explicit `@authentication_classes([])` so stale browser session cookies do not trigger DRF `SessionAuthentication` CSRF enforcement on the signed HMAC `initData` authentication handshake itself.
  - Added `django.middleware.csrf.get_token(request)` across `tma_auth_view`, `TelegramWidgetAuthView`, and `SessionStatusView` so valid `csrftoken` cookies are freshly issued immediately alongside session/JWT credentials for subsequent stateful API calls.
  - Preserved full CSRF enforcement across all browser/session-mutating endpoints (zero blanket `csrf_exempt` introduced).

- **Unmatched API Catch-All Boundary (`BUG-003`):**
  - Ordered explicit JSON `404` route guards for `/api/...`, `/tma/api/...`, `/essays/api/...` ahead of Django's SPA `<path:resource>` catch-all in `config/urls.py`, preventing erroneous HTML `200 OK` fallback payloads and surfacing clean JSON errors.

## 2. Role-Based Access Control (RBAC) Enforcement

- **Telegram Bot Privileged Callback Separation (`BUG-012`):**
  - Fixed `group_assistant_callback_handler` regex in `apps/notifications/bot/group_assistant.py` so global Admin callbacks (`adm_stats`, `adm_pending_*`, `adm_settings`, `adm_switch_*`, `adm_rec_*`, `adm_appr_*`) are never intercepted by group-assistant routing.
  - Enforced DB-backed verified-admin checks on `adm_*` callbacks and verified-teacher checks on `tch_*` callbacks inside `apps/notifications/bot/handlers.py`, backed by `tests/test_next7_phase8_bot_roles.py` (`66 passed, 4 PG-skipped` in targeted bot suite).

- **UI Role Boundary Isolation (`BUG-007`):**
  - Separated Admin, Teacher, Student, and Parent navigation chrome and removed student `<SubjectSwitcher />` and subscription upsell pills from Admin workspaces and test-authoring views (`/tests/create`, `/tests/scan-omr`).
  - Role-gated TMA Admin & Teacher workspace shortcut cards strictly behind backend-verified user roles returned by `/tma/api/auth/`.

## 3. Data Integrity, Idempotency & Input/XSS Safety

- **Group Lifecycle & Serialization (`BUG-001`, `BUG-014`):**
  - Standardized group archive/restore/dependency/safe-delete endpoints in `apps/webapi/urls_classroom.py`, enforced idempotency keys on `groups_view` group creation (`apps/webapi/views_school.py`), and included `"status"` in `StudentGroupSerializer` so archived groups reflect state accurately after API reloads.
- **Private Artifact Permission Checks (`BUG-013`):**
  - Retained strict `0o600` POSIX permission assertions on generated private PDF/report files (`tests/test_interactive_results_and_tg_sync.py`, `tests/test_teacher_grade_override_and_vedomost.py`) for Linux environments while skipping OS-specific `st_mode` mask checks on Windows NTFS (`if os.name != "nt":`).
- **Frontend Response & XSS Hygiene:**
  - Centralized HTML-body rejection on JSON endpoints in `frontend/src/lib/httpClient.ts` (`4` unit assertions in `frontend/tests/api-client.test.ts`), alongside verified HTML/SVG XSS sanitization tests (`frontend/tests/xss.test.ts` inside `34/34` unit pass).

## 4. Static & Repository Hygiene

- `ruff check .`: `0` findings.
- `oxlint src`: `0` warnings / `0` errors across 196 frontend files.
- Authorship hygiene: all commits authored solely as `Komiljon Roziyev <kruziyev0@gmail.com>` with zero AI signatures.
