# GRANDEC NEXT 7.0 — Deployment & Verification Guide

- **Baseline Release Version in `VERSION`:** `2.11.0`
- **Target Branch:** `feat/grandec-next-7-0-platform-refinement` (submitted as Draft PR; **not** merged or deployed automatically)
- **Database Schema Impact:** `python manage.py makemigrations --check --dry-run` confirmed **zero new Django migrations**. Rollback does not require database schema down-migrations.

---

## Pre-Deployment Checklist

1. **Merge & CI Gate (GitHub)**
   - Ensure GitHub Actions `CI` (both SQLite and PostgreSQL test matrix, including the 13 skipped PG row-lock tests and Nginx private-media checks) and `Security` pass on the PR head commit.
   - Do not bypass branch protection rules or merge without repository owner approval.

2. **Container & Static Assets Build**
   - Build application image via release workflow so `frontend/dist` (`tsc -b && vite build`) and backend layers match the tagged commit (`VERSION == APP_VERSION`).
   - Run `python manage.py collectstatic --noinput` (handled cleanly inside container build/entrypoint).

3. **Zero-Downtime Server Rollout (`zero-downtime-vps-sync`)**
   - Keep PostgreSQL, Redis, Nginx, and persistent volumes untouched (never execute `docker compose down -v` or volume prunes).
   - Pull verified image tag/digest and perform service-level rollout (`docker compose up -d --no-deps <service>`).
   - Run `python manage.py migrate --check` / `python manage.py check --deploy` inside the backend container.

4. **Post-Deploy Live Smoke Verification**
   - Verify HTTP `200 OK` on `/` and health endpoints (`/api/health/`).
   - Verify unmatched `/api/does-not-exist` returns JSON `404` (not SPA HTML `200`).
   - Verify `/tma/` loads cleanly in Telegram Dark & Light themes without `403 CSRF Failed`.
   - Confirm `celery-worker` and `celery-beat` remain healthy if background essay tasks are queued.
