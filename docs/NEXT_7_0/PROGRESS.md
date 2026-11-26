# GRANDEC NEXT 7.0 — Progress Tracker

- **Branch:** `feat/grandec-next-7-0-platform-refinement`
- **Base:** `main` (`e0447e16956404192a30fde6c6de9ba16c3ef07c`, `v2.11.0`)

| Phase | Name | Status | Summary / Notes |
| :--- | :--- | :--- | :--- |
| Phase 00 | Complete Repository Audit | PASS | Audited backend, frontend, bot, TMA, nginx, CI; recorded baseline tests & 13 confirmed bugs. |
| Phase 01 | Critical API & Authentication Recovery | NOT STARTED | Next: Groups JSON error, SPA fallback guard, `api.ts` hardening, TMA CSRF & session recovery. |
| Phase 02 | Unified GRANDEC Design System | NOT STARTED | Semantic tokens, Light/Dark/System themes, reusable UI component primitives. |
| Phase 03 | Role-Based Workspace Architecture | NOT STARTED | Separate Admin / Teacher / Student shells, remove student subject switcher from Admin, fix `<title>`. |
| Phase 04 | Responsive Layout 2.0 | NOT STARTED | Collapsible sidebar, mobile menu trigger, 320–1920px grid/flex stabilization. |
| Phase 05 | Admin Panel 2.0 | NOT STARTED | Fix dark-mode modals/tables in `PanelTests` / `PanelUsers`, refine `PanelDashboard`. |
| Phase 06 | Group Management & Teacher Workspace 3.0 | NOT STARTED | Group card actions & overflow menu, inline create validation, Telegram connect/send UX. |
| Phase 07 | Smart Test Builder 7.0 | NOT STARTED | Theme-aware `SmartTestCreate`, responsive editor/preview tabs, draft recovery & validation. |
| Phase 08 | Telegram Bot 7.0 | NOT STARTED | Role menus (Admin/Teacher/Student), back/cancel, duplicate callback & authz tests. |
| Phase 09 | Telegram Mini App 7.0 | NOT STARTED | Telegram theme integration, role-aware TMA UI, exam resume/retry reliability. |
| Phase 10 | Performance, Security & Quality Optimization | NOT STARTED | Post-implementation N+1, bundle, and security re-audit. |
| Phase 11 | Full Testing, CI & Release Gate | NOT STARTED | Full pytest, frontend tests/build, Playwright E2E + multi-viewport visual checks, final docs. |
