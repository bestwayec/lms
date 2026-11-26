# GRANDEC NEXT 7.0 — Release Notes

## Highlights

- **Reliability & API Recovery:**
  - Unmatched `/api/*`, `/tma/api/*`, and `/essays/api/*` requests now return structured JSON `404` responses rather than HTML shell fallbacks.
  - Group archive, restore, dependency audit, and safe-delete endpoints align cleanly across frontend and backend, with `StudentGroupSerializer` exposing `status` so archived badges and restore actions persist reliably after reloads.
  - Telegram Mini App WebView re-authentication (`/tma/api/auth/`) cleanly avoids CSRF cookie/session mismatches and reissues fresh CSRF tokens across auth handlers.

- **Unified Light / Dark / System Design & Role Workspaces:**
  - Consistent Light, Dark, and System theme support with flicker-free initialization and semantic status/surface tokens across Admin, Teacher, Student, and TMA screens.
  - Dedicated workspace chrome separates Admin, Teacher, Student, and Parent workflows: removes student subject/plan pills from Admin views, syncs page titles dynamically per route, adds collapsible desktop sidebar and mobile navigation drawer controls.

- **Admin Panel 2.0, Groups 3.0 & Smart Test Builder 7.0:**
  - Fixed dark-mode modals, table selection contrast, and Audience Audit field mappings in Admin Panel.
  - Cleaner Group Management cards with accessible overflow dropdowns, inline loading locks, collapsible student join box, truthful Telegram connection/vedomost indicators, and semantic modals.
  - Smart Test Builder supports full Dark Mode styling, responsive mobile Editor/Preview tabs, `localStorage` draft recovery, and unsaved-changes leave guards.

- **Telegram Bot & Mini App 7.0:**
  - Resolved callback regex routing collisions so Admin bot menus (`adm_stats`, `adm_pending_*`, `adm_settings`, `adm_switch_*`, `adm_rec_*`, `adm_appr_*`) work reliably with strict DB role enforcement.
  - Telegram Mini App respects `colorScheme` & `themeParams`, renders role-specific Admin/Teacher shortcuts with high-contrast dark typography, recovers in-progress exam answers across reloads, and provides inline exit/submit confirmation with retry recovery.
