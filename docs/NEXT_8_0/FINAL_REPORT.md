# GRANDEC NEXT 8.0 — Final Release Readiness Report

## 1. Executive Summary
GRANDEC NEXT 8.0 upgrades the platform with a unified English Learning Center, BESTWAY Schema 1.0 Exam Builder, Reliable Exam Engine 2.0, Range-safe Listening Engine, Stimulus-isolated Reading Engine, Writing Studio 3.0 & Grounded AI Assessment, Speaking AI 3.0, separate IELTS Academic/General and UZBMB Multilevel v2 Full Mocks, PronunciationEngine + Vocabulary & Grammar Studios, Separated Teacher English Workspace & Formula-Safe Exports, Telegram English Center, and Admin AI Cost Control — while preserving 100% of existing Uzbek essay, National Certificate, Biology, Chemistry, Law, billing, and NEXT 7.0 security guarantees.

## 2. Phase 00–15 Status
All 16 phases (Phase 00 through Phase 15) are complete and verified (`PASS`):
- Backend SQLite suite: **2054 passed, 14 skipped, 0 failed**.
- Real PostgreSQL 17.11 NEXT 8.0 + row-lock suite: **162 passed, 0 failed, 0 skipped**.
- Ruff + Oxlint + TypeScript + Vite build (`7.07s`) + Node unit suite (`34/34`): **PASS**.
- Real Chromium Playwright E2E across 6 viewports (`360px`–`1920px`) in Light & Dark themes with 0 console/page/5xx errors: **PASS**.

## 3. Confirmed Regression Fixes Applied
- Fixed `N8-001` (`ReportViolationView` `Result` lookup) and `N8-002` (canonical question type serialization).
- Fixed `N8-003` (`EssayStudio` IELTS/Multilevel payload contract & removed hardcoded fake band fallbacks).
- Fixed `N8-004` (widened `TeacherReview.final_score` max to 75 and supported IELTS `/9` & Multilevel `/16`/`/75` rubrics).
- Fixed `N8-005` (bounded audio duration check, async evaluation, honest nullable `pronunciation_score`, and privacy-gated teacher review).
- Fixed legacy generic `raw_to_ielts_band` compatibility when `section` is omitted vs separate Listening / Academic Reading / General Reading scales.
- Fixed translation parity across `uz`, `ru`, and `en` for all newly introduced UI keys.

## 4. Additive Migrations Summary
- `accounts/0027_profile_english_track.py`
- `tests/0025_attempt_reliability_fields.py`
- `tests/0026_builder_schema_fields.py`
- `essays/0024_writing_studio_and_review_scale.py`
- `speaking/0002_speaking_ai_3_0.py`
- `vocabulary/0002_vocabulary_and_grammar_studio.py`

## 5. Limitations & Verification Scope
- Automated tests verify AI providers using mocked responses + explicit fault/unavailable paths + `ESSAY_AI_MOCK_MODE=True` where explicitly requested; live paid OpenRouter / Gemini model accuracy against external human examiners was not queried in CI.
- Telegram Bot & TMA flows were verified via Django integration tests and simulated browser Playwright requests against `/tma` (not physical mobile Telegram clients).

## 6. Release Gate
- **Merge readiness (PR Review & CI):** YES (pending final GitHub Actions CI run on Draft PR).
- **Direct auto-merge / production deployment:** NO (manual owner approval & VPS rollout required).
