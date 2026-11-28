# GRANDEC NEXT 8.0 — English Learning & Assessment UX Report

## Overview
All English learning workflows follow a calm academic workspace layout with Light, Dark, and System themes synchronized through shared CSS variables and Tailwind utility tokens. Admin workspace views remain strictly isolated from student subject switchers (`workspace-routing.test.ts`).

## Delivered Student Journeys
1. **English Learning Center (`/english` — `EnglishCenter.tsx`)**:
   - Persistent track selector (`ielts_academic`, `ielts_general`, `cefr_multilevel`, `general_english`) and target Band / CEFR level backed by `Profile` (`accounts/0027`) and `/api/v1/english/center/`.
   - Unified entry cards to Listening tests, Reading tests, Full Mocks, Writing Studio, AI Speaking Simulator, Vocabulary Studio (`/vocabulary`), Grammar Studio (`/grammar`), Active Homework, Mistake Review, and Result History.
2. **Reading & Listening Exam Interface (`CdExamInterface.tsx`, `EnglishExamInterface.tsx`)**:
   - Server-enforced playback schedules & replay limits (`apps/tests/listening_service.py`) over HTTP `206` Range streaming (`apps/core/private_files.py`).
   - Reading passage `stimulusRef` isolation (`EX4-402`), highlights/notes/bookmarks persisted in `localStorage`, and 7-state sync pill (`useAnswerQueue` + monotonic `revision`).
3. **Writing Studio 3.0 (`EssayStudio.tsx`)**:
   - Supports IELTS Academic (`Task 1`, `Task 2`), IELTS General Training, and BMB Multilevel v2 (`Task 1.1`, `Task 1.2`, `Task 2`) with split prompt/editor views and live word-count zone indicators (`50+`, `120+`, `150+`, `180+`, `250+`).
4. **Speaking AI 3.0 (`SpeakingPractice.tsx`, `SpeakingResult.tsx`, `CdExamInterface.tsx`)**:
   - Pre-flight microphone readiness check (`navigator.mediaDevices.getUserMedia`), prep/speak timers, audio blob preservation on retry/network failure, async polling (`202` -> `evaluating`), honest null `pronunciation_score` rendering when unmeasured from text alone, and explicit Teacher Review escalation button.
5. **Vocabulary & Grammar Studios (`/vocabulary`, `/grammar`)**:
   - Shared `PronunciationEngine` (`frontend/src/lib/pronunciation/engine.ts`) with stored-audio-first + Web Speech API fallback, sequential double play (650 ms pause), and `0.7x` slow toggle (`PronounceButton.tsx`).
   - Answer-safe quiz types (`listen_choose`, `listen_type`, `fill_blank`, `context_meaning`, `synonym`) never exposing answer keys to clients.
   - 10 core English Grammar categories seeded with formulas, contrasts, interactive exercises, and recommendations derived from recent Essay & Speaking errors.
6. **Teacher English Workspace (`/teacher/english`)**:
   - Separated IELTS (`0–9` Band) and CEFR Multilevel (`0–75` BMB) cohort analytics (never averaged together).
   - Unified Writing + Speaking + Pending Mock inbox, audited score overrides table, formula-safe CSV export, and paginated ReportLab PDF export.
