# GRANDEC production quality — 2026-11-12

Repository: `bestwayec/lms`. Branch: `fix/grandec-production-quality`.
Base: `1309869406a5c310ce6b43c8b80d960cc065acdb` (also the fetched `origin/main`).
This is an incremental reliability release, not a claim that every workflow has been redesigned or audited exhaustively. No production server, production account, production database, BESTWAY resource, deployment, or real financial transaction was changed. AI tests use mocks; no paid AI requests were made.

## Findings and implemented behavior

| Finding | Status | Evidence and change |
| --- | --- | --- |
| G-001 public navigation error | NOT REPRODUCED | Local Chromium direct and client navigation to Tests/Essays reaches login without an exception. Pricing now has a public catalogue. Existing ErrorBoundary stale-chunk recovery was retained and exercised by aborting one lazy module request; full reload recovers. This simulated failure does not identify the reported production exception. Service worker has no fetch handler. |
| G-002 onboarding persistence | FIXED | Removed fire-and-forget endpoint fallback chain, premature confetti, fabricated local profile, and shared local completion flags. Both finish and skip await `/api/auth/onboarding/`, with a bounded timeout, duplicate-submit guard, accessible error, retained selections, and retry. Auth state uses the returned normalized profile. A backend regression also found that the response could serialize an already cached reverse profile relation; the response now uses the just-saved instance. Invalid numeric/subject inputs return 400 before plan fields change. |
| G-003 changing study plan | FIXED / NOT REPRODUCED | Dashboard already used GoalModal rather than onboarding. Retained that behavior. Replaced two sequential best-effort writes with one canonical save; added study reminder editing, valid initial target grades, focus containment/restoration, disabled in-flight controls, and failure/retry coverage. No introduction/referral questions are shown. |
| G-004 dashboard data | PARTIAL | Removed curated topic percentages, default radar scores, 35–95 clamping, two always-active weekdays, the default one-day streak, cross-account stored plan fallback, and fabricated grade targets in track labels. Charts/lists share measured API labels/counts; 0% and 100% remain intact. No measurements means an empty state; failed/loading requests do not render achievement cards. Daily answer counts now filter by subject and exclude previews. Weekly markers use the existing server response; that response still infers history from streak metadata rather than a complete event ledger. Backend study-minute estimates and the existing coupling of question goal/minutes remain follow-up work. |
| G-005 UI/CSS | PARTIAL | Current Tailwind v4 setup was verified, not replaced. Light/dark Chromium screenshots and seven viewport widths cover the dashboard. Fixed a clipped group-join button and narrow goal-dialog grids; added focus, selected-state and reduced-motion treatment. Full keyboard, contrast, screen-reader and all-page accessibility certification remains open. |
| G-006 public route/SEO policy | PARTIAL | Added `/pricing` with live published catalogue data, loading/error/retry/empty states. Only the filtered catalogue is anonymous; private billing, checkout, receipts and learning routes retain guards. Dynamic and static sitemaps include only `/` and `/pricing`, excluding private tests/courses and nonexistent FAQ. Private navigation clears landing JSON-LD and uses noindex; password-reset metadata has a safe canonical without its token. Server-rendered product metadata and production crawl validation remain open. |
| Center administrator privileges | FIXED | Frontend incorrectly counted `center_admin` as a global platform administrator despite the backend excluding it. Aligned the policy and sent center admins to the existing scoped enterprise UI. Backend permission enforcement remains unchanged. |
| Teacher live controls | FIXED | Removed hardcoded `MOCK-42`, Chemistry class label, leaderboard test ID `1`, unsupported `/pin` and `/test/:id` QR routes. Live controls require an actual created test and use its returned ID, title and access code; web QR uses `/tests/:id`. Existing-test selection and configured Telegram share links need separate work. |

## Files and review areas

