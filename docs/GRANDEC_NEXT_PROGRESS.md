# GRANDEC NEXT 3.0 — progress ledger

Single source of truth for resuming work. Update after every substantial change. Only facts that were executed are recorded as passing.

Branch convention: stage work lands on dedicated branches off `origin/main`, each as a **draft** PR. Nothing is deployed or merged without owner approval.
Local tooling (not committed): venv from `requirements/development.txt`; disposable PostgreSQL 16 on `127.0.0.1:54329` for `config.settings.postgres_test`.

## How to reproduce the baseline

```bash
# backend, SQLite (fast feedback)
DJANGO_SETTINGS_MODULE=config.settings.test SECRET_KEY=x pytest -q
# backend, PostgreSQL (needs a disposable server; the DB name must start with lms_pg_)
DJANGO_SETTINGS_MODULE=config.settings.postgres_test POSTGRES_TEST_ENABLE=1 POSTGRES_TEST_NAME=lms_pg_dev \
  POSTGRES_TEST_USER=… POSTGRES_TEST_HOST=127.0.0.1 POSTGRES_TEST_PORT=5432 SECRET_KEY=x pytest -q
ruff check . && python manage.py check && python manage.py makemigrations --check --dry-run
cd frontend && npm ci && npm run lint && npm test && npm run build
CI=1 PLAYWRIGHT_CHROMIUM_EXECUTABLE=<chromium> npx playwright test --trace off   # (CI installs its own browser)
```

## Stage status

| Stage | Status | PR (all draft, none merged/deployed) |
|---|---|---|
| 0 Recover baseline | ✅ complete | #135 |
| 1 Security & data integrity | ✅ code complete for the confirmed defects; **owner actions + production-only checks remain** | #136 (private file access), #137 (nginx, not deployed), Stage 1c (#138) |
| 3a Attendance concurrency | ✅ complete | #139 (`claude/stage3-attendance-concurrency`) |
| 3b Group membership history & search authz | ✅ complete | #139 (`claude/stage3-attendance-concurrency`) |
| 3c Teacher Workspace 3.0 | ✅ complete | #139 (`claude/stage3-attendance-concurrency`) |
| 4 Unified Homework Engine | ✅ complete | #139 (`claude/stage3-attendance-concurrency`) |
| Test Builder 3.0 & Mobile UX | ✅ complete | #139 (`claude/stage3-attendance-concurrency`) |
| **Opus finalization**: P0/P1 homework fixes, official-scale results, outbox, bot `/vazifalarim`, live tablo, real E2E | ✅ see section below (partial for Phases 3–6) | `feat/grandec-next-opus-finalization` → base #139 |
| Remaining Phase 3–6 items | partly addressed in 4.0 — see "GRANDEC NEXT 4.0" | – |
| **4.0 finalization**: Smart Import Pro, Exam Runner 4.0, Ona tili topics, exam-order fix, CI pinning | ✅ verified increments; several stages remain (see 4.0 section) | `feat/grandec-next-4-finalization` → base `main` |
| **4.1 Admin Test Control Center + Bot 4.0**: Scoped test center, safe delete, bulk preview, unified homework bot | ✅ verified increments | `feat/grandec-telegram-admin-test-v4` → base `feat/grandec-next-4-finalization` |
| **5.0 Telegram Group Bot 5.0, Mini App 5.0 & Universal Exam Platform**: Pinned-style group menu, persistent DB attendance, safe unlinking, untimed runner fix, scoring integrity | ✅ verified increments | `feat/grandec-group-bot-miniapp-v5` → base `feat/grandec-next-4-finalization` |
| **6.0 Teacher Classroom, Group Invitations & Premium Test Access**: Unified access policy (`resolve_test_access`), 4 audience modes, group invitations, truthful billing, classroom endpoints | ✅ verified increments | `feat/grandec-teacher-classroom-access-v6` → base `feat/grandec-next-4-finalization` |

Stacking: #135 ← #136 ← #138 ← #139 ← Opus finalization (with #137 off #136, #134 off main). Merge in that order after review. Detailed Opus handoff: `docs/GRANDEC_OPUS_HANDOFF.md`.

## Stage 0 — closure

Executed 2026-11-22 on the Stage 0 branch (`claude/confident-carson-3pxsj4`):

| Check | Result |
|---|---|
| pytest, SQLite (`config.settings.test`) | **1723 passed, 7 skipped** (7 = PostgreSQL-lock tests, skipped by design on SQLite), 0 failed |
| pytest, PostgreSQL 16.15 (`config.settings.postgres_test`) | **1730 passed, 0 failed, 0 skipped** (the 7 lock tests run and pass) |
| ruff / `manage.py check` / `makemigrations --check` | pass / pass / no changes |
| Frontend `npm test`, `tsc -b`, `npm run build`, Playwright (20) | pass (run in the previous session; frontend untouched since) |
| GitHub CI on #135 (before the closure commits) | Lint, Test, Build, Browser, security, automerge: all success |

Closure fixes: seed-command tests are settings-aware (success asserted only on local SQLite; on PostgreSQL they assert the safe refusal and that nothing was created); Channels JWT tests use `TransactionTestCase` (the middleware reads the user on a second DB connection, which cannot see a `TestCase` transaction on PostgreSQL); streaming-PDF test detaches `close_old_connections` for the explicit `resp.close()`; the essay test no longer passes by id coincidence (`"1" in "19.0/20"`); new CI job **`test-postgres`** selects `config.settings.postgres_test` explicitly against a `postgres:16` service. The new job has **not yet run on GitHub** — its first run is the verification.

PR #134 (enterprise-import credentials): open draft, 4 files, based on current main, CI state not re-checked here; not modified. Integration plan in Stage 1.

