# GRANDEC NEXT 8.0 — Release Notes

**Target Milestone:** GRANDEC NEXT 8.0 (English Learning, Premium UI/UX & AI Assessment Platform)
**Branch:** `feat/grandec-next-8-0-english-learning`
**Baseline:** `v2.12.0` (`main @ 5db1a432294d3d29bba592f49d1b604862b94be1`)

## Highlights
- **English Learning Center (`/english`)**: Persistent track preferences (`IELTS Academic`, `IELTS General Training`, `CEFR Multi-level`, `General English`), target scores, mobile-safe search, and Light/Dark contrast parity.
- **Exam Engine Reliability 2.0**: Monotonic answer revisions (`409 STALE_REVISION`), active-session lease takeover (`session-takeover/`), idempotent submit, 7-state sync badge, shared-browser logout draft scrub, and `CdExamInterface` full support for `TEXT_MATCH`/`WRITTEN`/`SPEAKING_PROMPT`.
- **Exam Builder 3.0 & Listening/Reading Engines**: Schema 1.0 JSON import/export/keyless templates, mock readiness & publish parity, HTTP `206 Range` audio streaming, `stimulusRef` passage separation (`EX4-402`), highlights/notes recovery, and post-review evidence display.
- **Writing Studio 3.0 & Essay Assessment 3.0**: IELTS Ac Task 1, GT Letter, Ac/GT Task 2, and BMB Multilevel v2 tasks, backend draft save/restore, repeated-phrase grounded inline highlighting, vocabulary upgrades, next-level examples, and Teacher review escalation.
- **Speaking AI 3.0**: PyAV (`av>=14.0,<20.0`) WebM/OGG/Opus + Wave duration verification, Chromium CBT Speaking capture & upload, honest unmeasured-pronunciation partial deferral (`overall_band = None`), Multilevel `/75` conversion, and privacy-preserving teacher review workflow.
- **IELTS Ac/GT & CEFR Multilevel v2 Full Mocks**: Verified Reading Ac vs GT curves, Task 2 `2x` Writing weight, `UZBMB_MULTILEVEL_EN_2026_V2` (`5/5/6` Writing, `5/5/5/6` Speaking), `ONE_WORD` / `ONE_WORD_AND_OR_NUMBER` rules, Gradebook & Certificate Card parity, and strict pending-overall hold.
- **Vocabulary & Grammar Studios (`/vocabulary`, `/grammar`)**: Shared `PronunciationEngine`, answer-safe quizzes (`synonym`, `fill_blank`, `context_meaning`, `listen_*`), and 10 seeded English Grammar topics.
- **Teacher English Workspace (`/teacher/english`) & Telegram Center**: Unified Writing/Speaking/Mock grading inbox, separated IELTS vs Multilevel cohort analytics, formula-safe `CSV` + `XLSX` + paginated `PDF` exports, `/english` Telegram Bot command, `/tma/api/english/` hub, and Admin AI Cost Control panel.
