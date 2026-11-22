# GRANDEC NEXT 3.0 — progress ledger

Single source of truth for resuming work. Update after every substantial change. Only facts that were executed are recorded as passing.

Branch convention: stage work lands on dedicated branches off `origin/main`, each as a **draft** PR. Nothing is deployed or merged without owner approval.
Local tooling (not committed): venv from `requirements/development.txt`; disposable PostgreSQL 16 on `127.0.0.1:54329` for `config.settings.postgres_test`.

## How to reproduce the baseline

```bash
# backend, SQLite (fast feedback)
DJANGO_SETTINGS_MODULE=config.settings.test SECRET_KEY=x pytest -q
# backend, PostgreSQL (needs a disposable server; the DB name must start with lms_pg_)
DJANGO_SETTINGS_MODULE=config.settings.postgres_test POSTGRES_TEST_ENABLE=1 POSTGRES_TEST_NAME=lms_pg_dev \
  POSTGRES_TEST_USER=… POSTGRES_TEST_HOST=127.0.0.1 POSTGRES_TEST_PORT=5432 SECRET_KEY=x pytest -q
ruff check . && python manage.py check && python manage.py makemigrations --check --dry-run
cd frontend && npm ci && npm run lint && npm test && npm run build
CI=1 PLAYWRIGHT_CHROMIUM_EXECUTABLE=<chromium> npx playwright test --trace off   # (CI installs its own browser)
```

## Stage status

| Stage | Status | PR (all draft, none merged/deployed) |
|---|---|---|
| 0 Recover baseline | ✅ complete | #135 |
| 1 Security & data integrity | ✅ code complete for the confirmed defects; **owner actions + production-only checks remain** | #136 (private file access), #137 (nginx, not deployed), Stage 1c (below) |
| 3a Attendance concurrency | ✅ complete | commit ca0ad07 |
| 3b Group membership history & search authz | ✅ complete | branch `claude/stage3-attendance-concurrency` |
| 3c Teacher Workspace 3.0 | 🟡 in progress | branch `claude/stage3-attendance-concurrency` |
| 4–12 | not started | – |

Stacking: #135 ← #136 ← #137, and Stage 1c branches off #136. Merge in that order after review.

## Stage 0 — closure

Executed 2026-11-22 on the Stage 0 branch (`claude/confident-carson-3pxsj4`):

| Check | Result |
|---|---|
| pytest, SQLite (`config.settings.test`) | **1723 passed, 7 skipped** (7 = PostgreSQL-lock tests, skipped by design on SQLite), 0 failed |
| pytest, PostgreSQL 16.15 (`config.settings.postgres_test`) | **1730 passed, 0 failed, 0 skipped** (the 7 lock tests run and pass) |
| ruff / `manage.py check` / `makemigrations --check` | pass / pass / no changes |
| Frontend `npm test`, `tsc -b`, `npm run build`, Playwright (20) | pass (run in the previous session; frontend untouched since) |
| GitHub CI on #135 (before the closure commits) | Lint, Test, Build, Browser, security, automerge: all success |

Closure fixes: seed-command tests are settings-aware (success asserted only on local SQLite; on PostgreSQL they assert the safe refusal and that nothing was created); Channels JWT tests use `TransactionTestCase` (the middleware reads the user on a second DB connection, which cannot see a `TestCase` transaction on PostgreSQL); streaming-PDF test detaches `close_old_connections` for the explicit `resp.close()`; the essay test no longer passes by id coincidence (`"1" in "19.0/20"`); new CI job **`test-postgres`** selects `config.settings.postgres_test` explicitly against a `postgres:16` service. The new job has **not yet run on GitHub** — its first run is the verification.

PR #134 (enterprise-import credentials): open draft, 4 files, based on current main, CI state not re-checked here; not modified. Integration plan in Stage 1.

## Stage 1 — security & data integrity