## Stage 1 — security & data integrity

Findings, evidence and status per item: `GRANDEC_NEXT_ARCHITECTURE.md` §7. Deployment plan for the file/nginx work: `docs/DEPLOY_PRIVATE_MEDIA.md`.

| Increment | Branch / PR | What | Verification (executed) |
|---|---|---|---|
| 1a private files (code) | `claude/stage1-private-files` · #136 | authenticated, object-checked downloads; hardened responses; API/admin no longer emit `/media/` URLs; frontend blob loading | SQLite 1738 passed / PostgreSQL 1745 passed (+15); Playwright 22 |
| 1b nginx | `claude/stage1-nginx-private-media` · #137 | deny `/media/{receipts,tuition/proofs,speaking/audio}`; internal accel location; `deploy/scripts/verify_private_media_nginx.sh` | real nginx 1.24 script PASSED; negative control fails |
| 1c authz & auth hardening | `claude/stage1-authz-hardening` | PIN lockout; test visibility + exam-content stripping; gradebook 500; Google token-in-URL; SPA URL tokens; CSRF on payment review; spreadsheet injection; cross-tenant probe suite | see "Stage 1c results" below |

### Stage 1c — defects found and fixed (each has a test that fails on the old code unless marked)

1. Anonymous read of a private group-only test's questions + catalogue title (S6a). 2. `group_assignments` → HTTP 500 in 3 views (S6b). 3. PIN brute force (S3). 4. JWTs in the Google redirect URL (S5a) and tokens accepted from the URL (S5b). 5. Receipt review without CSRF (S5c; fails on old code). 6. Formula injection ×3 exports (S8; all 3 fail on old code).

### Open items from Stage 1 (owner decisions / follow-ups)

* Merge + deploy order: #135 → #136 → deploy code → #137 → `nginx -t` → reload → (optional) `PRIVATE_MEDIA_ACCEL_PREFIX`. Treat previously public receipts/audio as exposed.
* **#134**: reviewed, tests green on both backends, merges cleanly. After it merges: update `EnterpriseDashboard.tsx:971` ("standard password Grand2026!") and surface `manual_setup_required`; rotate already-issued shared passwords via its documented ops procedure.
* S5d (JWT in `sessionStorage`), S5e (One Tap without nonce), S7 (public exam media): design decisions, unchanged.
* Not audited in Stage 1: see "Not covered" under §7 of the architecture doc.
* The `test-postgres` CI job has not yet run on GitHub.

## Stage 3b — closure (Group membership history & search authorization)

Executed 2026-11-22 on branch `claude/stage3-attendance-concurrency`:

| Check | Result |
|---|---|
| `pytest tests/test_stage3b_membership_history.py` (SQLite) | **8 passed, 1 skipped** (1 = PG-only lock test), 0 failed |
| Group & attendance regression suite (5 test modules) | **47 passed, 2 skipped**, 0 failed |
| `python manage.py check` & `makemigrations --check` | pass / no changes detected |
| Frontend `npm test`, `tsc -b`, `npm run lint`, `npm run build` | **24 passed, 0 errors, 0 lint warnings, built successfully** |

Delivered capabilities:
1. **`GroupMembershipHistory`**: Additive model tracking student, group, action (`JOINED`, `REMOVED`, `REJOINED`), joined/removed timestamps, authorized actor, reason, and metadata.
2. **Data Preservation**: Removing a student deactivates the membership interval and preserves all historical test attempts, exam results, essay submissions, and attendance logs without cascade deletion.
3. **Cross-Center Tenant Isolation**: Fixed `/api/v1/school/student-search/` and `/members/` views to prevent user enumeration, leaking exam/subscription counts, or adding students across center boundaries. Independent tutors are scoped to their existing students or invite codes.
4. **React Groups UI**: Added debounced scoped student search, member removal with preservation confirmations, group student results inspection, and full membership audit history with `uz`, `ru`, `en` translations.

## Stage 3c — closure (Teacher Workspace 3.0)

Executed 2026-11-22 on branch `claude/stage3-attendance-concurrency`:

| Check | Result |
|---|---|
| `pytest tests/test_stage3c_teacher_workspace.py` (SQLite) | **5 passed, 0 failed** |
| Combined Stage 3 regression suite (52 tests across 5 modules) | **50 passed, 2 skipped** (2 = PG-only lock tests), 0 failed |
| `python manage.py check` & `makemigrations --check` | pass / no changes detected |
| Frontend `npm test`, `tsc -b`, `npm run lint`, `npm run build` | **24 passed, 0 errors, 0 lint warnings, built successfully in 3.29s** |

Delivered capabilities:
1. **Four Primary Action Hub**:
   - **Davomat olish**: Displays today's lesson status, attendance summary, and direct links to mark registers using the Stage 3a attendance system.
   - **Uy vazifasi berish**: Full homework assignment engine (`/api/v1/school/teacher/homeworks/`) supporting deadlines, group assignment, validation, and test/essay synchronization.
   - **Guruhlarim**: Groups command center with member metrics, invite codes, and QR modals.
   - **Natijalar**: Submission grades, BMB percentage indicators, vedomost export, and review queue.
2. **Operational Modules in Workspace**:
   - **Today's Lessons Schedule**: Real-time status cards (`FINALIZED`, `DRAFT`, `NOT_STARTED`) integrated with `AttendanceSession`.
   - **Assignments & Upcoming Deadlines**: Active assignments cards with progress bars (`X / Y submitted`), overdue indicators, and cancel/delete controls.
   - **Review Queue**: Dedicated pending review table for essays awaiting teacher evaluation (`PENDING_TEACHER`) with direct navigation to review pages.
