# GRANDEC NEXT — Phase 0 architecture audit, gap matrix and implementation ledger

Status: **Phase 0 (audit + baseline recovery)**. Branch `claude/confident-carson-3pxsj4`, based on `origin/main` @ `3a5f777`.
Nothing here was deployed. No production database, Telegram chat, paid AI endpoint or secret was touched.

> `CLAUDE.md` still points to `docs/FIX_PLAN.md` for sequencing. The GRANDEC NEXT programme was explicitly requested for
> this session and supersedes it; `FIX_PLAN.md` is untouched.

---

## 1. Method and evidence limits

* Local repo inspected directly (models, services, URLs, handlers, tests, CI, nginx, settings).
* BESTWAY (`bestwayec/bestway`) was read **from a shallow clone at `25f624b` (merge of #211)**, which includes the code and docs of
  #209–#211 (`docs/TEACHER_WORKSPACE_2.md`, `docs/TELEGRAM_BOT_2_RELEASE.md`, `backend-django/apps/core/{class_quiz,telegram_outbox,
  telegram_notify,telegram_teacher,telegram_quiz,vocabulary_bot,result_card}.py`). **The PR threads themselves (review comments,
  discussion) were not readable** — the GitHub tools in this session are scoped to `bestwayec/lms`. Concepts below come from the merged code and docs.
* Not verifiable here: real Telegram delivery, real devices, production data, GitHub Actions runs (CI was reasoned about from its YAML).

## 2. Repository and branch state

| Check | Result |
|---|---|
| Working tree at start | clean |
| Local branch | `claude/confident-carson-3pxsj4` == `origin/main` (`3a5f777`) |
| Open PRs | #134 (draft security), #72–#80 dependabot (8 pip/actions bumps) |
| Remote feature branches | `feat/favicon-ot`, `feat/grandec-v2-master`, `feat/mobile-ux-redesign-v6-stage1`, `feat/multi-subject-branches-v3`, `fix/deploy-v054-compose`, `fix/essay-react-grading` (all pre-existing, not touched) |
| Migrations | 142 migration files over 25 apps; `makemigrations --check` → *No changes detected* |
| PR #134 | `security/enterprise-import-unique-credentials-20261120`, based on current `main`, 4 files (`csv_import.py`, `organizations/views.py`, a doc, a test). **Not modified, not merged.** It overlaps with nothing in this PR. See §7. |

## 3. Baseline (exact commands and results)

Environment: Python 3.13, Node 22, venv `/tmp/claude-0/venv` from `requirements/development.txt`
(the container's Debian `setuptools` cannot build `http-ece`; a clean venv does — an environment quirk, not a project defect).

| Suite | Command | Before this PR | After this PR |
|---|---|---|---|
| Django check / migrations | `manage.py check`, `makemigrations --check --dry-run` | OK / no changes | OK / no changes |
| Ruff | `ruff check .` | pass | pass |
| Backend, SQLite (what CI runs) | `pytest -q` (`config.settings.test`) | **1714 passed, 9 failed, 7 skipped** | **1723 passed, 0 failed, 7 skipped** (the 7 are PostgreSQL-lock tests) |
| Backend, PostgreSQL 16.15 | `pytest -q` (`config.settings.postgres_test`, disposable local cluster) | **1691 passed, 39 failed** | **1721 passed, 9 failed, 0 skipped** (9 = open items below; the 7 lock tests now run and pass) |
| Frontend lint | `npm run lint` (oxlint) | exit 0, warnings only (3 in `ScanOMR.tsx`: ref-in-render, set-state-in-effect ×2) | unchanged |
| Frontend unit | `npm test` | 24 passed | 24 passed |
| Frontend types + build | `tsc -b`, `npm run build` | OK | OK |
| Playwright (Chromium) | `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/opt/pw-browsers/chromium npx playwright test` | 19 passed, **1 failed** | **20 passed** |

### 3.1 Findings from the baseline

**Fixed in this PR (confirmed, reproduced, regression-covered by the existing tests):**

1. `tests/test_teacher_bot_commands.py` — 8 failures. The handler `_attendance_actor` correctly refuses non-private chats, but the
   fake `Update` had no `effective_chat`. Fixture now carries `effective_chat.type == "private"` (the existing group-chat test is
   unchanged and still proves refusal). One further assertion was stale: since "review and paginate attendance safely" the register shows
   `tconfirm_` (review) and only the review screen offers `tfin_`; the test now asserts that two-step flow, including that `tfin_` is
   **not** offered directly.
2. `tests/test_user_facing_messages.py` — 11 keys used by `SubjectSwitcher.tsx` / `ScanOMR.tsx` were missing from
   `frontend/src/i18n/translations.json`; added in uz / ru / en (parity test passes).
3. `frontend/e2e/quality.spec.ts` — `getByRole('combobox')` matched both the header exam-goal select and the dialog's reminder select
   (strict-mode violation). Now scoped to the dialog's *Eslatma vaqti* select.
4. **Production-relevant PostgreSQL bug (invisible to CI):** `select_for_update()` combined with `select_related()` over a nullable FK
   emits a `LEFT OUTER JOIN`, which PostgreSQL rejects (`FOR UPDATE cannot be applied to the nullable side of an outer join`).
   Affected: tuition payment verification, refund, and invoice locking (`apps/tuition/services.py` ×3, `apps/webapi/views_tuition.py` ×2) —
   **27 PostgreSQL test failures**, i.e. these flows would raise 500 on the production database. Fixed with `select_for_update(of=("self",))`
   (same row-lock semantics; related rows are not locked).
5. PostgreSQL-only test-data issues: arena room codes longer than the `varchar(10)` column; certificate test asserted the SQLite-only
   counter table (PostgreSQL uses `cert_number_seq`) — now vendor-aware while keeping the strictly-increasing assertion on both.

**Resolved after the first Phase 0 push (see `GRANDEC_NEXT_PROGRESS.md`, Stage 0 closure); the table below is the state at first audit:**

| Item | Why it is open |
|---|---|
| **CI never runs on PostgreSQL.** `ci.yml` sets `DATABASE_URL=postgres://…`, but `config/settings/development.py:33` hard-codes SQLite, so `config.settings.test` ignores it. The `FOR UPDATE` bug above therefore passed CI. | Adding a PG job is blocked until the PG-only failures below are resolved, otherwise it would be red. |
| `tests/test_seed_accounts_safety.py` ×2, `tests/test_seed_qa_accounts.py` ×1 fail on PostgreSQL | The seed commands intentionally refuse non-SQLite/non-DEBUG databases (security guard); the tests assume SQLite. Needs an owner decision (make tests settings-aware) rather than a silent skip. |
| `tests/test_audit_fixes_release.py::AuditChannelsJwtTests` ×4 and `test_interactive_results_and_tg_sync.py::test_result_vedomost_pdf_download_endpoint` fail on PostgreSQL with `connection already closed` | Channels communicator / streaming-response tests close the shared test connection; harness issue, production code not implicated. |
| `tests/test_essay_bot_submit.py::test_identical_graded_submission_returns_existing_grade` | Passes alone; fails in a full PostgreSQL run because it asserts a hard-coded row id (`'108'`) in a message. Order/sequence dependent. |
| 7 skipped tests (row-lock / advisory-lock) | Skipped on SQLite by design. Under `postgres_test` they **execute and pass** (0 skipped in the PostgreSQL run). |

