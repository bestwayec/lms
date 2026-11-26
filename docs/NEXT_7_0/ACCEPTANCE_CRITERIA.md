# GRANDEC NEXT 7.0 — Acceptance Criteria & Definition of Done

1. **API & Auth Recovery (Phase 01):**
   - `/groups` archive, restore, dependencies, safe-delete, create, edit, and join work without `"<!doctype "` JSON parse errors.
   - Unmatched `/api/*`, `/tma/api/*`, `/essays/api/*`, `/arena/api/*`, `/subscribe/api/*` requests return structured JSON `404` instead of HTML `200`.
   - Centralized `api()` validates `Content-Type`, handles HTTP `204` / empty responses cleanly, guards against duplicate mutation clicks, attaches correlation IDs (`X-Request-ID`), and maps 401/403/400/409/429/5xx/network failures to localized user messages without exposing raw HTML.
   - TMA auth (`/tma/api/auth/`) succeeds cleanly even when an existing `sessionid` cookie is present without `csrftoken`, issues `csrftoken` on session-creating endpoints, clears stale `initData` promise caches cleanly, and passes security tests (valid/invalid/tampered/expired/replay `initData`, missing/invalid CSRF on session mutations, expired session recovery, cross-user/cross-group isolation).
2. **Design System & Themes (Phase 02 & 05):**
   - Unified semantic CSS tokens drive both Light Mode and Dark Mode cleanly (plus persisted `'system'` preference without initial flash).
   - Shared UI component primitives cover Buttons, Form controls, Badges, Cards, Modals, ConfirmDialogs, Dropdowns, Tabs, Tables, Pagination, Toasts, Alerts, Tooltips, Skeletons, EmptyState, ErrorState.
   - Zero white-on-white or unreadable text in `PanelTests` Safe Bulk / Visibility Audit modals, selected rows, or `PanelUsers` / `SmartTestCreate` in Dark Mode.
3. **Role-Based Workspaces & Responsive Shell (Phase 03 & 04):**
   - Global Admin no longer sees student `<SubjectSwitcher />` or student billing upgrades in global topbar/shell; Admin, Teacher, and Student workspaces reflect actual backend permissions.
   - Browser `<title>` updates accurately on every authenticated and public route (`/panel`, `/dashboard`, `/groups`, `/tests/create`, etc.).
   - No clipped headers, overlapping cards, horizontal page overflow, or trapped modal buttons across 320px–1920px viewports and 100%–150% zoom.
4. **Groups, Test Builder, Bot & Mini App (Phase 06–09):**
   - `/groups` action buttons stay inside card bounds (overflow menu for secondary/destructive actions); create/edit/archive/delete/Telegram workflows work reliably.
   - `/tests/create` (`SmartTestCreate`) adapts to Light/Dark themes, provides clear desktop & mobile workflow + draft recovery, preserves all scoring/access rules, and handles 15+ question import → publish → assign → attempt → grade → archive.
   - Bot role menus (`Admin`, `Teacher`, `Student`) contain only working actions with concise Uzbek messages, back/cancel support, and permission/idempotency tests.
   - Telegram Mini App (`/tma`) honors Light/Dark theme + Telegram `themeParams`, separates Admin/Teacher/Student experiences, and protects active exams across reload/network loss/double-submit.
5. **Optimization, Testing & Release Gate (Phase 10–11):**
   - `ruff check .`, `manage.py check`, `makemigrations --check --dry-run`, `pytest` (accounting explicitly for platform-specific checks), `oxlint`, frontend tests, production `vite build`, Playwright E2E + multi-viewport visual regression pass and evidence is saved in `docs/NEXT_7_0/`.