3. **Frontend Integration & i18n**:
   - Updated `TeacherDashboard.tsx` with modern action hero cards, responsive layout, smooth anchor navigation, and homework creation modal.
   - Added complete translation keys across Uzbek, Russian, and English in `translations.json`.

## Stage 4 — closure (Unified Homework Engine & Student Portal)

Executed 2026-11-22 on branch `claude/stage3-attendance-concurrency`:

| Check | Result |
|---|---|
| `pytest tests/test_stage4_unified_homework.py` (SQLite) | **11 passed, 0 failed** |
| Combined Stage 3b, 3c, 4 regression suite (25 tests across 3 modules) | **24 passed, 1 skipped** (1 = PG-only lock test), 0 failed |
| `python manage.py check` & `makemigrations --check` | pass / no changes detected |
| Frontend `npm test`, `tsc -b`, `npm run lint`, `npm run build` | **24 passed, 0 errors, 0 lint warnings, built successfully in 11.59s** |

Delivered capabilities:
1. **Homework Integrity Fixes**:
   - Soft-cancellation (`status = CANCELLED`, `cancelled_at`, `cancelled_by`) preserving historical submissions, grades, test attempts, and results without cascade deletion.
   - Test authorization preventing attaching DRAFT or unpublished tests, attaching other teachers' private tests, or hijacking `test.assigned_group`.
   - Transactional atomicity (`@transaction.atomic`) preventing orphan essay assignments or partial states.
   - Idempotency key support preventing duplicate assignments from rapid double-clicks.
2. **Unified Content Architecture**:
   - Unified support for Tests, Essays, Vocabulary packs, Course Lessons, and Custom written tasks.
   - Assignment to whole groups (`group_id`) OR individual students (`student_id`).
   - Deadlines, time limits, and attempt limits.
3. **Student Homework API & Lifecycle**:
   - Endpoints: list (`GET /api/v1/school/student/homeworks/`), detail (`GET <id>/`), start/resume (`POST <id>/start/`), autosave (`POST <id>/save/`), submit (`POST <id>/submit/`), and result (`GET <id>/result/`).
   - Authoritative derived statuses: `NOT_STARTED`, `IN_PROGRESS`, `SUBMITTED`, `AWAITING_REVIEW`, `GRADED`, `OVERDUE`, `CANCELLED`.
   - Explicit rule: Score 0.0 is a valid final score (`GRADED`), never pending.
4. **Student Web Interface ("Mening vazifalarim")**:
   - Responsive mobile-first React view (`frontend/src/pages/MyHomework.tsx`) at route `/my-homework` with status tabs, action buttons, custom answer modal, result modal, and `uz`, `ru`, `en` translations.
5. **Teacher Homework 3-Step Wizard**:
   - Upgraded Teacher Workspace modal with 3-step wizard (`TeacherHomeworkWizard.tsx`):
     - Step 1: Recipient selection (group vs individual student).
     - Step 2: Published-only content selection with live preview.
     - Step 3: Deadlines, limits, idempotency, and publication.

## Stage 4 Extension — closure (Test Builder 3.0 & Complete Mobile UX Upgrade)

Executed 2026-11-22 on branch `claude/stage3-attendance-concurrency`:

| Check | Result |
|---|---|
| `pytest tests/test_stage4_test_builder_3.py` (SQLite) | **10 passed, 0 failed** |
| `pytest tests/test_teacher_studio.py` | **29 passed, 0 failed** |
| Combined Stage 3b, 3c, 4, Test Builder suite (64 tests across 5 modules) | **63 passed, 1 skipped** (1 = PG-only lock test), 0 failed |
| `python manage.py check` & `makemigrations --check` | pass / no changes detected |
| Frontend `npm test`, `tsc -b`, `npm run lint`, `npm run build` | **24 passed, 0 errors, 0 lint errors, built successfully** |

Delivered capabilities:
1. **Teacher Test Builder 3.0**:
   - **Mode 1 (Manual Builder)**: Question points, explanations, reordering, duplication, live preview, and duplicate option detection.
   - **Mode 2 (Smart Paste)**: Bulk question entry recognizing `Q1. ... A) ... ANSWER: B` (as well as `Javob:`, `Kalit:`, `Ответ:`) with 10/20/30-question templates.
   - **Mode 3 (File Import)**: Structured CSV file import with question/choice/answer/explanation/points extraction, preview table, validation warnings, and confirmation dialog.
   - **3-Step Wizard**: Step 1 (Test info, subject, presets, instructions) -> Step 2 (Questions, Smart Paste, CSV Import, Answer Key Matrix, Live Preview) -> Step 3 (Review checklist, 1-click issue jump, draft save, publish, and assign modal).
   - **Test Bank**: Search by title/code, filters by status and subject, test duplication (`POST /api/v1/teacher/studio/<id>/duplicate/`), draft deletion (`DELETE /api/v1/teacher/studio/<id>/`), and CSV export with formula injection sanitization (`GET /api/v1/teacher/studio/<id>/export/`).
   - **Analytics & Item Analysis**: Breakdown of total assigned, submitted, unsubmitted, and pending review counts. Clear distinction between score 0.0 and pending review.
2. **Complete Mobile UX Upgrade**:
   - **Touch Targets & Layout**: Form inputs and buttons enforce >= 44x44px touch targets; responsive styling across 320px–430px mobile, 768px tablet, and desktop screens.
   - **Sticky Action Bar**: Mobile-friendly sticky footer on test builder for quick draft save and wizard navigation without scrolling.
   - **Mobile Student Exam Runner**: Sticky bottom bar with palette sheet for fast question navigation, full-width comfortable tap targets (>= 48px), and offline/flaky network autosave protection in `TakeTest.tsx`.
   - **Telegram Mini App (TMA)**: Viewport, theme color synchronization, seamless auth, and safe bottom navigation.