Findings, evidence and status per item: `GRANDEC_NEXT_ARCHITECTURE.md` §7. Deployment plan for the file/nginx work: `docs/DEPLOY_PRIVATE_MEDIA.md`.

| Increment | Branch / PR | What | Verification (executed) |
|---|---|---|---|
| 1a private files (code) | `claude/stage1-private-files` · #136 | authenticated, object-checked downloads; hardened responses; API/admin no longer emit `/media/` URLs; frontend blob loading | SQLite 1738 passed / PostgreSQL 1745 passed (+15); Playwright 22 |
| 1b nginx | `claude/stage1-nginx-private-media` · #137 | deny `/media/{receipts,tuition/proofs,speaking/audio}`; internal accel location; `deploy/scripts/verify_private_media_nginx.sh` | real nginx 1.24 script PASSED; negative control fails |
| 1c authz & auth hardening | `claude/stage1-authz-hardening` | PIN lockout; test visibility + exam-content stripping; gradebook 500; Google token-in-URL; SPA URL tokens; CSRF on payment review; spreadsheet injection; cross-tenant probe suite | see "Stage 1c results" below |

### Stage 1c — defects found and fixed (each has a test that fails on the old code unless marked)

1. Anonymous read of a private group-only test's questions + catalogue title (S6a). 2. `group_assignments` → HTTP 500 in 3 views (S6b). 3. PIN brute force (S3). 4. JWTs in the Google redirect URL (S5a) and tokens accepted from the URL (S5b). 5. Receipt review without CSRF (S5c; fails on old code). 6. Formula injection ×3 exports (S8; all 3 fail on old code).

### Open items from Stage 1 (owner decisions / follow-ups)

* Merge + deploy order: #135 → #136 → deploy code → #137 → `nginx -t` → reload → (optional) `PRIVATE_MEDIA_ACCEL_PREFIX`. Treat previously public receipts/audio as exposed.
* **#134**: reviewed, tests green on both backends, merges cleanly. After it merges: update `EnterpriseDashboard.tsx:971` ("standard password Grand2026!") and surface `manual_setup_required`; rotate already-issued shared passwords via its documented ops procedure.
* S5d (JWT in `sessionStorage`), S5e (One Tap without nonce), S7 (public exam media): design decisions, unchanged.
* Not audited in Stage 1: see "Not covered" under §7 of the architecture doc.
* The `test-postgres` CI job has not yet run on GitHub.

## Stage 3b — closure (Group membership history & search authorization)

Executed 2026-11-22 on branch `claude/stage3-attendance-concurrency`:

| Check | Result |
|---|---|
| `pytest tests/test_stage3b_membership_history.py` (SQLite) | **8 passed, 1 skipped** (1 = PG-only lock test), 0 failed |
| Group & attendance regression suite (5 test modules) | **47 passed, 2 skipped**, 0 failed |
| `python manage.py check` & `makemigrations --check` | pass / no changes detected |
| Frontend `npm test`, `tsc -b`, `npm run lint`, `npm run build` | **24 passed, 0 errors, 0 lint warnings, built successfully** |

Delivered capabilities:
1. **`GroupMembershipHistory`**: Additive model tracking student, group, action (`JOINED`, `REMOVED`, `REJOINED`), joined/removed timestamps, authorized actor, reason, and metadata.
2. **Data Preservation**: Removing a student deactivates the membership interval and preserves all historical test attempts, exam results, essay submissions, and attendance logs without cascade deletion.
3. **Cross-Center Tenant Isolation**: Fixed `/api/v1/school/student-search/` and `/members/` views to prevent user enumeration, leaking exam/subscription counts, or adding students across center boundaries. Independent tutors are scoped to their existing students or invite codes.
4. **React Groups UI**: Added debounced scoped student search, member removal with preservation confirmations, group student results inspection, and full membership audit history with `uz`, `ru`, `en` translations.

## Blockers / owner decisions

* Production nginx change for S1 requires owner deployment approval.
* Real-Telegram and real-device checks need an authorized staging bot/environment.
