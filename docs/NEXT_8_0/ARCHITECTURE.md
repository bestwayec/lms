# GRANDEC NEXT 8.0 — Technical Architecture & Contracts

## 1. Non-Duplication Principle
GRANDEC already owns mature Django apps (`tests`, `essays`, `speaking`, `vocabulary`, `results`, `accounts`, `webapi`, `telegram_app`, `notifications`). NEXT 8.0 extends these apps in place with additive migrations rather than introducing parallel models or duplicate auth/exam tables:

1. **Tracks & Preferences (`apps/accounts/models.py`):**
   - `UserProfile` gains additive defaults:
     - `english_track`: `'ielts_academic' | 'ielts_general' | 'cefr_multilevel' | 'general_english'` (default `'ielts_academic'`)
     - `target_band`: nullable `DecimalField(3, 1)` (e.g. `7.5` for IELTS, or CEFR `B2`/`C1` via `target_cefr_level` CharField `'B2'`)
   - Admin accounts/workspaces (`is_platform_admin`) continue omitting student track/subject UI chrome (`shouldShowSubjectSwitcher`).

2. **Unified Exam Engine & Reliability 2.0 (`apps/tests/`):**
   - **Authoritative State (`TestAttempt`):** Adds `session_token` (active writer lease), `last_revision` (monotonic int), `content_version` (int snapshot lock on `Test`), `spec_version` (`IELTS_ACADEMIC_V1`, `IELTS_GENERAL_V1`, `UZBMB_MULTILEVEL_EN_2026_V2`, etc.), `section_deadlines` (JSON), `media_state` (JSON tracking server Listening schedules & play grants).
   - **Answer & Annotation Integrity (`StudentAnswer`):** Adds `revision` (monotonic int per attempt), `annotations` (JSON highlights/bookmarks/notes scoped cleanly per passage/question).
   - **Listening Media & Range Safety:** Private media endpoint (`/api/tests/<test_id>/media/<group_id>/`) streams byte-ranges cleanly (`206 Partial Content` / `Accept-Ranges: bytes`). Server Listening schedule (`/api/tests/attempts/<attempt_id>/listening/<group_id>/start/`) records `startedAt`, `readingEndsAt`, and `durationSec` inside `TestAttempt.media_state`, never consuming an extra play on Range requests.
   - **Schema 1.0 Import/Export (`apps/tests/package_service.py`):** Bidirectional adapter validating/importing/exporting BESTWAY `schemaVersion: "1.0"` JSON packages into `Test -> ExamSection -> ExamPart -> QuestionGroup -> ReadingPassage -> Question -> Choice/GapBlank/Matching*` transactionally (draft-first, key-free template export, owner/admin-only key export, HTML sanitization, readiness check blocking incomplete Full Mocks).

3. **Versioned English Blueprints & Honest Scoring (`apps/tests/blueprints.py`, `cefr_multilevel.py`, `scoring.py`):**
   - **Official Specifications Tracked:**
     - `IELTS_ACADEMIC_V1`: Listening (4 parts, 40Q, 30m+10m), Academic Reading (3 passages, 40Q, 60m), Writing (Task 1 report >=150w + Task 2 essay >=250w, weight 1:2, 60m), Speaking (Parts 1–3). Academic Reading band mapping (distinct from GT).
     - `IELTS_GENERAL_V1`: Same L/W/S structure with General Training Reading conversion table (30–31 = 6.0, 34–35 = 7.0, 40 = 9.0) & Writing Task 1 letter format.
     - `UZBMB_MULTILEVEL_EN_2026_V2`: Verified against UzBMB guidelines — Listening 6 parts / 35Q (45m), Reading 5 parts / 35Q (60m), Writing Task 1.1 informal (~50w, max 5) + Task 1.2 formal (120–150w, max 5) + Task 2 publication (180–200w, max 6) -> /16 (60m), Speaking Parts 1.1, 1.2, 2, 3 (max 5/5/5/6 -> /21). Standardized 75-pt practice estimate thresholds (`<38` below B1, `38–50` B1, `51–64` B2, `65–75` C1), explicitly marked `ESTIMATED` (`is_official=False`) unless verified Rasch item parameters exist.
   - Full Mock completion holds overall score as `pending_grading` until Writing and Speaking assessments finish (never returning misleading partial overall bands/scores as final).

4. **AI Provider Gateway, Writing Studio 3.0 & Speaking AI 3.0 (`apps/core/ai_gateway.py`, `apps/essays/`, `apps/speaking/`):**
   - Single centralized AI adapter supporting OpenRouter/Gemini calls with circuit breaker, bounded exponential retry, strict schema validation, character-offset evidence verification (must match submitted text), and `AICallLog` cost/token accounting (`apps/core/models.py`).
   - Zero silent mock/zero score fallbacks on provider failure: failed runs transition cleanly to `error` / `pending_teacher` with honest retry / teacher fallback UI.
   - **Speaking Audio Pipeline:** Bounded subprocess WAV/PyAV decoder (`apps/speaking/audio_verify.py`) computes true `decoded_duration_ms`, detects silent/corrupt/short blobs, separates STT transcript from grading, and never invents acoustic Pronunciation scores when only transcript is available (leaves `pronunciation_score = None` / flags teacher review if acoustic analysis is unavailable).
   - **Teacher Review Parity:** `EssayTeacherReview` supports BOTH Uzbek BMB 12-criterion (`/20`) and English IELTS 4-criterion (`Band 0–9`) + Multilevel (`5/5/6` & `/75`) submissions; Speaking adds teacher review & score override.

5. **Vocabulary Pronunciation Engine & Grammar Studio (`apps/vocabulary/`, `frontend/src/lib/pronunciation/`):**
   - Shared `PronunciationEngine` (`audioUrl` -> browser `speechSynthesis` fallback, 2 sequential plays with 650 ms pause, slow 0.75x/0.6x speed, owner-scoped cancellation, autoplay-blocked tap prompt).
   - Grammar Studio models (`GrammarTopic`, `GrammarExercise`, `GrammarAttempt`) across 10 core English grammar areas (`tenses`, `subject_verb_agreement`, `articles`, `prepositions`, `passive_voice`, `sentence_structure`, `conditionals`, `relative_clauses`, `linking_words`, `academic_grammar`), linked directly from verified Writing/Speaking mistake categories.
