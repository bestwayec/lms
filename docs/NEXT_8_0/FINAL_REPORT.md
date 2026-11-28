# GRANDEC NEXT 8.0 — Final Release Readiness Report

## 1. Executive Summary
GRANDEC NEXT 8.0 delivers the complete English Learning Center, Schema 1.0 Exam Builder, Reliable Exam Engine 2.0, Range-safe Listening Engine, Stimulus-isolated Reading Engine, Writing Studio 3.0 & Grounded AI Assessment, Speaking AI 3.0 (with `av` container decoding & honest incomplete-band deferral), IELTS Academic/General & CEFR Multilevel v2 4-skill Full Mocks, PronunciationEngine + Vocabulary & Grammar Studios, Teacher English Workspace (`CSV`/`XLSX`/`PDF` exports & separated analytics), Telegram `/english` + TMA card, and Admin AI Cost Control — while preserving existing Uzbek essay, National Certificate, Biology, Chemistry, Law, billing, and NEXT 7.0 security guarantees.

## 2. Independent Audit & Verification Summary
- **Backend Full SQLite Suite (`task-8495`)**: **`2058 passed, 14 skipped, 272 subtests passed` (`0 failed`)** in `192.60s`.
- **Backend Real PostgreSQL 17.11 Suite (`task-8519`)**: **`247 passed, 0 failed, 0 skipped`** in `229.37s` (covering all 13 PostgreSQL row-lock tests + NEXT 8.0 + studio/essay/evidence suites).
- **Static & Migration Checks**: `ruff check .` (`All checks passed!`), `manage.py check` (`0` issues), `makemigrations --check --dry-run` (`No changes detected`).
- **Frontend Final Build & Tests (`task-8514`)**: `oxlint src` (`0 warnings, 0 errors`), `npm test` (`34 passed, 0 failed`), `tsc -b && vite build` (`3194 modules`, `2.62s`, `0` errors).
- **Live Chromium Playwright E2E (`task-8528`)**: Verified **IELTS Academic**, **IELTS General Training**, and **CEFR Multilevel** full 4-skill exams (with Chromium fake-mic WebM/Opus capture -> upload -> PyAV probe -> Teacher review -> auto-finalize -> Gradebook & Certificate Card parity), Writing Studio Draft persistence, Speaking Practice, Vocab & Grammar, `0` overflows across `360..1920`, Dark Mode fixes, and **`0` console/page/5xx errors**.
- **PostgreSQL 17.11 Migration & Performance Audit**: `v2.12.0 -> NEXT 8.0` forward migration (`15.41s`, `data_preserved: true`), reverse migrations (`rc: 0`), `0` extra backend SQL queries (`11`/`16` vs `11`/`16`), and `+4.37 kB` gzip initial frontend entry delta.

## 3. Audit & Regression Fixes Completed
- `N8-001`..`N8-010`: Initial Phase 00–15 functional/contract fixes.
- `N8-AUD-01`..`N8-AUD-12`: Blueprint sources/Task 2 `2x` weight/timing disclosures, PyAV `av>=14.0,<20.0`, honest transcript-only Speaking deferral (`overall_band = None`), CBT `SpeakingPrompt` capture + `AttemptSpeakingUploadView` + `ExamBridgeService` scaling, `TEXT_MATCH` (`"text"`) rendering in `CdExamInterface.tsx`, Schema 1.0 package publish `audio_url` fix, Writing Studio 3.0 Draft/Highlighter/Teacher Review UI + repeated-quote disambiguation, Logout draft storage scrub, Vocab synonym fix, Dark Mode Admin & EnglishCenter contrast fixes, `.xlsx` export, and GHCR deployment guide alignment.

## 4. Additive Migrations Summary
- `accounts/0027_profile_english_track.py`
- `tests/0025_attempt_reliability_fields.py`
- `tests/0026_builder_schema_fields.py`
- `essays/0024_writing_studio_and_review_scale.py`
- `speaking/0002_speaking_ai_3_0.py`
- `vocabulary/0002_vocabulary_and_grammar_studio.py`

## 5. Honest Verification Boundaries & Limitations
- Live paid external LLM grading calls (OpenRouter / Gemini) were not invoked with paid API keys during automated runs; live AI-vs-human rater MAE must be monitored post-release via `/api/v1/panel/ai-metrics/`.
- Docker image build and Linux container `av` WebM/Opus decoding require GitHub Actions Ubuntu CI confirmation (`ci.yml` / `build.yml`) since Docker CLI is absent on this Windows workstation.
- Detailed audit findings and acceptance mapping live in `docs/NEXT_8_0/INDEPENDENT_AUDIT.md` and `docs/NEXT_8_0/FUNCTIONAL_ACCEPTANCE_MATRIX.md`.

## 6. Release Gate
- **PR Review & CI Gate:** Ready for review once GitHub Actions `CI` and `Security` workflows pass on the latest pushed HEAD.
- **Direct auto-merge / production deployment:** Prohibited without explicit owner approval and manual deployment trigger.
