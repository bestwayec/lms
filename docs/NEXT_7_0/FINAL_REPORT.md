# GRANDEC NEXT 7.0 — Final Engineering Report

- **Branch:** `feat/grandec-next-7-0-platform-refinement`
- **Base Revision:** `main` (`e0447e1`, release baseline `v2.11.0`)
- **Delivery Status:** Complete across Phases 00–11; ready for Draft PR review, GitHub PostgreSQL/Nginx CI verification, and owner-approved release deployment.

---

## Executive Summary

GRANDEC NEXT 7.0 systematically audited and repaired the full platform surface—Django REST API routing, CSRF/session authentication across Telegram Mini App WebView, unified semantic Light/Dark/System UI design tokens, role-separated workspaces (`Admin`, `Teacher`, `Student`, `Parent`), Teacher Group management, Smart Test Builder (`SmartTestCreate`), Telegram Bot callback routing & RBAC, and multi-viewport responsiveness from `360px` to `1920px`.

All **14 confirmed bugs** (`BUG-001` through `BUG-014`) recorded in [BUG_REGISTRY.md](BUG_REGISTRY.md) were resolved and verified with automated unit/integration tests and real-Django Chromium Playwright E2E tests.

---

## Key Architecture & Product Improvements

1. **Critical API & CSRF Recovery (Phase 01, `74299ec` & `ed8fb65`)**
   - Guarded unmatched `/api/...`, `/tma/api/...`, `/essays/api/...` routes in `config/urls.py` with JSON `404` before SPA catch-all HTML fallback (`BUG-003`).
   - Added `/api/classroom/groups/<id>/{dependencies,archive,restore,safe-delete}/` lifecycle route compatibility in `apps/webapi/urls_classroom.py`, server idempotency protection in `views_school.py`, and `"status"` serialization on `StudentGroupSerializer` (`BUG-001`, `BUG-014`).
   - Eliminated TMA Android WebView `403 CSRF Failed` errors on `/tma/api/auth/` via `@authentication_classes([])` and explicit `django.middleware.csrf.get_token(request)` issuance (`BUG-002`).
   - Hardened `frontend/src/lib/httpClient.ts` and `api.ts` to validate Content-Type and reject HTML bodies cleanly without `SyntaxError: Unexpected token '<'`.

2. **Unified Design System & Role-Separated Shell (Phases 02–04, `8035c10`, `9472ef6`)**
   - Unified Light/Dark/System semantic CSS tokens in `frontend/src/index.css` & `ThemeContext.tsx` with early inline theme bootstrap in `index.html` (no FOUC).
   - Built reusable primitives (`Modal`, `ConfirmDialog`, `Alert`, `Dropdown`, `Tabs`, etc.) in `frontend/src/components/ui/index.tsx` & `styles/ui.css`.
   - Separated Admin, Teacher, Student, and Parent navigation chrome (`Layout.tsx`, `Navbar.tsx`, `MobileNavDrawer.tsx`, `BottomNav.tsx`); removed student `SubjectSwitcher` and `PRO` upgrade prompts from Admin routes; synchronized route `<title>` dynamically via `frontend/src/lib/routeTitle.ts`.
   - Added collapsible desktop sidebar state (`sidebarCollapsed`) and direct mobile drawer button.

3. **Workspace Overhauls: Admin, Groups, Smart Test Builder (Phases 05–07, `efeefb8`, `4ed01a9`, `db3bf2b`, `ed8fb65`)**
   - **Admin Panel:** Migrated `PanelTests.tsx`, `PanelUsers.tsx`, and `PanelDashboard.tsx` modals/tables/rows onto semantic Dark Mode surfaces and aligned the Audience Audit modal payload mapping (`total_public_tests`, `active_assignments_count`, `existing_attempts_count`, `current_audience_mode`, `proposed_audience_mode`).
   - **Teacher Groups:** Replaced crowded card action rows with accessible `<Dropdown>` menus, disabled unlinked Vedomost triggers honestly, added duplicate-submit locks, collapsed the secondary student Join form, and migrated analytics/White-Label/Dependency modals to semantic `<Modal>`.
   - **Smart Test Builder:** Converted hardcoded light surfaces in `SmartTestCreate.tsx` to semantic theme tokens, added mobile `Editor`/`Preview` tabs, and implemented `localStorage` auto-draft persistence plus `beforeunload` exit protection.

4. **Telegram Bot & Mini App 7.0 (Phases 08–09, `3a24737`, `f938ec4`, `ed8fb65`)**
   - Fixed `group_assistant_callback_handler` regex in `apps/notifications/bot/group_assistant.py` so Admin callbacks (`adm_stats`, `adm_pending_*`, `adm_settings`, `adm_switch_*`, `adm_rec_*`, `adm_appr_*`) reach `callback_handler` cleanly (`BUG-012`).
   - Enforced strict verified-admin and verified-teacher DB role guards on `adm_*` and `tch_*` callbacks, upgraded Teacher & Admin keyboards to `/dashboard` & WebApp deep links, and added `tests/test_next7_phase8_bot_roles.py`.
   - Upgraded TMA (`Tma.tsx`, `Tma.css`, `Home.tsx`, `TestFlow.tsx`, tabs) to honor `Telegram.WebApp.colorScheme`/`themeParams`, resolved dark-mode heading contrast overrides against `theme.css`, added role-aware Admin/Teacher quick-action panels, added `sessionStorage` answer recovery and non-blocking inline submit/exit confirmations, and fixed `"branches"` i18n parity across `uz`/`ru`/`en`.

---

## Verification Summary (Post-Final-Edit)

| Gate | Result | Details |
| :--- | :--- | :--- |
| Backend Lint (`ruff check .`) | **PASS** | `All checks passed!` (`0` errors) |
| Django System Check | **PASS** | `System check identified no issues (0 silenced).` |
| Django Migrations Check | **PASS** | `No changes detected` |
| Full Backend Suite (`pytest -q`) | **PASS** | `2026 passed, 14 skipped, 272 subtests passed` (`0` failed; 13 PG lock tests + 1 DejaVuSans font test env-skipped) |
| Frontend Lint (`oxlint src`) | **PASS** | `0 warnings and 0 errors` (196 files, 116 rules) |
| Frontend Unit Tests | **PASS** | `34 passed, 0 failed` (4 suites) |
| TypeScript + Vite Build | **PASS** | Clean build in `5.85s` |
| Real-Django Chromium E2E | **PASS** | `39 passed, 0 failed, 0 console errors`, 0 horizontal overflow (`360–1920px`) |

See detailed breakdowns in [TEST_RESULTS.md](TEST_RESULTS.md), [SECURITY_REPORT.md](SECURITY_REPORT.md), and [PERFORMANCE_REPORT.md](PERFORMANCE_REPORT.md).
