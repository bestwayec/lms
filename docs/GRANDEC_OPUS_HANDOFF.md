# GRANDEC NEXT 3.0 — Claude Opus Handoff Specification

**Document Version:** 1.0  
**Date:** 2026-11-22  
**Handoff From:** Gemini 3.8 Flash High (Google Antigravity)  
**Handoff To:** Claude Opus  
**Repository:** `bestwayec/lms`  
**Current Branch:** `claude/stage3-attendance-concurrency`  
**PR URL:** https://github.com/bestwayec/lms/pull/139 (Draft)  
**PR Base Branch:** `claude/stage1-authz-hardening` (PR #138)  
**Latest Confirmed Commit:** `c20d49c`

---

## 1. Executive Summary

This document provides complete architectural, operational, and testing context for Claude Opus to seamlessly take over development of **GRANDEC NEXT 3.0**. 

All work from **Stage 3a (Attendance Concurrency)**, **Stage 3b (Group Membership History & Scoped Search)**, **Stage 3c (Teacher Workspace 3.0)**, **Stage 4 (Unified Homework Engine)**, **Priority A (Teacher Test Builder 3.0)**, and **Priority B (Complete Mobile UX Upgrade)** has been fully implemented, rigorously tested (including Playwright E2E and backend regression suites), committed, and pushed to `origin/claude/stage3-attendance-concurrency` under Draft Pull Request **#139**.

---

## 2. Branch Hierarchy & PR Stacking

```text
main
 │
 ├── PR #135 (Stage 0: Baseline recovery & PostgreSQL locks)
 │    └── PR #136 (Stage 1a: Authenticated private file access)
 │         └── PR #138 (Stage 1c: Auth & authz hardening)
 │              └── PR #139 (Stages 3a–3c, 4, Test Builder 3.0, Mobile UX) ◄── [CURRENT WORKSPACE]
 └── PR #137 (Stage 1b: Nginx private upload security — independent, not deployed)
```

> **IMPORTANT FOR OPUS:**  
> - Work continues on branch `claude/stage3-attendance-concurrency` (or branch from it for Stage 5).
> - PR #139 has base `claude/stage1-authz-hardening` to ensure the diff only reflects Stage 3 & Stage 4 changes without duplicating PRs #135, #136, or #138.
> - Never force-push or use destructive git reset.

---

## 3. Completed Capabilities & Technical Architecture

### 3.1. Stage 3a — Attendance Concurrency & Stale-Save Protection
- **Revision ETag Tokens**: Every attendance sheet generates a SHA-256 state revision token (`revision`). If another client updates attendance in the interim, stale saves are rejected with **HTTP 409 Conflict** and the fresh register is returned.
- **Atomic Batch Attendance**: `save_attendance_sheet` runs inside `transaction.atomic()`, ensuring all student status changes succeed or fail together.
- **Audited Corrections**: Once a register is marked `finalized`, modifications require `correction: true` with a mandatory textual reason, creating an immutable audit trail in `AttendanceCorrectionLog`.
- **Key Files**:
  - `apps/attendance/services.py`
  - `apps/webapi/views_attendance.py`
  - `tests/test_attendance_concurrency.py`

### 3.2. Stage 3b — Group Membership History & Scoped Search Authorization
- **GroupMembershipHistory Model**: Tracks student joins (`joined`), removals (`removed`), and re-joins (`rejoined`) with timestamp, notes, and the initiating user (`changed_by`).
- **Data Preservation Guarantee**: Removing a student from a group never cascade-deletes their historical test attempts, homework submissions, attendance entries, or grades.
- **Tenant-Scoped Search**: The `GET /api/v1/school/students/` endpoint restricts results to students within the teacher's active learning center and branch. Independent tutors can only search their own students.
- **Key Files**:
  - `apps/courses/models.py` (`GroupMembershipHistory`)
  - `apps/courses/group_service.py`
  - `apps/courses/migrations/0014_groupmembershiphistory.py`
  - `tests/test_stage3b_membership_history.py`

### 3.3. Stage 3c — Teacher Workspace 3.0 Dashboard
- **Teacher Action Hub**: Prominent operational tiles for:
  1. *Davomat olish* (Attendance)
  2. *Vazifa berish* (Unified Homework)
  3. *Guruhlarim* (Groups Command Center)
  4. *Natijalar* (Results & Gradebook)
- **Unified Overview Endpoint**: `GET /api/v1/school/teacher/` delivers cached roster counts, active assignments, and today's attendance summary.
- **Key Files**:
  - `apps/courses/teacher_workspace_service.py`
  - `frontend/src/pages/TeacherDashboard.tsx`
  - `tests/test_stage3c_teacher_workspace.py`

### 3.4. Stage 4 — Unified Homework Engine & Student Portal
- **Non-Destructive Cancellation**: `delete_teacher_homework` performs a safe status transition to `CANCELLED` (`cancelled_at`, `cancelled_by`), preserving historical attempts and submissions.
- **Strict Test Authorization**: Teachers cannot assign unpublished/draft tests or tests created by other teachers. Official tests remain assignable platform-wide.
- **Unified Multi-Content Assignment**: Supports Tests, Essays, Vocabulary Packs, Course Lessons, and Custom Written Tasks.
- **Student Homework Lifecycle**:
  - State machine: `NOT_STARTED` ➔ `IN_PROGRESS` ➔ `SUBMITTED` / `AWAITING_REVIEW` ➔ `GRADED` (or `OVERDUE` / `CANCELLED`).
  - Score 0.0 is treated as a valid graded score (`GRADED`), never pending review.
  - Endpoints: `GET /api/v1/school/student/homeworks/`, `GET <id>/`, `POST <id>/start/`, `POST <id>/save/`, `POST <id>/submit/`, `GET <id>/result/`.
- **Student Portal**: Responsive React interface at `/my-homework` ([MyHomework.tsx](file:///c:/Users/user/Desktop/lms/frontend/src/pages/MyHomework.tsx)).
- **Key Files**:
  - `apps/courses/homework_service.py`
  - `apps/courses/migrations/0015_homework_cancelled_at_homework_cancelled_by_and_more.py`
  - `apps/webapi/views_homework.py`
  - `frontend/src/pages/MyHomework.tsx`
  - `frontend/src/components/TeacherHomeworkWizard.tsx`
  - `tests/test_stage4_unified_homework.py`

### 3.5. Priority A — Teacher Test Builder 3.0
- **Mode 1 (Manual Builder)**: Individual question creation, points, explanations, question reordering, question duplication, and duplicate choice validation.
- **Mode 2 (Smart Paste Bulk Entry)**: Smart text parser parsing `Q1. ... A) ... ANSWER: B` (and localized variants `Javob:`, `Kalit:`, `Ответ:`) with 10/20/30-question templates.
- **Mode 3 (Structured File Import)**: CSV question extraction with choices, answer keys, explanations, points, validation warnings, and preview confirmation.
- **3-Step Wizard**: Test metadata ➔ Question builder + Answer matrix + Live Preview ➔ Checklist, 1-click issue jump, draft save, publish, and assignment modal.
- **Test Bank**: Search, subject/status filters, test cloning (`POST /duplicate/`), safe draft deletion (`DELETE /tests/<id>/`), and CSV export with formula sanitization (`safe_cell`).
- **Key Files**:
  - `apps/tests/studio_parser.py`
  - `apps/tests/studio_service.py`
  - `apps/tests/views_studio.py`
  - `frontend/src/pages/TeacherStudio.tsx`
  - `frontend/src/pages/TeacherStudioEditor.tsx`
  - `frontend/src/pages/TeacherStudioResults.tsx`
  - `frontend/src/components/studio/BlockCard.tsx`
  - `tests/test_stage4_test_builder_3.py`
  - `tests/test_teacher_studio.py`

### 3.6. Priority B — Complete Mobile UX Upgrade (3.0)
- **Touch-Friendly Controls**: All inputs, choice radios, and action buttons maintain `>= 44x44px` touch targets.
- **Sticky Actions**: Mobile sticky bar in test builder for fast draft saves and step navigation without infinite scrolling.
- **Mobile Student Exam Runner**: Sticky bottom bar with palette sheet for fast question navigation, full-width choice tap targets (`>= 48px`), and offline autosave.
- **Telegram Mini App (TMA)**: Viewport adaptation, theme color matching, seamless initData auth, and safe bottom padding.
- **Key Files**:
  - `frontend/src/styles/studio.css`
  - `frontend/src/pages/TakeTest.tsx`
  - `frontend/src/pages/Tma.tsx`

---

## 4. Verification Results & Test Status

### Backend Tests
```bash
pytest tests/test_attendance_concurrency.py \
       tests/test_stage3b_membership_history.py \
       tests/test_stage3c_teacher_workspace.py \
       tests/test_stage4_unified_homework.py \
       tests/test_stage4_test_builder_3.py \
       tests/test_teacher_studio.py \
       tests/test_telegram_security_evolution.py -v
```
- **Passed:** 92
- **Skipped:** 5 (Row-level lock race tests explicitly skipped on SQLite, active on PostgreSQL)
- **Failed:** 0
- **Duration:** 47.13s

### Code Quality & Static Analysis
- `ruff check .`: **All checks passed!** (0 errors)
- `python manage.py check`: **0 issues (0 silenced)**
- `python manage.py makemigrations --check`: **No changes detected**

### Frontend Quality & Unit Tests
```bash
npm --prefix frontend test
```
- **Passed:** 24/24 tests (Parity between `uz`, `ru`, `en` translations, XSS sanitization, responsive charts, smart paste)
- `npm --prefix frontend run lint`: **0 errors**
- `npm --prefix frontend run build`: **Clean build in 2.27s** (`tsc -b && vite build`)

### Browser / Playwright E2E Tests
```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE="C:\Program Files\Google\Chrome\Application\chrome.exe" npm --prefix frontend run test:e2e
```
- **Passed:** 23/23 tests (3.9m) across desktop (1440px) and mobile (375px) viewports
- **Failed:** 0

---

## 5. Database Migrations Added in this Stack

1. **`apps/courses/migrations/0014_groupmembershiphistory.py`**:
   - Model `GroupMembershipHistory` (`group`, `student`, `action`, `changed_by`, `created_at`, `notes`).
2. **`apps/courses/migrations/0015_homework_cancelled_at_homework_cancelled_by_and_more.py`**:
   - Fields on `Homework`: `cancelled_at`, `cancelled_by`, `idempotency_key`, `content_type`, `assigned_student`, `time_limit_minutes`, `max_attempts`.

---

## 6. Known Risks & Blocker Checklist for Claude Opus

1. **PostgreSQL Concurrency Tests**:
   - 5 tests (`test_exactly_one_of_two_concurrent_saves_with_the_same_revision_wins`, `test_concurrent_enrollment_thread_safety`, etc.) require a PostgreSQL 16 instance (`config.settings.postgres_test`). When staging on Contabo VPS (`169.58.58.229`) or CI with Postgres service, run these with `DJANGO_SETTINGS_MODULE=config.settings.postgres_test`.
2. **Production Nginx Deployment (PR #137)**:
   - PR #137 blocks public `/media/` access to private uploads. It is ready for deployment once the host administrator reviews Nginx configs.
3. **Telegram Webhook Verification**:
   - Live Telegram bot callbacks require active staging bot credentials (`TELEGRAM_BOT_TOKEN`).
4. **Planned Next Stages**:
   - **Stage 5**: Live Tablo / Monitoring & Real-time Class Sync (Teacher live scoreboard, WebSocket reconnects).
   - **Stage 6**: Production Staging, Migration run, and Final Release Verification on `grandec.uz`.

---

## 7. How to Continue Development

```bash
# 1. Ensure you are on the continuation branch
git checkout claude/stage3-attendance-concurrency
git pull origin claude/stage3-attendance-concurrency

# 2. Verify git state
git status --short --branch
# Expected: clean working tree, up to date with origin/claude/stage3-attendance-concurrency

# 3. Verify test baseline
pytest tests/test_stage4_unified_homework.py tests/test_stage4_test_builder_3.py
npm --prefix frontend test
```