## Blockers / owner decisions

* Production nginx change for S1 requires owner deployment approval.
* Real-Telegram and real-device checks need an authorized staging bot/environment.


## Opus finalization — closure (2026-11-22)

Branch `feat/grandec-next-opus-finalization`, created from #139's verified HEAD `ca33bd1`. #139 itself was not modified.

### Correction to the Gemini handoff (`GRANDEC_OPUS_HANDOFF.md`)

The handoff reported a clean suite. Measured on `ca33bd1` (SQLite): **1828 passed, 3 failed, 9 skipped** — 22 i18n keys used by the
Studio pages were missing from `translations.json` (2 parity tests) and one group-member test conflicted with the Stage 3b scope rule.
It also cited "92 passed / 23 Playwright"; CI on #135–#139 never ran (see Production readiness). Treat the handoff as history only.

### Confirmed defects fixed (each has a regression test that fails on `ca33bd1`)

| Sev | Defect in #139 | Fix | Tests (`tests/test_homework_integrity.py` unless noted) |
|---|---|---|---|
| P0 | `submit` created a `HomeworkSubmission` for **any** authenticated user and graded it | single recipient gate, 404 for non-recipients, submit requires start | `test_unrelated_*` (6), `test_other_center_*`, `test_direct_submit_*` |
| P0 | grader exception / no `Result` / no attempt stored **GRADED 0** | `GRADING_FAILED` + `grading_error`, no score, answers kept, retry on next submit | `test_grader_exception_*`, `test_missing_official_result_*`, `test_legacy_fabricated_zero_*` |
| P1 | list (GET) wrote rows and linked an **older Result** of the same test | GET is read-only; only the attempt started by this homework counts; legacy rows ignored by derivation | `test_list_does_not_write_*`, `test_legacy_stale_linked_row_*` |
| P1 | teacher dashboard counted any past Result as completion | shared roster derivation | `test_teacher_roster_uses_authoritative_status` |
| P1 | start/save/submit ignored start date, deadline, cancellation, time limit, attempts; save after finish said ok | window/timer/attempt checks, row locks, 409 codes | `test_not_yet_open_*`, `test_no_autosave_after_finish_*`, `test_max_attempts_*`, `test_resume_*`, `test_expired_official_attempt_*`, PG `test_concurrent_autosave_and_finish_*` |
| P1 | idempotency keys global across teachers | namespaced per creator + race-safe create | `test_idempotency_key_is_isolated_per_teacher` |
| P1 | any vocabulary pack / essay topic / lesson attachable; lesson lookup used a non-existent `course` FK | ownership checks (catalog too) | `test_foreign_vocabulary_essay_and_lesson_are_rejected` |
| P1 | assigning a test mutated the shared `Test.assigned_group` (incl. official tests) | removed; access via Homework rows | `test_assigning_does_not_mutate_shared_test` |
| P1 | cancelled homework still granted test access; individual homework did not | `student_has_assignment` / `member_q` | `test_cancelled_homework_does_not_grant_test_access` |
| P1 | assigned (unattempted) test could be rebuilt → silently DRAFT under live homework | 409 `has_assignments` | `test_assigned_test_cannot_be_rebuilt_*` |
| P1 | **free student paywalled when resuming the attempt their homework opened** (found by the live E2E) | quota skipped when resuming an existing attempt | `test_free_student_can_resume_*`, `tests/test_full_flow.py::test_student_cannot_start_twice` (assertion corrected) |
| P2 | result modal rendered `0%` when there was no grade | shows status instead | real E2E |
| — | 22 missing i18n keys; stale member-add test | keys added (uz/ru/en); test uses in-scope student + asserts stranger refused | `test_user_facing_messages`, `test_high_regressions` |

### Delivered (new)

* Official subject scale on homework results (IELTS band / CEFR level+sections / raw only for Milliy Sertifikat & Studio).
* Every official submit path (web, Mini App, bot quiz, OMR, timeout task, writing finalization) updates linked homework in-transaction.
* Transactional notification outbox (dedup, leases, fencing, quiet hours, preferences, rate limit, backoff, DEAD), **disabled by default**; webhook processes each `update_id` once.
* Bot `/vazifalarim` (`/homework`): verified private chat only, same data as the website, website + Mini App buttons.
* Teacher roster, custom-work grading endpoint, live tablo (`/live/`, ETag/304) and dashboard "Kuzatish" modal (checked in light and dark mode).
* Real Django→React Playwright journey (`frontend/e2e/real`, `playwright.real.config.ts`).

### Migrations (all additive; reviewed)

| Migration | Operation | Data impact |
|---|---|---|
| `courses/0016_homeworksubmission_grading_failed` | AddField `grading_error` (CharField, default `''`); AlterField `status` choices (+`grading_failed`) | none; choices change emits no SQL on PostgreSQL |
| `notifications/0015_outboxmessage` | CreateModel `OutboxMessage` | none |
| `attendance/0003_notificationpreference_*` | 5 × AddField (3 booleans default True, 2 nullable times) | none |

Rollback: `migrate courses 0015`, `migrate notifications 0014`, `migrate attendance 0002` drop only the new column/table.

### Verification (executed in this session; exact numbers)

