# GRANDEC 4.0 product readiness matrix

Checkpoint: 2026-11-13. Scope is local, isolated verification; no production readiness is implied. VERIFIED applies only to the narrow behavior described, not the whole module. Earlier evidence is in TELEGRAM_SECURITY_2026-11-12.md and PRODUCTION_QUALITY_2026-11-12.md; it is not substituted for current execution.

| Workflow | Status | Current evidence / tests | Remaining risks / next gate |
| --- | --- | --- | --- |
| Recover security branch | VERIFIED | Git refs and PR HTML agree on initial head c3499e9e394be57c6b32fa7c77558e986c93f605; PR #131 DRAFT; initial Checks page shows all six jobs succeeded | Recheck final pushed commit |
| Preserve earlier fixes | VERIFIED | Continued directly from c3499e9; eight security commits remain ancestors; no reset/rebase | Full security audit still required |
| Main integration | PARTIAL | main 45b98f0e3db55a9244a474fe1656c647de1de4c0; only release commit and #130 merge absent from security branch | No functional main changes require integration for this checkpoint |
| Telegram identity / linking | PARTIAL | Current focused security tests and PostgreSQL tests exercise legacy raw-ID rejection and verified actors | Review every login/session/recovery/unlink path |
| Teacher / group authorization | PARTIAL | Ownership, private reports, binding and CRM callback regressions | Complete command/callback inventory; center admin scope |
| Automatic individual group disclosures | VERIFIED | Legacy test/essay/speaking broadcast paths generate no PDF and send nothing; duplicate/redelivery regressions | Intentional behavior change: no automatic group scorecards |
| Private test / essay notifications | PARTIAL | Existing paths retained; completion integration tests continue | Current account status, retries and concurrent idempotency audit incomplete |
| Speaking notification | PARTIAL | Persisted result remains on protected speaking page; unsafe legacy group job safely skips | Build reliable private notification; no replacement delivery claimed |
| Report storage / download | PARTIAL | Student/essay/speaking PDFs use random private temporary files; tests check 0600, PDF bytes and no MEDIA_ROOT output; student endpoint deletes file and prevents caching | Generator failures can leave private temporary files; bounded cleanup policy needed; historical public files need inventory |
| Historical public PDFs | BLOCKED | Remediation plan in PRODUCTION_READINESS_4_0.md | Authorized production inventory and operator-approved remediation |
| Grade overrides | PARTIAL | Legacy Telegram writes remain disabled and tested | Web override authorization, audit, transaction, idempotency and concurrent writes |
| Guardian invitations | PARTIAL | Expiry/replay/revocation/scope and PostgreSQL concurrency tests | Complete notification and relationship-removal audit; reissue legacy links |
| Webhook / Mini App authentication | PARTIAL | Prior hardening retained | Complete replay, duplicates, freshness, CSRF, logging and rate-limit review |
| Bot commands / callback navigation | PARTIAL | Existing handlers retained | Full handler inventory, registration tests, cancellation/recovery UX |
| Student onboarding / menu / profile | PARTIAL | Existing implementation; not end-to-end verified in this checkpoint | Phase 1 exit gate before product work |
| Student tests / resume / quiz | PARTIAL | Existing implementation; not end-to-end verified in this checkpoint | Eligibility, timer, persistence, interruption, safe review |
| Student essay / AI state lifecycle | PARTIAL | Existing private delivery retained | Mocked lifecycle E2E, quota, failure/retry and provider validation |
| Progress / study plans / achievements | PARTIAL | Previous #130 changes retained | Current browser and data integrity verification |
| Subscription / checkout | PARTIAL | Existing implementation, no payment made | Isolated plan/quota/expiry/checkout E2E |
| Teacher groups / attendance | PARTIAL | Ownership regressions retained | Transactional confirmation and duplicate protection |
| Teacher assignment / reports / announcements | PARTIAL | Scoped private report paths retained | Assignment E2E; announcement preview, authorization and deduplication |
| Parent interface / preferences | PARTIAL | Secure invitation implementation retained | Role-specific E2E, opt-out/removal and privacy checks |
| Administrator operations | PARTIAL | No hardcoded privilege grants restored | Scope, audit and confirmation review across all actions |
| Mini App theme / mobile / safe areas | PARTIAL | Existing app; no UI change in this checkpoint | Browser coverage at requested widths and Telegram WebView |
| Real Telegram device validation | BLOCKED | No real-device testing performed | Authorized device/test account setup |
| Notifications / queues / observability | PARTIAL | Unsafe broadcasts blocked; existing logs remain | Outbox/idempotency, bounded retries, preferences, quiet hours, redaction |
| Landing / registration / dashboards | PARTIAL | Build/lint/UI logic verification only | Rendered workflow and accessibility review |
| Exam authoring / taking / scoring | PARTIAL | Existing implementation retained | All exam types, preview isolation, autosave/resume and scoring E2E |
| AI / OCR / speaking | PARTIAL | No paid AI requests issued | Mocked provider failure and output validation review |
| Games / certificates / referrals / payments | PARTIAL | Existing implementation retained | Module-specific correctness and security review |
| Design system / localization / WCAG | PARTIAL | No visual accessibility claim | Keyboard, screen reader, contrast, localization and responsive renders |
| Performance / production reliability | PARTIAL | No before/after performance claim | Measured DB/bundle/runtime audit; backup and rollback rehearsal |
| Release / production deployment | BLOCKED | Code preparation only; no production changes | Finish Phase 1; final CI/Security, full QA, human release authorization |
