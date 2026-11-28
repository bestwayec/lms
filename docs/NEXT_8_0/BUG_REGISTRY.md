# GRANDEC NEXT 8.0 — Audit Bug & Gap Registry

## Initial Implementation Audit (`N8-001`..`N8-010`)

| ID | Severity | Component | Description | Target Phase | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **N8-001** | Critical | `apps/tests/views.py:ReportViolationView` | Accesses `result.id` on `AttemptResult` dataclass (`attempt_id` is the field name), raising `AttributeError` on 3rd-strike anti-cheat closeout. | Phase 02 | RESOLVED |
| **N8-002** | High | `apps/tests/serializers.py` & `frontend/src/pages/TakeTest.tsx` | `_student_question_payload()` & runner omitted structured payloads for canonical uppercase `QuestionType` values. | Phase 02 / 05 | RESOLVED |
| **N8-003** | High | `apps/webapi/views_essays.py` & `frontend/src/pages/EssayStudio.tsx` | `EssayStudio.tsx` ignored `:topicId`, used static fallback scores, and mismatched backend IELTS payload contract. | Phase 06 / 07 | RESOLVED |
| **N8-004** | High | `apps/essays/models.py`, `views_essays.py`, `EssayTeacherReview.tsx` | `TeacherReview.final_score` capped at `24` while English/Multilevel needed `/9`, `/16`, and `/75`. | Phase 07 / 12 | RESOLVED |
| **N8-005** | High | `apps/speaking/views.py`, `services.py`, `CdExamInterface.tsx` | Missing bounded audio duration validation, async Celery evaluation, Multilevel rubric, teacher review, and CBT speaking upload. | Phase 08 / 09 / 10 | RESOLVED |
| **N8-006** | High | `apps/tests/` (Reliability & Media) | Missing monotonic answer revisions, 7-state sync pill, session takeover lock, and Range-safe Listening playback schedules. | Phase 02 / 04 | RESOLVED |
| **N8-007** | Medium | `apps/tests/blueprints.py`, `cefr_multilevel.py`, `scoring.py` | Missing separation of IELTS Academic vs General Reading conversion tables, `UZBMB_MULTILEVEL_EN_2026_V2` lookup tables, and pending-overall hold. | Phase 09 / 10 | RESOLVED |
| **N8-008** | Medium | `apps/vocabulary/views.py`, `quiz_engine.py` | Vocabulary quiz used static generic distractors and lacked pronunciation engine, answer-safe quiz types, and Grammar Studio mastery tracking. | Phase 11 | RESOLVED |
| **N8-009** | Medium | `apps/tests/ai_converter.py`, `apps/core/ai_gateway.py` | Needed centralized circuit breaker, token/cost telemetry, and consistent `google.genai` SDK usage. | Phase 14 | RESOLVED |
| **N8-010** | Medium | `apps/tests/package_service.py` | Needed Schema 1.0 JSON exam package import/export, keyless template stripping, `stimulusRef` isolation (`EX4-402`), and mock readiness gates. | Phase 03 | RESOLVED |

## Independent Release Audit Findings (`N8-AUD-01`..`N8-AUD-12`)

| ID | Severity | Component | Description | Status |
| :--- | :--- | :--- | :--- | :--- |
| **N8-AUD-01** | Medium | `apps/tests/blueprints.py` | Lacked official URL/date citations, `audio_plays` (`1` vs `2`), Task 2 `2x` Writing weighting, and Multilevel 30m speaking buffer disclosure. | RESOLVED |
| **N8-AUD-02** | High | `requirements/base.txt`, `apps/speaking/audio_verify.py` | Missing `av` (PyAV) runtime dependency and container decoding for browser `.webm`/`.ogg`/`.mp3`/`.m4a` uploads when `strict_decode=False`. | RESOLVED |
| **N8-AUD-03** | High | `apps/speaking/services.py`, `SpeakingResult.tsx` | Partial transcript-only speaking results (`pronunciation_score=None`) stored 3-criterion mean in `overall_band` and displayed `"Rasmiy baholash"`. | RESOLVED |
| **N8-AUD-04** | Critical | `CdExamInterface.tsx`, `apps/tests/views.py`, `services.py`, `speaking/services.py`, `essays/services.py` | CBT `SpeakingPrompt` recorded locally only; missing `AttemptSpeakingUploadView`, `ExamBridgeService` `/9` & `/16` scaling, and sync finalization extraction for dict-valued `speaking_submissions`. | RESOLVED |
| **N8-AUD-05** | High | `apps/tests/views.py` | `TestGradebookView` omitted `PENDING_GRADING` attempts and band/CEFR section fields; `CertificateCardView` omitted top-level `grading_status`/`cefr_level` on `cefr_multilevel`. | RESOLVED |
| **N8-AUD-06** | Critical | `frontend/src/pages/tests/CdExamInterface.tsx` | `renderQuestion` only matched `INLINE_GAP_FILL` / lowercase `"written"` / uppercase `"SPEAKING_PROMPT"`, failing to render `QuestionType.TEXT_MATCH` (`"text"`) text inputs. | RESOLVED |
| **N8-AUD-07** | High | `apps/tests/studio_service.py` | Schema 1.0 imported full mocks with `section.audio_url` passed `/readiness/` yet failed `/publish/` (`400 audio_missing`) and lost `[n:alts]` gap markers in `load_blocks`. | RESOLVED |
| **N8-AUD-08** | High | `apps/core/ai_gateway.py`, `views_essays.py`, `EssayStudio.tsx` | Repeated phrase grounding picked first occurrence; Writing Studio lacked Draft Save/Restore endpoints, Ac/GT task switchers, grounded inline highlighter, vocab upgrades, next-level examples, and Teacher escalation CTA. | RESOLVED |
| **N8-AUD-09** | Medium | `frontend/src/lib/api.ts` | `clearTokens()` retained `cd-exam:*` / `writing_studio_draft_*` storage entries across logout on shared browsers. | RESOLVED |
| **N8-AUD-10** | Medium | `apps/vocabulary/quiz_engine.py`, `views.py`, `VocabularyStudio.tsx` | `synonym` questions were omitted when earlier entries lacked context sentences, and submit skipped `token` lookup + updated counts + TS fields. | RESOLVED |
| **N8-AUD-11** | High | `frontend/src/theme.css`, `EnglishCenter.tsx`, `SpeakingPractice.tsx` | Dark Mode Admin `.admin-action` cards rendered white; `360px` search overlapped magnifier icon; `/english` `Qidirish` and inactive Study Mode buttons rendered white-on-white in Dark mode; Speaking prep text had low contrast on dark card. | RESOLVED |
| **N8-AUD-12** | Medium | `DEPLOYMENT_GUIDE.md`, `views_teacher_english.py`, `TeacherEnglishWorkspace.tsx` | Deployment guide referenced `git pull` instead of immutable GHCR + `workflow_dispatch`; Teacher export lacked `.xlsx` format. | RESOLVED |