- Study plan persistence: `apps/accounts/{views,serializers}.py`, `frontend/src/lib/api.ts`, `pages/Onboarding.tsx`, `components/{GoalModal,OnboardingModal}.tsx`.
- Dashboard/roles: `apps/webapi/views_dashboard.py`, `pages/{Dashboard,DashboardRouter,TeacherDashboard}.tsx`, `lib/dashboardMetrics.ts`, `styles/dashboard.css`.
- Public catalogue and metadata: `apps/webapi/views_billing.py`, `apps/core/views_seo.py`, `frontend/public/sitemap.xml`, `App.tsx`, `auth/AuthContext.tsx`, `components/SEO.tsx`, `pages/{PublicPlans,PasswordReset,PasswordResetConfirm}.tsx`.
- Translation dictionary, focused backend regressions, dashboard/SEO tests, UI logic regression, Playwright config/suite, lockfile and CI browser job. Browser tooling is a development dependency only.

## Reproducible verification

Use Python 3.13 in `.venv`, Node 24, and the existing isolated checkout. Never target production databases.

```sh
.venv/bin/ruff check .
DJANGO_SETTINGS_MODULE=config.settings.development .venv/bin/python manage.py check
.venv/bin/pytest tests -q
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend test
cd frontend
PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e
```

Without system Chromium, run `npx playwright install --with-deps chromium` and omit the executable override. CI installs Playwright Chromium itself. Browser route tests use isolated API fixtures and no paid services; a separate real local Django/Chromium smoke verified registration, password login, onboarding dismissal, logout and protected-route redirection with no page exceptions. The only accounts created by that smoke are in the local development SQLite database.

The initial full pytest run had 1,682 passes, two PostgreSQL skips, and one translation-key failure introduced by the new metadata. Reusing existing translation keys fixed that failure; **final full pytest run: 1,683 passed, 2 skipped** (the skipped races also passed on PostgreSQL). Final frontend checks passed: frozen install, production build/typecheck, lint and **24 UI logic tests**. The final Playwright run passed **17 tests** in 1.6 minutes. The dedicated translation suite passed all six tests after correction.

A separate local PostgreSQL 16 container on loopback port 55432 ran `tests/test_essay_async_grading.py` and `tests/test_subscription_usage_quota.py` with `config.settings.postgres_test`: **59 passed**, including nullable-topic row-lock grading and simultaneous last-allowance reservation. SQLite alone cannot verify those races. The temporary test container is removed after validation.

Playwright covers guest direct/client navigation, rejected/timeout/duplicate/retried onboarding, profile restoration, legacy local flags, empty/failed dashboards, goal-save rejection/retry, scoped center/student route guards, teacher empty state and live controls, and a stale lazy module. Dashboard geometry is checked at 320, 375, 390, 768, 1024, 1440 and 1920 pixels in both themes. Screenshots are generated at 375, 1440 and 1920 pixels under `frontend/test-results/`; CI retains browser artifacts for seven days. No before-dashboard screenshot was captured, and these fixture screenshots are not evidence about production accounts.

Initial parallel browser runs encountered 5-second assertion timeouts while pytest, builds and PostgreSQL setup competed for CPU. The final configuration uses one browser worker, a 15-second assertion timeout, and a 60-second test timeout. No application assertions were removed. Incorrect initial API fixtures/selectors and Vite timestamp matching were corrected rather than changing application logic to satisfy those tests.

## Remaining scope and external blockers

- OPEN: complete role dashboard redesign, all-page UI/i18n modernization, full accessibility audit, browser exam authoring/execution matrix, real-device/Telegram QA and measured performance budgets.
- PARTIAL: broad exam, AI, quota, auth and payment coverage comes from the repository's existing backend suite. This does not establish production provider health, live payment processing, every official scoring rubric, or all browser workflows. No official score was invented or scoring contract changed.
- BLOCKED: GitHub GraphQL and REST calls currently receive a proxy CONNECT 403 for `api.github.com`. Git fetch works. The missing API hostname was saved as an additive environment draft network rule, preserving package-manager presets. Runtime access must be applied through environment settings before PR creation/unmerged-PR inspection/Actions inspection can be completed. No GitHub token was requested or exposed.
- No merge or deployment is authorized or performed. Saved environment settings are not publication or deployment.

## Bundle observation

The entry JS measured 622.48 kB (180.77 kB gzip) before these changes and 625.06 kB (181.57 kB gzip) after. This release does not claim a payload reduction. Playwright is a development-only dependency; broader runtime payload/waterfall optimization remains open.
