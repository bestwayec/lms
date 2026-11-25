# Staging & Pre-Production Readiness Guide

This guide documents how to enable automated staging deploys and verify release artifacts safely before manual production approval.

## 1. GitHub `staging` Environment Setup

Create the `staging` environment in GitHub **Settings → Environments → New environment (`staging`)** and configure:

| Secret | Required | Purpose |
| --- | --- | --- |
| `STAGING_HOST` | Yes | Staging VPS IP or hostname |
| `STAGING_USER` | Yes | SSH user (e.g. `deploy`) |
| `STAGING_SSH_KEY` | Yes | Base64-encoded private SSH key for `STAGING_HOST` |
| `STAGING_SSH_PORT` | Optional | SSH port (defaults to `22`) |
| `STAGING_DOMAIN` | Yes | TLS domain served by Nginx on staging (e.g. `staging.grandec.uz`) |
| `GHCR_USER` | Yes | GitHub username with `read:packages` |
| `GHCR_READ_TOKEN` | Yes | Token with `read:packages` to pull GHCR images |
| `OPENROUTER_API_KEY` | Optional | OpenRouter key synced to `.env.prod` |

When `STAGING_HOST` and `STAGING_DOMAIN` are unset, the `staging` job in `.github/workflows/deploy.yml` logs a warning and exits cleanly without touching any host.

## 2. Automated Staging Pipeline Flow

`CI` → `Release` (commits `VERSION`, tags `vX.Y.Z`) → `Build` (pushes `sha-<rev>`, `vX.Y.Z`, `latest` + `build-meta`) → `Deploy (staging)` → `deploy/scripts/smoke_test.sh "https://${STAGING_DOMAIN}"`.

## 3. Pre-Deploy Backup, Migration & Rollback Safeguards

`deploy/ci-ssh-deploy.sh` + `deploy/remote-deploy.sh` execute identically on staging and production:

1. **Pre-deploy DB backup**: `deploy/scripts/backup_db.sh /opt/backups/lms/pre-deploy` fails closed unless `pg_dump`, `gzip -t`, min size, and min table count all pass.
2. **Migration preview**: `python manage.py showmigrations --plan` lists pending migrations prior to service restart.
3. **Zero-downtime container rollout**: Pulls immutable `sha-xxxxxxx` tag, restarts `web`, `celery-worker`, `celery-beat`, `bot`, self-heals Nginx bind-mount inodes if needed, and runs `nginx -s reload`.
4. **Post-deploy verification**: Checks `http://127.0.0.1:8000/healthz/`, `manage.py migrate --check`, `manage.py check --deploy`, public `https://${DEPLOY_DOMAIN}/healthz/`, and `smoke_test.sh` (including `404` checks on `/media/receipts/`, `/media/speaking/audio/`, and `/media/essays/audio/`).
5. **Rollback**: Run **Deploy → workflow_dispatch** with the previous immutable tag stored in `/opt/lms/.last_good_tag` (and restore the pre-deploy backup in `/opt/backups/lms/pre-deploy` if a migration must be reverted).
