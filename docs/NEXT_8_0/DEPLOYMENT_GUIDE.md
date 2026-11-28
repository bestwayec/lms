# GRANDEC NEXT 8.0 — Production Deployment, Migration & Rollback Guide

## 1. Immutable CI/CD Release Architecture (Official Repository Procedure)
GRANDEC production deployments on `grandec.uz` NEVER build containers or run `docker compose build` directly on the VPS. Instead, deployments strictly use the repository's immutable image pipeline (`.github/workflows/ci.yml` -> `release.yml` -> `build.yml` -> `deploy.yml`):

1. **Merge & CI Verification (`main`)**:
   - All PR checks (`Lint`, `Test (Pytest & Django)`, `Test (PostgreSQL)`, `Build`, `Browser regressions`, `Nginx Private-Media Verification`, `Security`) must pass on `main`.
2. **Release & Immutable GHCR Build (`.github/workflows/build.yml`)**:
   - Produces immutable multi-stage Docker image `ghcr.io/bestwayec/lms:sha-<7char>` (and `:v<VERSION>`) containing the compiled Django backend (`daphne`, `pyav`/`av` for Opus/WebM/OGG/WAV audio verification, `openpyxl`, `reportlab`, `weasyprint`) and Vite-built SPA static assets (`/app/spa`).
   - Automatically verifies staging (if configured) before production is permitted.
3. **Manual Production Deployment (`.github/workflows/deploy.yml` -> `workflow_dispatch`)**:
   - Trigger **Deploy** workflow manually in GitHub Actions with:
     - `tag`: exact immutable `sha-xxxxxxx` tag produced by `Build`.
     - `confirm`: `deploy grandec.uz`
   - `deploy/ci-ssh-deploy.sh` & `deploy/remote-deploy.sh` execute on the VPS:
     - Regenerates live `deploy/nginx/nginx.conf` in-place (preserving bind-mount inodes).
     - Runs `./deploy/preflight.sh` and mandatory fail-closed database backup (`deploy/scripts/backup_db.sh /opt/backups/lms/pre-deploy`).
     - Pulls `web`, `celery-worker`, `celery-beat`, and `bot` images from GHCR (`docker compose --env-file .env.prod -f docker-compose.prod.yml pull ...`).
     - Inspects pending migrations read-only (`showmigrations --plan`).
     - Recreates services without touching volumes (`docker compose ... up -d` and `--force-recreate bot`), never running `docker compose down -v` or deleting persistent volumes.
     - Executes `deploy/scripts/smoke_test.sh https://grandec.uz` confirming HTTP `200 OK` on `/`, `/api/health/`, `/healthz/`, and updated SPA assets.

---

## 2. Environment & Worker Requirements
- **Production AI Mode**: Keep `ESSAY_AI_MOCK_MODE=False` in `.env.prod`.
- **AI Keys**: Configure `OPENROUTER_API_KEY` (and optional `GROQ_API_KEY` / `GEMINI_API_KEY` for STT multimodal fallback).
- **Async Workers & Broker**: Ensure `celery-worker`, `celery-beat`, and `redis` containers are healthy so Writing (`grade_essay_task`) and Speaking (`evaluate_speaking_submission_task`) tasks complete cleanly without blocking HTTP workers.
- **Audio Decoding**: `av` (PyAV `>=14.0,<20.0` with bundled `libopus`, `webm`, `ogg`) is declared in `requirements/base.txt`, included automatically inside the Docker wheelhouse (`Dockerfile` stage 1 -> stage 2).

---

## 3. Database Migrations (Additive Only — Zero Destructive Changes)
Six additive schema migrations are included from `v2.12.0`:
1. `accounts/0027_profile_english_track.py` (`english_track`, `target_band`, `target_cefr_level`)
2. `tests/0025_attempt_reliability_fields.py` (`last_revision`, `active_session_token`, `media_state`)
3. `tests/0026_builder_schema_fields.py` (`spec_version`, `is_keyless`, `stimulus_ref`, `content_layout`, `audio_play_limit`, `transcript`)
4. `essays/0024_writing_studio_and_review_scale.py` (widens `TeacherReview.final_score` `DecimalField` `max_digits=5`)
5. `speaking/0002_speaking_ai_3_0.py` (`decoded_duration_ms`, `audio_hash`, `is_verified_audio`, `track`, `rubric_version`, `task_scores`, `teacher_review_*`, nullable `pronunciation_score` & `overall_band`)
6. `vocabulary/0002_vocabulary_and_grammar_studio.py` (`GrammarCategory`, `GrammarExercise`, `GrammarAttempt`)

### Pre-Deploy Verification
- Inspect SQL & migration plan before rollout:
  ```bash
  python manage.py showmigrations --plan
  python manage.py migrate --noinput
  ```
- Forward migration from a `v2.12.0` database snapshot preserves 100% of existing users, courses, historical exam attempts, Uzbek essays, payments, and certificates.

---

## 4. Rollback Compatibility & Recovery Procedure
### Application-Level Rollback (`sha-xxxxxxx`)
- Initial NEXT 8.0 migrations add new columns with schema/Django defaults or nullability (`null=True`), and subsequent `DROP DEFAULT` operations are explicitly reversed by additive database-default compatibility migrations:
  - `accounts.0028_db_defaults_compat` (`english_track`, `target_cefr_level`)
  - `essays.0025_db_defaults_compat` (`stimulus_data`, `task_subtype`)
  - `speaking.0003_db_defaults_compat` (`audio_hash`, `is_verified_audio`, `rubric_version`, `task_scores`, `teacher_comments`, `teacher_review_requested`, `track`)
  - `tests.0027_db_defaults_compat` (all newly added non-nullable columns on `Test`, `ExamSection`, `ReadingPassage`, `ExamPart`, `QuestionGroup`, `Question`, `TestAttempt`, `StudentAnswer`)
- Because every newly added non-nullable column retains a metadata-only PostgreSQL SQL `DEFAULT`, both reads/updates AND raw `v2.12.0` `INSERT` statements omitting NEXT 8.0 columns remain forward-compatible against an upgraded database during rolling deploys or quick application container rollbacks (`tests/test_next8_release_safety.py`).
- **Standard Safe Rollback Rule**:
  1. Keep the mandatory pre-deploy backup in `/opt/backups/lms/pre-deploy/daily/*.sql.gz` as your full point-in-time recovery net before migrating.
  2. For quick application container rollback while retaining DB compatibility, deploy the previous `sha-<short>` tag via manual **Deploy** `workflow_dispatch`; to revert the schema cleanly back to `v2.12.0`, either restore the pre-deploy DB snapshot or run targeted reverse migrations (`python manage.py migrate <app> <previous_migration>`) BEFORE removing NEXT 8.0 schema dependencies.
