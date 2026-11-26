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
| Phase 05 | Admin Panel 2.0 | IN PROGRESS | Fixing dark-mode modals, selected rows, badge tokens, and error/confirmation states in `PanelTests.tsx`, `PanelUsers.tsx`, and `PanelDashboard.tsx`. |
| Phase 06 | Group Management & Teacher Workspace 3.0 | NOT STARTED | Group card actions & overflow menu, inline create validation, Telegram connect/send UX. |
| Phase 07 | Smart Test Builder 7.0 | NOT STARTED | Theme-aware `SmartTestCreate`, responsive editor/preview tabs, draft recovery & validation. |
| Phase 08 | Telegram Bot 7.0 | NOT STARTED | Role menus (Admin/Teacher/Student), back/cancel, duplicate callback & authz tests. |
| Phase 09 | Telegram Mini App 7.0 | NOT STARTED | Telegram theme integration, role-aware TMA UI, exam resume/retry reliability. |
| Phase 10 | Performance, Security & Quality Optimization | NOT STARTED | Post-implementation N+1, bundle, and security re-audit. |
| Phase 11 | Full Testing, CI & Release Gate | NOT STARTED | Full pytest, frontend tests/build, Playwright E2E + multi-viewport visual checks, final docs. |
