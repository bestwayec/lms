# GRANDEC NEXT 8.0 — Release Notes

**Target Milestone:** GRANDEC NEXT 8.0 (English Learning, Premium UI/UX & AI Assessment Platform)
**Branch:** `feat/grandec-next-8-0-english-learning`
**Baseline:** `v2.12.0` (`main @ 5db1a432294d3d29bba592f49d1b604862b94be1`)

## Highlights
- **English Learning Center (`/english`)**: Persistent track preferences (`IELTS Academic`, `IELTS General Training`, `CEFR Multi-level`, `General English`) and target scores alongside unified skill shortcuts.
- **Exam Engine Reliability 2.0**: Monotonic answer revisions (`409 STALE_REVISION`), active-session lease takeover (`session-takeover/`), idempotent submit, 7-state sync badge, and fixed `ReportViolationView` & canonical question types (`N8-001`, `N8-002`).
- **Exam Builder 3.0 & Listening/Reading Engines**: Schema 1.0 JSON import/export/keyless templates, mock readiness gates, HTTP `206 Range` audio streaming with non-counting range fetches, `stimulusRef` passage separation (`EX4-402`), highlights/notes/bookmarks recovery, and post-review evidence display.
- **Writing Studio 3.0 & Essay Assessment 3.0**: IELTS Ac/GT + BMB Multilevel v2 tasks (`1.1`, `1.2`, `2`), shared `ai_gateway.py` with character-offset quote grounding and insufficient-text refusal, and unified multi-rubric Teacher Review (`/9`, `/16`, `/20`).
- **Speaking AI 3.0**: Bounded WAV/container duration verification (`audio_verify.py`), async Celery evaluation, honest unmeasured pronunciation (`None`), Multilevel `/75` conversion, and privacy-preserving teacher review workflow.
- **IELTS Ac/GT & CEFR Multilevel v2 Full Mocks**: Separate Academic vs General Reading conversion tables, `UZBMB_MULTILEVEL_EN_2026_V2` (`5/5/6` Writing, `5/5/5/6` Speaking), `ONE_WORD` / `ONE_WORD_AND_OR_NUMBER` rules, and strict pending-overall protection.
- **Vocabulary & Grammar Studios (`/vocabulary`, `/grammar`)**: Shared `PronunciationEngine` (2 sequential plays, 650 ms pause, slow mode, Web Speech fallback), answer-safe vocabulary quizzes, and 10 seeded English Grammar topics linked to recent Essay/Speaking mistakes.
- **Teacher English Workspace (`/teacher/english`) & Telegram Center**: Unified grading inbox, separated IELTS vs Multilevel cohort analytics, formula-safe CSV + paginated ReportLab PDF exports, `/english` Telegram Bot command, `/tma/api/english/` hub, and Admin AI Cost Control panel.
