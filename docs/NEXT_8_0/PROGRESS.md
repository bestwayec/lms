# GRANDEC NEXT 8.0 — Phase Execution Tracker

- **Branch:** `feat/grandec-next-8-0-english-learning`
- **Base:** `main @ 5db1a432294d3d29bba592f49d1b604862b94be1` (`v2.12.0`)
- **Reference:** `bestwayec/bestway @ 67b92f5419e0bf9e95f2a16852019aef3c72659e` (strictly read-only)

| Phase | Name | Status | Verification / Notes |
| :--- | :--- | :--- | :--- |
| Phase 00 | Full Audit & BESTWAY Integration Map | PASS | Inventoried models/APIs/UI, inspected BESTWAY reference modules, logged `N8-001`..`N8-010`. |
| Phase 01 | English Learning Center | PASS | Persistent track/target settings (`/english`), Dashboard entry, Dark/Light contrast & `360px` search spacing verified visually. |
| Phase 02 | Exam Engine Reliability 2.0 | PASS | Monotonic revisions (`409`), takeover lock, idempotent submit, 7-state sync pill, `clearTokens()` draft scrub on logout. |
| Phase 03 | English Exam Builder 3.0 | PASS | Schema 1.0 validate/import/export/template, readiness gates, publish + `audio_url` fix & group assign E2E verified. |
| Phase 04 | Listening Engine | PASS | HTTP `206 Range` audio streaming, server replay limit, practice transcripts, real WAV E2E playback. |
| Phase 05 | Reading Engine | PASS | `stimulusRef` isolation (`EX4-402`), post-submit evidence display, highlights/notes recovery, `TEXT_MATCH` (`"text"`) CBT fix. |
| Phase 06–07 | Writing Studio 3.0 & Grounded AI Assessment | PASS | Ac/GT/Multilevel tasks, `ielts_draft_view` persistence across reload, repeated-quote context grounding, inline highlighter, teacher escalation. |
| Phase 08 | Speaking AI 3.0 | PASS | `av>=14.0,<20.0` (`19.0.2`), bounded WAV/WebM verification, honest `PR=None -> overall_band=None` partial deferral, Chromium fake-mic upload. |
| Phase 09–10 | IELTS Ac/GT & CEFR Multilevel v2 Full Mocks | PASS | Separate Academic vs General Reading tables, Task 2 `2x` Writing weight, CBT Speaking upload + `ExamBridgeService` scaling, 3/3 Chromium 4-skill E2E journeys PASS. |
| Phase 11 | Vocabulary & Grammar Studios | PASS | `PronunciationEngine`, answer-safe `synonym` + token quizzes, 10 seeded Grammar categories. |
| Phase 12 | Teacher English Workspace & Exports | PASS | Unified inbox (`mocks` `writing_items`/`speaking_items`), separated analytics, formula-safe `CSV` + `XLSX` + paginated `PDF`. |
| Phase 13–14 | Telegram English Center & Admin AI Cost Control | PASS | `/english` bot command, `/tma/api/english/`, Admin AI Metrics card, Dark Mode `/panel` `.admin-action` fix. |
| Phase 15 & Independent Audit | Release Audit, PostgreSQL Migration/Rollback & Full Gate | PASS | SQLite **`2058 passed, 14 skipped`**, PostgreSQL 17.11 **`247 passed, 0 failed`**, `ruff`/`oxlint`/`tsc`/`vite build` (`2.62s`), Chromium E2E across 3 mocks & 6 viewports (`0` console/5xx errors), PG `v2.12.0` migration + reverse rollback verified; PR `#152` docs & audit matrix completed. |
