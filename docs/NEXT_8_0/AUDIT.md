# GRANDEC NEXT 8.0 — Full Audit & Baseline Verification (Phase 00)

- **Branch:** `feat/grandec-next-8-0-english-learning`
- **GRANDEC Baseline:** `main @ 5db1a432294d3d29bba592f49d1b604862b94be1` (Release `v2.12.0`, PR #151 merged; GHCR image `sha-5db1a43`)
- **BESTWAY Reference Checkpoint (Read-Only):** `67b92f5419e0bf9e95f2a16852019aef3c72659e` (PR #226 merged)

---

## 1. Production & Verification Baseline

- **CI / Automated Baseline:** PR #151 merged cleanly into `main`; post-merge `Security`, `CI` (Lint, Nginx Private-Media, Browser Regressions, PostgreSQL Tests, Pytest & Django + Coverage, Build), `Release` (`v2.12.0`), and `Build` all passed (`2030` local backend tests, `34` frontend unit tests, `41/41` Chromium Playwright E2E scenarios).
- **Outstanding NEXT 7.0 Manual Verification:** Production deployment of `v2.12.0` (`sha-5db1a43`) awaits owner manual `workflow_dispatch`; physical Telegram Android/iOS WebView verification against live `@uz_essaygrader_bot` remains outstanding and is tracked separately without blocking local/CI engineering progress.

---

## 2. GRANDEC Domain & Codebase Audit

### 2.1 Existing Reusable Strengths (Preserved Intact)
- **Exam Models (`apps/tests/models.py`):** Already has `Test` (with `subject`, `exam_type`, `assessment_category`), `ExamSection`, `ReadingPassage`, `ExamPart`, `QuestionGroup`, `Question` (including `evidence`, `explanation`, `explanation_status`, `config`), `Choice`, `TestAttempt` (with `mode`, `trial_part`, `section_scores`, `STATUS_TRANSITIONS`), `StudentAnswer`, `GapBlank`/`GapResponse`, `MatchingPrompt`/`MatchingOption`/`MatchingPair`, `AttemptSectionProgress`, `ExamWrittenBridge`, and `ExamScoringProfile`.
- **CEFR & CBT Engines (`apps/tests/`):** `cefr_multilevel.py` + `scales/cefr_multilevel.json`, `bmb_grading.py`, `rasch_engine.py`, `score_converter.py`, `studio_service.py`, `EnglishExamInterface.tsx` + `CdExamInterface.tsx` + `cdAdapter.ts`.
- **Essays (`apps/essays/`):** Async Celery/thread grading (`start_grading`), single-flight/lease-locked `EssayGradingCache` (`schema v2`), BMB 12-criterion (20-pt) & IELTS 4-criterion (`ielts_task1`/`ielts_task2`) rubrics, `EssayRewriteCache`, appeals & teacher review (`TeacherReview` with private `voice_feedback`).
- **Speaking (`apps/speaking/`):** `SpeakingTopic` (`part1`, `part2`, `part3`, `multilevel`) & `SpeakingSubmission` (private audio file, transcript, 4 criteria, overall band, feedback JSON).
- **Vocabulary & Games (`apps/vocabulary/`, `apps/games/`):** `VocabularyPack` (4 JSON exercise sets), `StudentWordMistake` (spaced repetition Ebbinghaus schedule), shared XP/coins/streaks/badges engine.
- **Role Shells & Telegram (`apps/accounts/`, `apps/telegram_app/`, `apps/notifications/bot/`):** Role-separated Admin/Teacher/Student/Parent workspaces, TMA HMAC-SHA256 `initData` + CSRF cookie issuance, RBAC-guarded bot callbacks.

### 2.2 Confirmed Audit Gaps & Defects Targeted in NEXT 8.0
1. **`ReportViolationView` `AttributeError` (`apps/tests/views.py`):** `SubmitAttemptService.execute()` returns `AttemptResult` (`.attempt_id`, not `.id`), breaking 3rd-strike auto-submit `result_id`.
2. **Canonical Question Type Serialization Gap (`apps/tests/serializers.py`, `TakeTest.tsx`, `cdAdapter.ts`):** `_student_question_payload()` only populates structured `gaps`/`matching`/`written` payloads for lowercase legacy types (`gap_fill`, `matching`, `written`), dropping payloads for uppercase `INLINE_GAP_FILL`, `MATCHING`, `HEADING_MATCHING`, `MAP_LABELING`, `SPEAKING_PROMPT`.
3. **Exam Reliability 2.0 Missing Contracts (`TestAttempt`, `SaveAnswerService`, `SubmitAttemptService`, `views.py`):** Missing monotonic answer revision numbers, client/server save-receipts & ack states (`unsaved`/`saving`/`saved`/`offline`/`retrying`/`conflict`/`submitted`), lease/session takeover lock (`active_session_token` / device conflict), server-authoritative Listening part playback window schedule (`media_state` + range fetch non-counting), and HTTP/DB attempt snapshot consistency.
4. **English Learning Center & Student Track Persistence Missing:** No persisted student English learning track (`ielts_academic` / `ielts_general` / `cefr_multilevel` / `general_english`), target score/band, or unified compact English Learning Hub combining Listening/Reading/Writing/Speaking/Vocabulary/Grammar/Mocks/Mistakes/Progress without leaking into Admin nav.
5. **`EssayStudio.tsx` Contract Mismatch & Synchronous HTTP Grading:** `EssayStudio.tsx` ignores `:topicId`, uses static defaults, and expects `{ criteria: { task_response: ... }, general_feedback }` while `views_essays.py:ielts_grade_view` returns list `criteria: [...]` synchronously inside HTTP POST.
6. **Teacher Review Scale & English Support Gap (`apps/essays/models.py`, `views_essays.py`, `EssayTeacherReview.tsx`):** `TeacherReview.final_score` validator still allows `24` (residue from old 24-pt rubric), and teacher review endpoints hardcode 12 BMB Uzbek criteria (blocking teacher review/override of English IELTS 4-criterion essays).
7. **Speaking AI 3.0 Gaps (`apps/speaking/`, `CdExamInterface.tsx`, `TestAttempt`):** `SpeakingSubmitView` runs STT + LLM synchronously in the HTTP request; no server-side decoded audio duration check (`wave`/container probe) preventing empty/short/spoofed recordings; no Multilevel 0–75 rubric; no async retry/recovery; no teacher speaking review queue; `CdExamInterface.tsx` SpeakingPrompt is timer-only with no recording or upload.
8. **CBT Reading & Listening Engine Gaps:** Missing BESTWAY `stimulusRef` identity handling (identical passage texts across numbered groups), server-authoritative Listening preview + play schedule, Reading highlighting/notes/bookmarks recovery, and official IELTS Academic vs General Training vs UZBMB Multilevel v2 scoring differentiation.
9. **Vocabulary & Grammar Gaps (`apps/vocabulary/`):** `spaced_repetition_quiz_view` uses hardcoded generic distractors; no browser/stored pronunciation engine (`PronounceButton`, two plays with pause, autoplay safety, never leaking word answers); no structured Grammar Studio (tenses, SVA, articles, prepositions, passive, conditionals, relative clauses, linking words) linked to Writing/Speaking errors.
10. **Exam Builder 3.0 & BESTWAY JSON Schema 1.0 Compatibility Missing:** SmartTestCreate and TeacherStudio lack unified track->skills->structure->validation->publish flow, BESTWAY `schemaVersion: "1.0"` JSON package import/export + keyless template export + atomic draft validation, undo/redo in editor, and completeness gates before publishing Full Mocks.
