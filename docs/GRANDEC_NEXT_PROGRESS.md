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

| Stage | Status | PR | Evidence |
|---|---|---|---|
| 0 Recover baseline | ✅ complete | #135 (draft) | below |
| 1 Security & data integrity | in progress | – | below |
| 2–12 | not started | – | – |

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

## Stage 1 — security & data integrity (in progress)

See the findings table in `GRANDEC_NEXT_ARCHITECTURE.md` §7 (S1–S6). Order of work:
1. S1 private files: authenticated downloads (code PR) → nginx/deploy config (separate PR, not deployed).
2. S3/S6 negative authorization tests (PIN throttling, draft exams, cross-center).
3. S5 JWT/CSRF/Google OAuth review.
4. #134 review.

## Blockers / owner decisions

* Production nginx change for S1 requires owner deployment approval.
* Real-Telegram and real-device checks need an authorized staging bot/environment.