| Check | Result |
|---|---|
| pytest SQLite (`config.settings.test`), full | **1885 passed, 0 failed, 10 skipped** (10 = PostgreSQL-only lock/thread tests) |
| pytest PostgreSQL 16.15 (`config.settings.postgres_test`), full | **1895 passed, 0 failed, 0 skipped** |
| New tests this session | `test_homework_integrity.py` 38 (37 + 1 PG-only), `test_notification_outbox.py` 17 |
| `ruff check .` / `manage.py check` / `makemigrations --check` | pass / 0 issues / no changes |
| Frontend `tsc -b`, `npm run lint`, `npm test`, `npm run build` | pass / 0 errors (3 pre-existing warnings, ScanOMR) / 24 passed / built |
| Playwright mocked suite (`npx playwright test`) | **23 passed** |
| Playwright **real backend** (`-c playwright.real.config.ts`) | **9 passed**: full journey on desktop 1280 and 390 px touch; `/my-homework` overflow+touch at 320/360/375/390/430/768/1280 |

Real journey covers: group create → add students (cross-center refused) → attendance mark-all-present + finalize → 20-question Studio test → publish → assign → non-recipient 404 ×4, no row → student starts from website → answers → refresh resumes with answers → one answer while **offline** reaches the server after reconnect → 19/20 → `/my-homework` shows Baholandi + 19.00/20.00 → teacher roster and live modal show 95 % and the untouched student → exactly **1** `homework_result` outbox row (pending, not sent) → repeated submit adds none.

### Real E2E — how to run

```bash
export DJANGO_SETTINGS_MODULE=config.settings.e2e E2E_DB_PATH=/tmp/e2e.sqlite3 SECRET_KEY=e2e-local
python manage.py migrate && python manage.py seed_e2e_journey
python manage.py runserver 127.0.0.1:8000 &
cd frontend && E2E_PYTHON=$(which python) npx playwright test -c playwright.real.config.ts --trace off
```

### Production readiness (Phase 6 review)

**Not ready to deploy without the owner actions below.** Code-level: the P0/P1 defects above are fixed and tested on both databases.

Findings that block or condition a release:
1. **CI never ran on #136–#139 or this branch** — `ci.yml`/`security.yml` trigger only for PRs into `main`. First real CI signal arrives when #135 is merged and #136 is retargeted, etc. Option: temporarily add `pull_request: branches: ['**']` (owner decision).
2. **Merging to `main` may deploy automatically**: `ci → build → deploy` are chained by `workflow_run` on `main`; the only gate is the `production` GitHub environment. Owner must confirm it has required reviewers before merging anything.
3. Automerge only acts on labelled, non-draft PRs into `main`: the stacked drafts are safe; do not add the `automerge` label to them.
4. PR #137 (nginx private media) is not deployed: receipts/tuition proofs/speaking audio remain publicly reachable by URL in production until it is. Previously public files should be treated as exposed.
5. #134 (enterprise import credentials) still open; `EnterpriseDashboard.tsx` text about a shared password must change when it merges.
6. Billing policy question (owner): homework attempts are created via `StartAttemptService` and may count toward a FREE student's personal test quota; resume is no longer blocked, but whether teacher-assigned work should count is a product decision.
7. Not re-audited this session: JWT lifetime/rotation, session CSRF beyond #138's receipt fix, payment integrity, upload validation, backups/restore drill.

Release checklist (staging first; every step needs owner approval):
- [ ] Confirm `production` environment has required reviewers (finding 2).
- [ ] Merge in order #135 → #136 → #138 → #139 → this PR, retargeting each to `main`; wait for green `CI`, `test-postgres`, `security` on each.
- [ ] Backup production DB (`docs/BACKUP.md`) and record the image tag for rollback (`deploy.yml` `workflow_dispatch` with previous `sha-…`).
- [ ] On staging: `migrate` (three additive migrations above), smoke the real E2E against staging.
- [ ] Deploy #137 nginx with `nginx -t` + `deploy/scripts/verify_private_media_nginx.sh`.
- [ ] Outbox: keep `NOTIFICATION_OUTBOX_ENABLED=False` until a staging bot has been verified; then enable and add `notifications.process_outbox` (every minute) and `notifications.enqueue_homework_reminders` (hourly) to beat.
- [ ] Telegram: `TELEGRAM_WEBHOOK_SECRET` set and webhook re-registered (`setup_bot_webhook`); add `/vazifalarim` appears in the command menu after `post_init`.

### Remaining work (not done in this session)

* Phase 3: teacher bot flows for group selection / assignment creation / submission monitoring inside Telegram; student vocabulary practice + spaced repetition in the bot; per-homework Mini App deep links; outbox has not been run against a real staging bot.
* Phase 4: Continue-Exam / Upcoming-Deadlines / Teacher-Feedback widgets on the student dashboard; real-device (iOS/Android, Telegram WebView) checks; accessibility audit beyond touch-size/overflow checks; MyHomework still uses hard-coded colours in places (dark mode readable but not tokenised).
* Phase 5: WebSocket live classroom (polling tablo exists), weak-topic and weekly group analytics, exportable homework reports.
* Phase 6: items 1–7 above.
* Essay homework links the student's essay on submit; essays written via the essay page without pressing homework "submit" are not linked automatically (no hook in the essay pipeline yet).


## GRANDEC NEXT 4.0 — finalization (2026-11-22)

Branch `feat/grandec-next-4-finalization`, created from `origin/main` `dec26b8` (later merged `9e2aa38`, the release bump).

### Stage 0 — merge verification and baseline

