# GRANDEC NEXT 7.0 — Progress Tracker

- **Branch:** `feat/grandec-next-7-0-platform-refinement`
- **Base:** `main` (`e0447e16956404192a30fde6c6de9ba16c3ef07c`, `v2.11.0`)

| Phase | Name | Status | Summary / Notes |
| :--- | :--- | :--- | :--- |
| Phase 00 | Complete Repository Audit | PASS | Audited backend, frontend, bot, TMA, nginx, CI; recorded baseline tests & 13 confirmed bugs. |
| Phase 01 | Critical API & Authentication Recovery | PASS | Fixed unmatched API JSON 404 guard, Groups lifecycle routes & duplicate-submit locks, centralized `httpClient.ts`/`api.ts` Content-Type & HTML checks, TMA `@authentication_classes([])` + `get_token` CSRF issuance (`62` pytest + `32` frontend unit tests PASS). |
| Phase 02 | Unified GRANDEC Design System | PASS | Consolidated semantic Light/Dark/System tokens in `index.css` & `ThemeContext.tsx` (zero FOUC in `index.html`), removed unsafe `!important` color overrides, and built 20 reusable UI primitives in `components/ui/index.tsx`. |
| Phase 03 | Role-Based Workspace Architecture | PASS | Separated Admin/Teacher/Student/Parent navigation & headers (`Layout.tsx`, `Navbar.tsx`, `BottomNav.tsx`, `MobileNavDrawer.tsx`), added workspace switcher, removed student `SubjectSwitcher`/`PRO` badges from Global Admin, synced route `<title>` via `routeTitle.ts` (`34` frontend unit tests, `oxlint`, `tsc -b && vite build` PASS). |
| Phase 04 | Responsive Layout 2.0 | PASS | Added collapsible desktop sidebar (`sidebarCollapsed` in `localStorage`), mobile menu drawer button in `Navbar.tsx`, and `.main` horizontal overflow containment across `320–1920px` viewports. |
| Phase 05 | Admin Panel 2.0 | PASS | Migrated `PanelTests.tsx`, `PanelUsers.tsx`, and `PanelDashboard.tsx` modals/alerts/selected rows to semantic design tokens & accessible `<Modal>`/`<Alert>`/`<ConfirmDialog>`, added group load error recovery & in-modal bulk/audit error feedback (`oxlint` 0, `34/34` unit, `vite build` PASS). |
| Phase 06 | Group Management & Teacher Workspace 3.0 | PASS | Refactored `Groups.tsx` cards with `<Dropdown>` overflow menu for secondary/destructive actions, full-width create form + collapsible join form, disabled loading buttons, truthful Telegram connection state (`vedomost` disabled until linked), semantic Light/Dark tokens across analytics/members/dependencies `<Modal>` and White-Label `<Modal>` (`oxlint` 0, `34/34`, `vite build` PASS). |
| Phase 07 | Smart Test Builder 7.0 | PASS | Migrated `SmartTestCreate.tsx` to semantic theme tokens (`var(--bg-surface)`, `var(--bg-elevated)`, `var(--text-*)`, `var(--success/warning/danger/info-*)`), added responsive mobile Editor/Preview `<Tabs>` via `ui.css`, `localStorage` auto-draft persistence/recovery, and `beforeunload` unsaved-changes guard (`oxlint` 0, `34/34`, `tsc -b && vite build` PASS). |
| Phase 08 | Telegram Bot 7.0 | IN PROGRESS | Fixing `adm_*` callback routing conflict between `group_assistant_callback_handler` and `callback_handler`, hardening admin callback RBAC, and upgrading Admin/Teacher menus. |
| Phase 09 | Telegram Mini App 7.0 | NOT STARTED | Telegram theme integration, role-aware TMA UI, exam resume/retry reliability. |
| Phase 10 | Performance, Security & Quality Optimization | NOT STARTED | Post-implementation N+1, bundle, and security re-audit. |
| Phase 11 | Full Testing, CI & Release Gate | NOT STARTED | Full pytest, frontend tests/build, Playwright E2E + multi-viewport visual checks, final docs. |
