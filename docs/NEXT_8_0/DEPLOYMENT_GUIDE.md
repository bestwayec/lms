# GRANDEC NEXT 8.0 — Deployment & Recovery Guide

## Pre-Deployment Requirements
1. **Additive Migrations Only (Zero Destructive Changes)**:
   - `accounts/0027_profile_english_track.py`
   - `tests/0025_attempt_reliability_fields.py`
   - `tests/0026_builder_schema_fields.py`
   - `essays/0024_writing_studio_and_review_scale.py`
   - `speaking/0002_speaking_ai_3_0.py`
   - `vocabulary/0002_vocabulary_and_grammar_studio.py`
   Verify before rollout: `python manage.py showmigrations --plan` and `python manage.py migrate --noinput`.
2. **Environment Variables**:
   - Keep `ESSAY_AI_MOCK_MODE=False` in production.
   - Configure `OPENROUTER_API_KEY` / `DEEPSEEK_API_KEY` and optional `GEMINI_API_KEY` for STT multimodal fallback.
   - Ensure Celery worker & Redis broker are healthy so async Speaking (`evaluate_speaking_submission_task`) & Writing tasks drain cleanly.
3. **Zero-Downtime VPS Rollout Rules**:
   - Never run `docker compose down -v` or delete volumes.
   - Rebuild only updated services (`docker compose up -d --build web celery-worker frontend`).
   - Run static asset build (`cd frontend && npm run build`) and `collectstatic --noinput` before reload.
   - Confirm public HTTP `200 OK` on `/`, `/api/health`, and English endpoints (`/api/tests/english/blueprints/`).
