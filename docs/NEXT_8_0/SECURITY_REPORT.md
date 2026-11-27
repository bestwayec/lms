# GRANDEC NEXT 8.0 — Security & Authorization Report

## Security Controls & Verified Invariants
1. **Multi-Role RBAC Separation (`multi-role-auth-guardian`)**:
   - Student-only practice & attempt routes block cross-student access (`403` / `404`).
   - Teacher routes (`/api/v1/english/teacher/workspace/`, `/api/v1/english/teacher/export/`, `/api/v1/essays/teacher/<id>/`, `/api/v1/speaking/teacher/<id>/review/`) verify role (`teacher`/`admin`/`center_admin`) AND active group/assignment ownership; students receive `403`, and unrelated teachers receive `403`.
   - Admin AI Cost Control endpoint (`/api/v1/panel/ai-metrics/`) strictly requires `IsPanelAdmin`; students and teachers receive `403`.
2. **Private Media & Audio Access Isolation (`apps/webapi/views_private_files.py`, `apps/core/private_files.py`)**:
   - Listening audio and Speaking recordings never expose public `/media/` paths.
   - HTTP `Range` (`206 Partial Content`) requests stream chunks cleanly without inflating replay counters.
   - Student speaking recordings remain hidden (`404`) from teachers by default unless explicitly submitted for teacher review (`teacher_review_requested=True` or `status=PENDING_TEACHER` or `teacher_reviewed_by == user`).
3. **Answer-Key & Stimulus Leakage Prevention**:
   - Student exam payloads (`_student_question_payload`), keyless exam templates (`studio_package_export_view` with `?keyless=1`), student Vocabulary quizzes (`student_vocab_quiz_view`), and Grammar exercises (`grammar_topic_detail_view`) never expose `correct_answer`, `accepted_keys`, or `is_correct`.
   - Listening transcripts and `audio_start_sec` cues and Reading `evidence_text` are stripped during live strict mock exams and revealed only in post-submit review.
4. **Formula-Injection-Safe Exports (`apps/core/spreadsheet.py`)**:
   - English cohort CSV exports (`TeacherEnglishExportView`) sanitize every text cell with `safe_row()` so payloads starting with `=`, `+`, `-`, `@`, `\t`, `\r`, `\n` are prefixed with `'` (verified with `=HYPERLINK(...)` and `=CMD|...` test vectors in `tests/test_next8_phase12_teacher_workspace.py`).
5. **Telegram Mini App Auth & CSRF (`apps/telegram_app/`)**:
   - Reuses HMAC-SHA256 `initData` signature verification, immutable `telegram_chat_id` matching, and NEXT 7.0 session CSRF protection (`tests/test_next7_phase1_api_and_csrf.py`).
6. **Sanitized Logging & Input Hardening**:
   - Zero secret keys, tokens, or bot credentials committed or logged; zero AI attribution footers in code, docs, or commits.