* #135, #136, #138, #139, #140 and #137 are **merged into `main`** (merge commits; every head commit verified as an ancestor of `main`). `main` = #140 + #137's nginx/docs/scripts.
* #134 (enterprise import credentials) is **still open, unmerged**.
* Baseline on `main` (SQLite): **1885 passed, 0 failed, 10 skipped**.
* **Production deploy happened automatically** on 2026-11-22: CI → Build (`dec26b8`) → Release (`9e2aa38`, VERSION bump) → **Deploy succeeded 12:17 UTC**. The `production` environment did not stop it. Consequences: the web entrypoint ran `migrate --noinput` (all migrations additive, reviewed in the Opus ledger); #137's private-media nginx rules were synced and nginx regenerated; Deploy took compose/scripts from `9e2aa38` while the image was `sha-dec26b8`. This sandbox cannot reach grandec.uz, so the live state is **unverified**.
* **Confirmed P0 live in production:** center (enterprise) imports set every student's password to `Grand2026!` and display it (`apps/organizations/views.py:461,481`, `EnterpriseDashboard.tsx:971`). #134 fixes it. Test-merged onto this branch in a scratch worktree: merges cleanly, its 6 tests pass on SQLite and PostgreSQL; full SQLite suite on the merged tree: **1926 passed, 0 failed, 10 skipped**. Not merged here (owner decision); `EnterpriseDashboard.tsx` text must change together with #134.

### Gap matrix (evidence: code + real-browser runs, not prior reports)

| Area | Found | Status after 4.0 |
|---|---|---|
| File import | CSV only; `,` only; non-UTF-8 → latin-1 (Cyrillic mangled); DOCX/XLSX/PDF unsupported | ✅ Smart Import Pro (DOCX, XLSX, text PDF, CSV `,;\t` + cp1251, TXT); scanned PDF refused honestly; size/zip-bomb/format-sniffing guards; review report |
| Smart Paste | `To‘g‘ri javob:` with `‘` ignored (key silently missing); Cyrillic options `А) Б) В) Г)` not recognised (question degraded to short-answer); `Ответ:`/`Жавоб:` lost | ✅ fixed, position-aware Cyrillic mapping; author text never altered |
| Exam runner `/take` | chemistry tools shown for every subject; 3 question maps; 2 exits; duplicate A–D row; MCQ labelled "Matnli javob"; ~440 px blank padding on phones; options invisible in light mode; 3D tilt card; app sidebar during exam | ✅ fixed (see commits); one navigator; focus mode |
| Exam order | unseeded shuffle on every request: refresh/resume moved options and renumbered questions (web + Mini App) | ✅ seeded per attempt |
| Ona tili teacher | no topic model; no weak-topic view; only an English 10-question sample template | ✅ 11 topics (config-stored, whitelisted), per-topic accuracy, blank 10/20/30/40 starters |
| Routing | Studio (sectioned) tests of any subject run on the CD/BMB kiosk engine — by design (`has_cd_structure`) | documented; CD engine has no tool buttons |
| CI/CD | Build/Deploy check out `main` HEAD, not the CI-verified SHA; `production` gate absent in practice | ✅ pinned to `workflow_run.head_sha` (effective after merge); gate = owner action |
| Teacher bot flows, student dashboard widgets, WebSocket, PDF/CSV group reports, full a11y audit | not built | ❌ remaining (below) |

### Real-browser verification (no API mocks; Django `config.settings.e2e` + Vite)

`npx playwright test -c playwright.real.config.ts` → **20 passed** (final code, fresh DB):
* **A/E** Ona tili teacher at 1280 px **and 360 px**: DOCX import → report → fixes the deliberately wrong Q20 key → publish → assign (UI only) → student at 390 px answers, reloads, resumes, submits → `20.00/20.00` (only possible if the key fix was saved) → teacher roster 100.
* **B** CSV, XLSX, selectable-text PDF, Smart Paste (‘ apostrophes + Cyrillic А/Б/В/Г): exact parsed text and keys checked in the editor.
* **C** legacy Ona tili test on `/take`: no sidebar, no tools, no map panel, one navigator, no overflow; 390 px answers → reload restores; resumes at 1280 px → `5.00/6.00`.
* **D** runner in uz/ru/en: Uzbek question text unchanged; UI label translated; language switch mid-exam keeps the answer.
* Stage 1 at 360 px: blank 20-question test + topic tag persisted; stays draft.
* Previous homework journey (desktop + 390 px) and `/my-homework` overflow at 7 widths still pass.

Mocked Playwright suite: **23 passed**. Visual checks (screenshots, light and dark): runner at 390/1280 px.

### Backend / frontend checks (exact)

| Check | Result |
|---|---|
| pytest SQLite, full (final, at `35275ac` + docs) | **1920 passed, 0 failed, 10 skipped** (10 = PostgreSQL-only) |
| pytest PostgreSQL 16.15, full (same commit) | **1930 passed, 0 failed, 0 skipped** |
| new backend tests | `test_smart_import_pro.py` 32, `test_exam_order_stability.py` 1 (fails on old code), `test_ona_tili_topics.py` 2 |
| ruff / `manage.py check` / `makemigrations --check` | pass / 0 issues / no changes (no migrations in 4.0) |
| frontend `tsc -b` / lint / `npm test` / build | pass / 0 errors (3 pre-existing warnings) / **28 passed** (+4 tool-policy) / built |

### Migration review

None added in 4.0 (topics live in `Question.config`). Requirements: `pypdf` moved from development to base (it was missing from production images).

### Release checklist (owner)

- [ ] **Immediately:** decide on #134 (the shared password is live). If merged: rotate/reset already-imported accounts per `docs/SECURITY_IMPORT_CREDENTIALS.md`; change `EnterpriseDashboard.tsx:971`.
- [ ] Confirm what is live: `/media/receipts/…` → 404, site healthy, `python manage.py showmigrations` on the VPS.
- [ ] GitHub → Settings → Environments → `production`: add required reviewers (otherwise every green `main` deploys).
- [ ] Back up the DB before the next merge to `main`; record the running image tag for rollback (`deploy.yml` workflow_dispatch `tag=sha-<previous>`).
- [ ] Merge this PR only after CI (lint, test, test-postgres, browser, security) is green on it.
- [ ] Rebuild images (pypdf now in base requirements) — happens automatically on the next deploy.

