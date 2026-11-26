# GRANDEC NEXT 8.0 — Phase Execution Tracker

- **Branch:** `feat/grandec-next-8-0-english-learning`
- **Base:** `main @ 5db1a432294d3d29bba592f49d1b604862b94be1` (`v2.12.0`)
- **Reference:** `bestwayec/bestway @ 67b92f5419e0bf9e95f2a16852019aef3c72659e` (strictly read-only)

| Phase | Name | Status | Verification / Notes |
| :--- | :--- | :--- | :--- |
| Phase 00 | Full Audit & BESTWAY Integration Map | PASS | Inventoried GRANDEC models/APIs/UI, inspected BESTWAY reference docs & core code, documented 10 confirmed bugs/gaps (`N8-001`..`N8-010`), integration matrix, architecture, and acceptance criteria. |
| Phase 01 | English Learning Center | PASS | Added `english_track`, `target_band`, `target_cefr_level` on `Profile` + migration `0027`, exposed `/api/auth/me/` + `GET/PATCH /api/v1/english/center/`, built `/english` (`EnglishCenter.tsx`) + Dashboard entry + nav & uz/ru/en i18n; 3/3 pytest, 0 oxlint warnings, 34/34 frontend tests, tsc pass. |
| Phase 02 | Exam Engine Reliability 2.0 | PENDING | Monotonic revisions, 7-state sync UI, session takeover lock, fix `N8-001` & `N8-002`. |
| Phase 03 | English Exam Builder 3.0 | PENDING | Schema 1.0 JSON validate/import/export, keyless templates, Undo/Redo, mock readiness validation. |
| Phase 04 | Listening Engine | PENDING | Server playback schedule, Range-safe private audio, practice transcripts/timestamps, synthetic WAV fixtures. |
| Phase 05 | Reading Engine | PENDING | Split pane + mobile tabs, `stimulusRef` identity, highlights/notes/bookmarks, canonical types & evidence review. |
| Phase 06 | Writing Studio 3.0 | PENDING | IELTS Ac/GT + BMB Multilevel v2 writing tasks, split prompt/editor, fix `EssayStudio` contract (`N8-003`). |
| Phase 07 | Essay Checking & AI Writing Assessment 3.0 | PENDING | Grounded evidence offsets, calibration harness, progressive disclosure result UI, English/BMB Teacher Review (`N8-004`). |
| Phase 08 | Speaking AI 3.0 | PENDING | Async STT+eval, decoded duration validation, honest pronunciation policy, Multilevel rubric, teacher speaking review (`N8-005`). |
| Phase 09 | IELTS Full Mock Engine | PENDING | Complete L->R->W->S flow for Academic & General Training with separate Reading tables & pending overall rules. |
| Phase 10 | CEFR Multilevel Full Mock | PENDING | `UZBMB_MULTILEVEL_EN_2026_V2` blueprint, 5/5/6 Writing & 5/5/5/6 Speaking conversion, honest `ESTIMATED` status. |
| Phase 11 | Vocabulary & Grammar Learning System | PENDING | Shared `PronunciationEngine`, answer-safe vocab quizzes, Grammar Studio across 10 topics linked to mistakes (`N8-008`). |
| Phase 12 | Teacher Workspace & English Analytics | PENDING | Unified grading inbox, separated IELTS/Multilevel analytics, formula-safe exports, paginated PDFs. |
| Phase 13 | Telegram English Center | PENDING | Student & Teacher English Bot + TMA menus, RBAC & safe browser fallback for full mocks. |
| Phase 14 | Premium UI/UX, Performance & AI Cost Control | PENDING | Calm unified academic UI polish, AI gateway circuit breaker & admin cost dashboard, performance benchmarks. |
| Phase 15 | Final Integration, Security, E2E & Release Gate | PENDING | Full pytest (SQLite + PostgreSQL CI), oxlint, frontend tests, Chromium E2E across 6 viewports Light/Dark, Draft PR. |
