# GRANDEC NEXT 7.0 — Execution Roadmap

Sequential execution plan preserving backward compatibility and all historical data:

1. **Phase 00 — Repository Audit & Baseline (`PASS` upon doc commit)**
   - Audit Django apps, REST URLs, SPA routes, auth/CSRF lifecycles, theme tokens, workspaces, bot handlers, TMA, CI, Nginx.
   - Establish baseline test metrics (`docs/NEXT_7_0/AUDIT.md`, `BUG_REGISTRY.md`, `ACCEPTANCE_CRITERIA.md`).

2. **Phase 01 — Critical API & Authentication Recovery (`BUG-001`, `BUG-002`, `BUG-003`, `BUG-011`)**
   - Guard `config/urls.py` SPA fallback so `/api/*`, `/tma/api/*`, `/essays/api/*`, `/arena/api/*`, `/subscribe/api/*` return structured JSON 404 rather than HTML.
   - Harden `frontend/src/lib/api.ts` (`api()` & `sessionApi()`): `Content-Type` validation before `res.json()`, HTTP 204/empty handling, correlation IDs, localized error mapping, duplicate-mutation guard / idempotency headers, safe diagnostics without leaking HTML/stack traces.
   - Align `Groups.tsx` lifecycle URLs with `apps/webapi/urls_classroom.py` (plus clean backward-compatible route aliases if needed).
   - Fix Telegram Mini App & Session CSRF lifecycle: `@authentication_classes([])` on pure credential-exchange endpoints (`tma_auth_view`), `get_token(request)` whenever Django session login occurs (`tma_auth_view`, `TelegramWidgetAuthView`, `SessionStatusView`, `tma_index_view`), clear stale `inflightInitData` after completion or expiry, ensure TMA recovers cleanly on expired tokens/WebView resume while keeping DRF `SessionAuthentication` CSRF strictly enforced.

3. **Phase 02 — Unified GRANDEC Design System**
   - Consolidate semantic design tokens (`--bg-main`, `--bg-surface`, `--bg-elevated`, `--text-primary`, `--text-secondary`, `--text-muted`, `--border-subtle`, `--brand-primary`, `--status-*`, `--focus-ring`, `--disabled-*`) in `index.css` without conflicting overrides.
   - Support Light Mode, Dark Mode, and `system` (`prefers-color-scheme`) in `ThemeContext.tsx` and `index.html` without FOUC or forced key deletion.
   - Add reusable UI primitives (`frontend/src/components/ui/`) — `Button`, `Input`, `Textarea`, `Select`, `Checkbox`, `Radio`, `Badge`, `Card`, `Modal`, `ConfirmDialog`, `Dropdown`, `Tabs`, `Table`, `Pagination`, `Toast`, `Alert`, `Tooltip`, `Skeleton`, `EmptyState`, `ErrorState` — with WCAG 2.2 AA contrast, keyboard focus rings, Escape/backdrop modal focus handling, and `prefers-reduced-motion`.

4. **Phase 03 — Role-Based Workspace Architecture**
   - Remove student `<SubjectSwitcher />` and student billing pills from Admin headers/shells; surface subject/exam-type filters only in Student or targeted management pages.
   - Separate Admin, Teacher, and Student sidebars/navigation with clear workspace switching for multi-role users.
   - Guarantee dynamic localized `document.title` across every route (`RouteTitleSync` + `<SEO>`), eliminating stale `"Tizimga kirish"` titles on `/panel` and `/dashboard`.

5. **Phase 04 — Responsive Layout 2.0**
   - Stabilize `.app`, `.sidebar` (collapsible desktop + mobile drawer trigger in navbar), sticky `.topbar`, safe-area padding, `min-width: 0`, wrap/truncation rules, `44px` touch targets, modal sizing across 320px–1920px and 100%–150% zoom without unintended horizontal page overflow.

6. **Phase 05 — Admin Panel 2.0**
   - Upgrade `PanelDashboard`, `PanelTests`, `PanelUsers`, and related admin modals to unified design tokens (`BUG-004`).
   - Make Safe Bulk Test Management & Visibility Audit modals crystal clear in both Light and Dark Mode (eligible/protected/skipped/succeeded/failed counts, explicit confirmation, server revalidation).

7. **Phase 06 — Group Management & Teacher Workspace 3.0**
   - Redesign `/groups` cards, creation/edit forms (inline validation, duplicate-submit guard), adaptive responsive grids, and accessible overflow menu (`Archive`, `Delete`, `Invite settings`) alongside visible primary actions (`Members & Analytics`, `Edit`, `Telegram`).
   - Polish Telegram group connect/disconnect/status/broadcast feedback and disable unavailable delivery actions cleanly.

8. **Phase 07 — Smart Test Builder 7.0**
   - Refactor `SmartTestCreate.tsx` off hardcoded Light Mode styles to semantic design tokens (`BUG-005`), structure desktop split editor/preview & mobile tab workflow, unsaved-change guard + draft recovery, and verify 15+ question import/publish/assign/take/archive journey.

9. **Phase 08 — Telegram Bot 7.0**
   - Upgrade Admin, Teacher, and Student menus (`apps/notifications/bot/handlers.py`) with concise Uzbek copy, back/cancel navigation, real permission-checked callbacks, stale-button & duplicate-callback guards, and tests.

10. **Phase 09 — Telegram Mini App 7.0**
    - Adapt `Tma.css` & `Tma.tsx` to Telegram `themeParams`/`colorScheme` + Dark/Light themes, dynamic `100dvh`, `BackButton`, role-aware Admin/Teacher/Student views, offline/resume/double-submit exam protection, and readable error/retry states.

11. **Phase 10 — Performance, Security & Quality Optimization**
    - Eliminate unnecessary N+1 queries / rerenders / polling spikes, measure bundle & query metrics, and verify authz/CSRF/XSS/private-media protections.

12. **Phase 11 — Full Testing, CI & Release Gate**
    - Execute backend (`pytest` + Django checks), frontend (`lint`, `test`, `build`), Playwright E2E + multi-viewport visual regression (`360/390/768/1024/1366/1920` × Light/Dark), write final deliverables under `docs/NEXT_7_0/`, commit cleanly, and prepare branch/PR.