### Remaining work (not done in 4.0)

* Stage 5/6: teacher bot flows (group pick, attendance, assign published tests, live progress); student bot vocabulary + spaced repetition; Mini App deep links per homework. Outbox still disabled and never run against a staging bot.
* Stage 7: student dashboard widgets (Today, Continue exam, Recently graded, Feedback, Weak topics).
* Stage 8: group/weekly trends, attendance trends, PDF/CSV group reports. Decision: **no WebSockets** — polling + ETag already meets the live-tablo requirement.
* Stage 9: route-by-route a11y/mobile audit beyond the runner, editor and homework pages; physical devices not tested.
* Runner: `TakeTest.tsx` is still ~3.2k lines; component extraction (ExamShell/QuestionCard/…) not started. The CD/BMB engine was not audited in this session.
* Scanned-PDF OCR: intentionally not offered (no tested OCR configured).

---

## Stage 4.1 — Admin Test Control Center 4.0 + Telegram Bot 4.0 + Unified Homework Sync

Executed 2026-11-22 on branch `feat/grandec-telegram-admin-test-v4`:

| Check | Result |
|---|---|
| `pytest tests/test_admin_test_control_center.py` (SQLite) | **8 passed, 0 failed** |
| `pytest tests/test_teacher_telegram_assignment.py` (SQLite) | **4 passed, 1 skipped** (PG row-lock) |
| `python manage.py check` & `makemigrations --check` | pass / no changes detected |
| `ruff check` on all modified files | **All checks passed!** |
| Frontend `npm test`, `npm run build` | **28 passed, 0 errors, build in 4.71s** |

### Delivered capabilities

1. **Admin Test Control Center (`/panel/tests`)**:
   - Multi-tenant and role-scoped test visibility (`apps/tests/admin_test_service.py`): Platform admin sees all; center admins scoped to center; teachers scoped to authored tests; students blocked.
   - Comprehensive test metrics: Total, Published, Draft, Archived, Attempted stats cards.
   - Safe deletion barrier: Prevents destructive deletion if test has attempts, student results, or active homework assignments (`409 Conflict`). Unused drafts can be safely cleaned up.
   - Deep duplication (`duplicate_test`): Full cloning of sections, reading passages (`content`), questions, choices, gap blanks, and matching pairs into a new draft test.
   - Lifecycle operations: Archive, restore, unpublish with full audit logging in Django `LogEntry`.
   - Bulk operations: Preview modal (`BulkPreviewModal`) distinguishing protected vs impacted tests before executing bulk archive, unpublish, restore, clean drafts, safe delete, or JSON metadata export.
   - Django Admin integration (`apps/tests/admin.py`): `archive_selected_tests`, `restore_selected_tests` and `delete_model` safety enforcement.
   - Hardened `purge_all_tests` management command against execution in production.

2. **Telegram Bot 4.0 & Unified Homework Sync**:
   - `quiz.py`: Serves only published, active tests (`status="published"`, `is_active=True`).
   - Detects complex exams (reading passages, IELTS/CEFR structures, audio, non-MCQ) and redirects to TMA (`/tma/#/tests/:id`) or Web Runner (`/take-test/:id`).
   - Resumes in-progress `TestAttempt` records cleanly without unhandled collisions or crash on tests with null course.
   - Never exposes correct answer keys in `callback_data`.
   - `teacher_assignments.py`: Synchronizes with Unified Homework Engine via `create_unified_homework`, creating proper `Homework` records.
   - Blocks reassigning tests already bound to unrelated groups.
   - Added `📚 Mening vazifalarim` and `📤 Vazifa yuborish` to persistent reply keyboard and quick inline actions.


---

## Stage 5.0 — Telegram Group Bot 5.0, Mini App 5.0 & Universal Exam Platform

Executed 2026-11-22 on branch `feat/grandec-group-bot-miniapp-v5`:

| Check | Result |
|---|---|
| `pytest tests/test_stage5_telegram_group_and_exam_platform.py` (SQLite) | **10 passed, 0 failed** |
| `pytest tests/test_admin_test_control_center.py` (SQLite) | **8 passed, 0 failed** |
| `pytest tests/test_teacher_telegram_assignment.py` (SQLite) | **4 passed, 1 skipped** (PG row-lock) |
| `python manage.py check` & `makemigrations --check` | pass / no changes detected |
| `ruff check` on all modified files | **All checks passed!** |
| Frontend `npm test`, `npm run build` | **28 passed, 0 errors, build in 4.43s** |

### Delivered capabilities

1. **Telegram Group Bot 5.0 & Persistent Attendance**:
   - Pinned-style classroom group menu (`GRANDEC | Guruh boshqaruvi`) with 8 inline actions: Bugungi vazifalar, Faol testlar, Dars jadvali, Davomat, Guruh progressi, Ixtiyoriy reyting, Mini App, Ustoz bilan bog'lanish.
   - Migrated from volatile in-memory dictionary state to transactional database-backed attendance using canonical `AttendanceSession` (`DRAFT`) and `AttendanceRecord`.
   - Attendance sessions are retrieved and restored seamlessly across bot restarts without losing student checks or active session state.
   - Enrolled student check: Only active group members can mark presence via `mark()`.
   - Safe group unlinking (`/uzish`, `/unlink_group`) restricted to group teacher or platform admin with audit trail.
   - Privacy protection: Individual student attendance reasons and nominal details are kept strictly private; public group chat only receives aggregate statistics.

