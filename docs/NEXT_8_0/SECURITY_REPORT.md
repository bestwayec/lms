# GRANDEC NEXT 8.0 — Security & Authorization Report

## Security Controls & Verified Invariants
1. **Multi-Role RBAC Separation (`multi-role-auth-guardian`)**:
   - Student-only practice & attempt routes block cross-student access (`403` / `404`), including `AttemptSpeakingUploadView` (`select_for_update()` scoped to `student=request.user`).
   - Teacher routes (`/api/v1/english/teacher/workspace/`, `/api/v1/english/teacher/export/`, `/api/v1/essays/teacher/<id>/`, `/api/v1/speaking/teacher/<id>/review/`) verify role (`teacher`/`admin`/`center_admin`) AND active group/assignment ownership; students and unrelated teachers receive `403`.
   - Admin AI Cost Control endpoint (`/api/v1/panel/ai-metrics/`) strictly requires `IsPanelAdmin`; students and teachers receive `403`.
2. **Private Media & Audio Access Isolation (`apps/webapi/views_private_files.py`, `apps/core/private_files.py`)**:
   - Listening audio and Speaking recordings never expose public `/media/` paths.
   - HTTP `Range` (`206 Partial Content`) requests stream chunks cleanly without inflating replay counters.
   - Student speaking recordings remain hidden (`404`) from teachers unless submitted for teacher review or tied to a mock exam (`teacher_review_requested=True`, `status=PENDING_TEACHER`, or `teacher_reviewed_by == user`).
3. **Answer-Key & Stimulus Leakage Prevention**:
   - Student exam payloads (`_student_question_payload`), keyless exam templates (`studio_package_export_view` with `?template=1`), student Vocabulary quizzes (`student_vocab_quiz_view`), and Grammar exercises (`grammar_topic_detail_view`) never expose `correct_answer`, `accepted_keys`, or `is_correct`.
   - Listening transcripts and `audio_start_sec` cues and Reading `evidence_text` are stripped during live strict mock exams and revealed only in post-submit review.
4. **Formula-Injection-Safe Exports (`apps/core/spreadsheet.py`)**:
   - English cohort `CSV` and `XLSX` exports (`TeacherEnglishExportView`) sanitize every cell via `safe_row()` so payloads starting with `=`, `+`, `-`, `@`, `\t`, `\r`, `\n` are prefixed cleanly (`tests/test_next8_phase12_teacher_workspace.py`).
5. **Shared-Browser Logout Draft & Token Scrubbing (`frontend/src/lib/api.ts`)**:
   - `clearTokens()` removes `lms_access`, `lms_refresh`, plus all cached exam answers/positions/flags/highlights/notes (`cd-exam:*`, `cd-pos:*`, `cd-flags:*`, `cd-highlights:*`, `cd-notes:*`, `exam_queue_*`, `writing_studio_draft_*`).
6. **Telegram Mini App Auth & CSRF (`apps/telegram_app/`)**:
   - Reuses HMAC-SHA256 `initData` signature verification, immutable `telegram_chat_id` matching, and NEXT 7.0 session CSRF protection.
7. **Zero Secret Leakage & Clean Human Authorship**:
   - Zero hardcoded API keys, credentials, or AI attribution notices in code, docs, or commits.