## 4. Current architecture (as found)

### 4.1 Backend (Django 5.2 + DRF, Celery/Redis, PostgreSQL in prod, SQLite in dev/CI)

| App | Role (≈ LOC) | Relevant to NEXT |
|---|---|---|
| `accounts` (5k) | `User` (roles student/teacher/admin/…, Telegram identity fields), JWT, CSV import | auth, linking |
| `courses` (1.3k) | `StudentGroup`, `GroupEnrollment` (CRM/fees), **`Homework` / `HomeworkSubmission`** | group + homework base |
| `groups` (0.3k) | compatibility re-export of `courses.StudentGroup` | — |
| `attendance` (2.5k) | `AttendanceSession` (unique per group/date/start_time → several lessons a day), `AttendanceRecord` (PRESENT/ABSENT/LATE/**EXCUSED**, `late_minutes`, `note`), `AttendanceAuditLog`, observations, notification destinations, `NotificationPreference` | Teacher Workspace |
| `tests` (25k incl. tests) | `Test`, `ExamSection/Part`, `Question…`, **`TestAttempt`**, `StudentAnswer`, services (`SaveAnswerService`, `SubmitAttemptService`), scoring (BMB, CEFR multilevel, IELTS scales, Rasch), OMR, studio | exam engine |
| `results` (3k) | `Result`, `ResultSectionScore`, `Certificate`, PDF vedomost | results |
| `essays` (10.7k) | `EssayTopic`, `EssayAssignment`, `EssaySubmission`, async AI grading | essay tasks |
| `vocabulary` (0.6k) | `VocabularyPack`, `StudentWordMistake` (Ebbinghaus `next_review_at`, 3-streak mastery) | vocab / SRS |
| `notifications` (15.7k) | `NotificationLog` (audit + unique `dedup_key`), `TelegramAuthToken`, the **bot** (`bot/handlers.py` 10k lines, `group_assistant.py`, `quiz.py`, `teacher_assignments.py`), Celery tasks with retry/backoff | Telegram |
| `telegram_app` (1.9k) | Mini App (TMA) API | Mini App |
| `webapi` (10k) | the React-facing DRF views (attendance, dashboard, panel, branches, tuition…) | API layer |
| `tuition`, `payments`, `subscriptions`, `billing` | fees / receipts / plans | security (files) |
| `organizations` | centers / enterprise accounts, CSV import | tenancy |
| `speaking`, `arena`, `games`, `weekly_reports`, `certificates`, `panel`, `web`, `core`, `bot` (CRM/quota) | other modules | — |

Bot framework is **python-telegram-bot ≥22.8** (not Aiogram as `CLAUDE.md` says — correct `CLAUDE.md` when convenient).

### 4.2 Frontend (React + TS + Vite, `frontend/src`)

* Routing in `App.tsx`: public → `ProtectedRoute` → `Layout`; `TeacherRoute`, `ParentRoute`, `NotForAdminRoute` guards.
* Teacher area today: `/teacher` (`TeacherDashboard`), `/teacher/studio*`, `/teacher/ai-converter`, `/teacher/vocab-generator`,
  `/teacher/finance`, `/teacher/essays*`, `/groups` (`Groups`), `/analytics`, `/import`. **`/attendance` redirects to `/panel`.**
  Attendance UI exists only as the embedded `components/AttendancePanel.tsx` (634 lines) inside group/teacher/panel pages.
* Student area: `/dashboard`, `/tests*`, `/essays*`, `/results*`, `/arena`, `/speaking*`, `/groups/:id`. **No "my homework" route.**
* i18n: `i18n/translations.json` (uz/ru/en, 3108 keys each, parity enforced by `tests/test_user_facing_messages.py`).
* Tests: `node --test` unit (24), Playwright `e2e/quality.spec.ts` (mocked API, 20 cases).

### 4.3 Exam engine facts that constrain the unified layer

* `TestAttempt`: `IN_PROGRESS → COMPLETED | TIMEOUT | PENDING_GRADING | CANCELLED`, `PENDING_GRADING → COMPLETED` (idempotent finalize). Time limit lives on `Test.time_limit_minutes`; deadline is computed server-side from `started_at` (`is_expired`, remaining-time helpers). Endpoints: `tests/<id>/start/`, `attempts/<id>/save-answer|save-batch|submit|finalize`.
* `Test.max_attempts`, `Test.access_pin` (4-digit), `Test.status/is_active`, **`Test.assigned_group` is a single FK** — one test can belong to only one group.
* A guard against answer-key leaks exists (`tests/test_exam_no_key_leak.py`).
* Scoring is per exam type (BMB, CEFR multilevel, IELTS scales). **No second grader may be introduced.**

### 4.4 Notifications today

* `NotificationLog` = immutable audit row with a unique `dedup_key`; sending is done by Celery tasks (`max_retries=3`, exponential backoff) and
  by inline handlers. There is **no queue/outbox**: no lease, no per-recipient quiet hours, no scheduled-for, no per-kind mute, no retry
  ceiling stored on the row, no worker that can be switched off independently of business code.
* `attendance.NotificationPreference` has opt-outs for attendance/essay/test/observation kinds (per user).

## 5. Gap matrix vs BESTWAY #209–#211

Legend: ✅ present · 🟡 partial/inadequate · ❌ missing · ⚠ broken/duplicated

### 5.1 Teacher Workspace (BESTWAY: `TEACHER_WORKSPACE_2.md`)

| Capability | BESTWAY | GRANDEC today | Gap |
|---|---|---|---|
| Teacher home with 4 primary actions + overview | ✅ | ❌ `/teacher` is a dashboard of tools; no 4-action home, no "today/awaiting/deadlines" overview endpoint | build |
| One-screen attendance | ✅ present/absent/late | 🟡 backend full (sessions, late minutes, notes, audit, finalize); UI is an embedded panel, route redirects away | new page over existing services |
| EXCUSED status | ❌ (needs schema) | ✅ already in model | keep (improvement over BESTWAY) |
| Several lessons/day | ❌ per-day | ✅ unique on `(group, date, start_time)` | keep |
| Explicit "all present", never prefilled | ✅ | ✅ `mark_all_present` explicit; finalize returns 409 while unmarked | verify in UI |
| Optimistic concurrency on save (409) | ✅ `revision` → `ATTENDANCE_CHANGED` | ❌ last-write-wins in `mark()`; no revision | **add** (no schema change needed if derived from `max(updated_at)`+count; a column is optional) |
| Group-scoped, center-scoped student search | 🟡 reuses group page | 🟡 `teacher_groups()` exists; need to audit the search endpoints for cross-center leakage | audit (Phase 1/2) |
| Membership history | ❌ | ❌ M2M `students` + `GroupEnrollment` only; no joined/left history | **add** (additive model) |
| Dashboard overview (today's lessons, attendance, homework, queue, deadlines) | ✅ | ❌ | build (real queries only) |

### 5.2 Homework / unified assignment layer

| Capability | BESTWAY | GRANDEC today | Gap |
|---|---|---|---|
| Assign grammar quiz / vocab / exam / lesson to a group, one click, idempotent | ✅ 4 kinds | ⚠ `courses.Homework(group,test|essay_topic,due_date)` exists and is written by the bot (`/new_homework`) and vocab "assign" view, but **`HomeworkSubmission` is never created or read by any view** (only a purge command) — student side does not exist. Separately `Test.assigned_group` (single group) is what the Telegram "assign test" flow uses. **Two disconnected assignment mechanisms.** | unify (§6 design) |
| Student "Mening vazifalarim" with real statuses | ✅ | ❌ | build |
| Server-owned timer, per-answer persistence, resume, idempotent finish | ✅ (ClassQuiz) | ✅ for `TestAttempt` (start/save-answer/save-batch/submit/finalize, server deadline) | reuse; wrap with assignment context + deadline/late rules |
| Grammar quiz authoring (MCQ/TF/short answer) | ✅ ClassQuiz | 🟡 Teacher Studio + AI converter create tests; no lightweight "paste questions + key" path; short-answer matching rules unknown | audit then decide reuse of `Test`+`Question` types |
| Published IELTS/CEFR/National assessments as homework | ✅ published only | 🟡 tests are assignable; draft/published rules must be enforced for assignment | enforce |
| Deadlines, attempt limits, cancel, revision history, snapshots | partial | ❌ | design |
| Key visibility rules (`keysVisible`) | ✅ | ✅ key-leak test exists; assignment layer must reuse it | reuse |
| Removed students keep results | ✅ | needs verification once membership history exists | test |

### 5.3 Telegram Bot

| Capability | BESTWAY | GRANDEC today | Gap |
|---|---|---|---|
| Secure linking, role menus | ✅ | ✅ `telegram_identity_verified_at`, token/phone-link hardening, parent invites (PRs #131/#132) | verify only |
| Teacher: group pick, attendance | ✅ | ✅ private-chat only, ownership-checked, two-step finalize | extend with revision/409 |
| Teacher: assign / monitor | ✅ | 🟡 assigns a *test* to one group (`Test.assigned_group`); no assignment kinds, no monitoring | on unified layer |
| Student: quizzes, vocab/SRS in bot | ✅ modes A–E, SRS | 🟡 `quiz.py` (generic quiz) and a `/vocab` command (`handlers.py:9923`: today's 5 hardest words from `StudentWordMistake`, Ebbinghaus `next_review_at`); no assigned-pack practice modes | extend on `StudentWordMistake` + assigned packs |
| Result cards from stored results | ✅ (Pillow) | ❌ | build, from `Result` only |
| **Durable outbox** (dedupe, retry limit, lease, quiet hours, opt-out, mute kinds) | ✅ `TelegramOutbox` + worker, opt-in | ❌ only `NotificationLog` + Celery retries | **build; worker disabled by default** |
| Homework assigned / deadline / missed / result-ready notices | ✅ | ❌ | on outbox |
| Mini App for long exams | ❌ | 🟡 `/tma` + `telegram_app` exist; scope to be audited | audit |
| No public grade disclosure / no bulk broadcast | ✅ | ✅ hardened in #131 (private cards only, group aggregate summaries need admin-approved destination) | keep |

### 5.4 Results and analytics

| Capability | GRANDEC today | Gap |
|---|---|---|
| Per-assignment: assigned / submitted / unsubmitted / awaiting review / graded / average | ❌ (per-test gradebook + item analysis exist) | build over assignment layer |
| Pending vs graded-zero distinction | model supports `PENDING_GRADING`; no assignment-level status | build |
| Per-student mistakes (`mistake-vault`, `explain-mistake`), weak-topic | 🟡 student-side only | teacher view |
| CSV/PDF export w/ formula protection | 🟡 `panel/attendance/export/`, vedomost PDF; formula-injection protection not verified | audit + test |
| Calendar/scheduling | ❌ (`AttendanceSession.start_time` only) | Phase 5 |

## 6. Proposed design (for Phases 2–4; to be reviewed before coding)

1. **`assignments` app (additive).** `Assignment` (kind: `TEST`, `VOCABULARY`, `ESSAY`, `LESSON`; target group and/or individual users; owner teacher; center; `publish_at`/`due_at`; `time_limit`, `max_attempts`; state `DRAFT/PUBLISHED/CANCELLED`; `idempotency_key`; frozen `snapshot` JSON of title/source ids/settings), `AssignmentRevision` (append-only), `AssignmentRecipient` (student, state, `removed_at` — keeps history), `AssignmentSubmission` (links to **existing** `TestAttempt` / `EssaySubmission` / vocab run, never copies scores).
2. **Status is derived, never typed in by hand:** from linked attempt/submission + deadline → `NOT_STARTED, IN_PROGRESS, SUBMITTED, AWAITING_REVIEW, GRADED, OVERDUE, CANCELLED`. Score comes only from `Result`/essay grade; `GRADED` with 0 ≠ `AWAITING_REVIEW`.
3. **Migration of existing data:** `courses.Homework` rows are back-filled into `Assignment` by a reversible data migration; `HomeworkSubmission` rows (none are written today) are carried over if present; `Homework`/`Test.assigned_group` keep working until callers are moved (no deletions).
4. **Outbox:** `TelegramOutbox` (dedupe key unique, `status`, `attempts`, `max_attempts`, `lease_until`, `not_before`, `kind`), worker command **not scheduled** until explicitly approved; quiet hours and per-kind mute read from preferences.
5. **Concurrency:** attendance saves carry a `revision` (token derived from the session's records); stale → HTTP 409 with the fresh sheet; the client keeps local edits.
6. **Authorization:** one helper per scope (`teacher_groups`, center scope) reused by every new endpoint; tests per role/center.

## 7. Phase 1 — security findings queue (evidence-based; not yet fixed)

| # | Finding | Evidence | Severity (initial) | Plan |
|---|---|---|---|---|
| S1 | Payment receipts, tuition proofs and speaking audio are served by nginx under `/media/` **without authentication**, with `Cache-Control: public, max-age=2592000`; serializers/views return `.url` | `deploy/nginx/nginx-ssl.conf:145`, `nginx.conf:13`, `webapi/serializers.py:384`, `speaking/views.py:55`; models: `payments.receipt_image`, `tuition.proof`, `speaking.audio_file` | **High** (privacy; unguessable-name not guaranteed, original filenames kept) | private storage + authenticated download views / `X-Accel-Redirect`; keep public media (avatars, topic images) separate |
| S2 | Imported student credentials were shared/plaintext | **PR #134** (draft, 4 files, based on current main) | High | **Reuse #134 as-is** (review + merge by owner); only add follow-ups for already-issued credentials (ops procedure in its doc). Do not duplicate. |
| S3 | `Test.access_pin` is a 4-digit PIN — brute-force/throttle behaviour unverified | `tests/models.py:237` | Medium | verify throttling on start endpoint; add tests |
| S4 | CI does not exercise PostgreSQL (see §3.1) — row-lock/concurrency regressions are invisible | `development.py:33` vs `ci.yml` | Process / High-impact | PG job after harness fixes |
| S5 | JWT / CSRF / Google OAuth handling | Access **and refresh** tokens are kept in `sessionStorage` (`frontend/src/lib/api.ts:24-36`), i.e. readable by any XSS; mitigations present: 60-min access, 7-day refresh with rotation + blacklist (`base.py:338`), production `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`/HSTS (`production.py:60-72`). `CSRF_COOKIE_HTTPONLY=False` by design. Google OAuth handling **not yet located/reviewed** | Medium (needs CSP/XSS review to rate) | focused review in Phase 1; no change proposed yet |
| S6 | Cross-center / cross-teacher access, draft exam access, enterprise onboarding | not yet audited | Unknown | audit endpoint by endpoint with negative tests |

No finding in this table is claimed fixed except where §3.1 says so.

## 8. Prioritized implementation ledger

| ID | Phase | Item | Size | Depends on | Status |
|---|---|---|---|---|---|
| P0-1 | 0 | Telegram attendance fixtures + stale two-step assertion | S | — | ✅ done |
| P0-2 | 0 | 11 missing i18n keys (uz/ru/en) | S | — | ✅ done |
| P0-3 | 0 | Playwright ambiguous combobox selector | S | — | ✅ done |
| P0-4 | 0 | PostgreSQL `FOR UPDATE` + outer-join bug in tuition (5 sites) | S | — | ✅ done |
| P0-5 | 0 | PG-only test-data fixes (arena codes, certificate counter) | S | — | ✅ done |
| P0-6 | 0 | PG job in CI; resolve seed/Channels/streaming/essay-id harness failures | M | — | ✅ done (see `GRANDEC_NEXT_PROGRESS.md`) |
| P0-7 | 0 | Correct `CLAUDE.md` (python-telegram-bot, not Aiogram) | S | owner | open |
| P1-1 | 1 | Private storage + authenticated download for receipts/proofs/speaking audio (S1) | M–L | deploy change (nginx) needs owner approval | open |
| P1-2 | 1 | Review/merge PR #134 (S2) | — | owner | open |
| P1-3 | 1 | PIN throttle, draft-exam access, cross-center negative tests (S3, S6) | M | — | open |
| P1-4 | 1 | JWT/CSRF/Google review (S5) | M | — | open |
| P2-1 | 2 | Attendance `revision` + 409 on stale save (service + API + Telegram) | M | — | open |
| P2-2 | 2 | Group membership history model + migration | M | — | open |
| P2-3 | 2 | Teacher workspace overview endpoint (real queries) | M | P3 data for homework metrics | open |
| P2-4 | 2 | Teacher home + one-screen attendance + group management UI (uz/ru/en, mobile-first, light/dark) | L | P2-1..3 | open |
| P3-1 | 3 | `assignments` app + data migration from `courses.Homework` | L | design review | open |
| P3-2 | 3 | Student "Mening vazifalarim" + run/resume/submit via existing `TestAttempt` | L | P3-1 | open |
| P3-3 | 3 | 3-step assignment wizard (teacher) | L | P3-1 | open |
| P4-1 | 4 | `TelegramOutbox` + worker (disabled) + preferences (quiet hours, mute) | L | — | open |
| P4-2 | 4 | Notices (assigned, reminder, missed, result-ready) via outbox; private result card from `Result` | L | P3, P4-1 | open |
| P5-x | 5 | Teacher results dashboard, weak-topic analysis, safe CSV/PDF export, calendar | XL | P3 | open |
| P6-x | 6 | Full QA incl. the 20-question Passive Voice journey, PG concurrency, Playwright desktop/mobile | L | all | open |

## 9. Compatibility and risk notes

* All Phase 0 code changes are test/fixture/i18n/lock-clause changes; **no migration, no API change, no data change.**
* `select_for_update(of=("self",))` is supported on PostgreSQL (and ignored by SQLite); locking behaviour for the primary row is unchanged.
* Remaining blockers for production claims: PG not in CI; S1 unfixed; real-Telegram/real-device checks need an authorized staging bot.

## 10. Phase 0 files changed

`apps/tuition/services.py`, `apps/webapi/views_tuition.py`, `frontend/e2e/quality.spec.ts`, `frontend/src/i18n/translations.json`,
`tests/test_arena_ws_reconnect.py`, `tests/test_high_regressions.py`, `tests/test_teacher_bot_commands.py`, `docs/GRANDEC_NEXT_ARCHITECTURE.md`.