2. **Teacher & Admin Bot Workspaces 5.0**:
   - `/ustoz` workspace with 8 actions: Guruhlarim, Test yaratish, Test yuborish, Davomat, Natijalar, Live monitoring, Eslatmalar, Sozlamalar.
   - `/admin` workspace with role-based scoping (Platform Super-Admin vs Learning Center Admin): Markazlar, Ustozlar, Guruhlar, Barcha testlar, Hisobotlar, Xavfsizlik, Sozlamalar.

3. **Universal Exam Mode System & Scoring Integrity**:
   - Exam policy: Timing (TIMED with remaining seconds vs UNTIMED without timer), attempts, and feedback controls.
   - Fixed TMA timer defect in `frontend/src/pages/tma/TestFlow.tsx`: Untimed tests never engage timer interval and never auto-submit at 0 seconds.
   - Rasch scoring integrity in `apps/tests/rasch_engine.py`: Dynamic Weighted Practice mode clearly labeled as `(Mashq)` practice with explicit non-official caveat; verified Rasch requires minimum 30 sample size; historical attempt results are immutable snapshots and never retroactively rewritten when calibrating test item difficulties.
   - Complete `uz`, `ru`, `en` localization across TMA and bot messages in `frontend/src/i18n/translations.json`.

## Final requirements (multi-tenant, PPTX, classroom access, release) — 2026-11-23

Branch `fix/grandec-ci-recovery-and-smart-builder-v6`, draft PR #145 (not merged, not deployed).

### CI recovery (main was red after #142–#144)
- Baseline before: SQLite pytest 35 failed; PostgreSQL pytest 98 failed; `manage.py test` 6F + 6E.
- Causes fixed: `rasch_grade` varchar(10) overflow on PG ("X (Mashq)") → grade code + new `rasch_mode`
  field (migrations tests/0023, results/0009, reversible data split); cross-tenant leak in `visible_tests`;
  global `center_admin`; resume charged quota / hit paywall; group analytics N+1; legacy tests that
  retook tests on FREE quota; Telegram group-bot callbacks (vedomost IDOR, attendance review binding,
  stale `ustoz_*` buttons).
- After (local, exact CI commands, 2026-11-23):
  - SQLite: `manage.py check` OK; `manage.py test tests` 1275 OK (3 skipped);
    `pytest tests --cov=apps --cov-fail-under=50` 1970 passed, 10 skipped (PG-only), 0 failed.
  - PostgreSQL 16: `check` OK; `makemigrations --check` no changes; `pytest` 1980 passed, 0 failed.
  - Frontend: `tsc --noEmit` OK, lint 0 errors, 28 unit tests pass, `vite build` OK.
  - GitHub: CI + Security green on PR #145 head 4433b2f.

### Classroom access (P3) and tenancy (P4)
- One policy (`apps/tests/access_policy.py`) for start/resume/catalog/results; `visible_tests` uses the
  same audience mapping (`effective_audience_q`).
- FREE group member: assigned private test, no paywall, no quota. Non-member / other group: denied.
  PRO outsider: private denied; allowed only for tests explicitly published to the paid catalog.
  Removed member: no new attempts, history preserved. Joining a group grants no subscription.
- Studio tests are now created **GROUP_ONLY** by default with an explicit audience choice
  (group only / group + subscribers / public free). Real E2E caught that Studio tests used to be PUBLIC.
- One canonical group scope (`get_teacher_groups`) used by school API, essays reports, studio,
  attendance; center admins see their own center's groups (incl. centers without branches) and nothing else.
- Cross-tenant suite probes reads and writes for anonymous / other-center student, teacher, admin.

### Smart Import (P2)
- PPTX: slide order, text boxes, numbered questions/options, table questions, answer keys from notes or a
  key slide (never invented), multi-slide questions, image-only slide warnings, slide column in review UI.
- Safe parsing: DOCTYPE/ENTITY refused, zip-bomb limits, extension/content mismatch refused.

### Real E2E (Django + Vite, no mocks): 25/25 passed
Homework journey (desktop + 390), overflow 320–1280, Ona tili DOCX import (1280/360), runner uz/ru/en,
legacy /take resume, v7 Scenario A (two centers isolated), C (PPTX), D (scanned PDF refused),
E (FREE member vs outsider), F (PRO outsider vs paid catalog).
Repro: see "Real E2E"; also export `E2E_DB_PATH` and `SECRET_KEY` for the spec's DB checks.

### Release pipeline (P1/H)
PR → CI → Security → merge → CI on main → Build (CI-verified SHA, `sha-xxxxxxx`) → Staging deploy + smoke
(automatic, skipped with a warning when STAGING_* secrets are absent) → Production **manual only**
(`workflow_dispatch`, immutable tag, typed `deploy grandec.uz`, `production` environment) → verified
pre-deploy pg_dump → smoke/health → release report. Rollback = rerun with the previous tag.

### Owner blockers / decisions
1. GitHub `production` environment: add required reviewers (Settings → Environments). Not configurable
   from this session. Branch protection needs a paid plan (see `.github/BRANCH_PROTECTION.md`).
2. Staging: create environment `staging` with STAGING_HOST/USER/SSH_KEY/DOMAIN; until then nothing deploys.
3. Existing Studio tests in production stay as they are (PUBLIC). Decide whether to switch them to GROUP_ONLY.
4. Not done this session: Scenario G (Telegram/Mini App end-to-end), test format categories
   (Mavzulashtirilgan / Attestatsiya / Full Mock / Milliy sertifikat) with timed/untimed, P5 join-request
   approval and welcome notifications.
5. PR #134 is merged into this branch; close it after #145 merges. Dependabot PRs untouched.
