# GRANDEC 4.0 — incremental release checkpoint

Date: 2026-11-13. **NOT RELEASE READY. Phase 1 remains PARTIAL.** This records a focused continuation of PR #131, not completion of phases 2–13.

## Recovered state

- Repository: bestwayec/lms; clean initial work branch at 45b98f0 (main release v2.4.0).
- `git ls-remote` confirmed main at 45b98f0e3db55a9244a474fe1656c647de1de4c0 and security branch/PR head at c3499e9e394be57c6b32fa7c77558e986c93f605.
- Continued security work directly from that head, preserving all eight earlier security commits. Main only adds the #130 merge and release commit; no functional main changes were missing.
- PR https://github.com/bestwayec/lms/pull/131 was DRAFT. Its Checks HTML showed automerge, security, lint, browser, backend and build jobs succeeded for c3499e9. The API returned 403; browser-accessible GitHub HTML supplied this evidence instead.
- Read CLAUDE.md, README.md, FIX_PLAN.md, existing Telegram security and production-quality audit notes, migrations/settings and CI/Security workflows. No live infrastructure inspected or changed.

## Implemented behavior

Individual test, essay and speaking scorecards must not be broadcast to every member of a student's Telegram groups. The legacy group task entry points now consume queued/redelivered work without sending messages or generating reports. Existing private test/essay notifications remain. Speaking results remain in the protected LMS speaking page; private speaking notification is pending. This is an explicit privacy correction to the earlier group-broadcast feature.

Student, essay and speaking report generators now write randomly named 0600 temporary files outside public media. The protected student PDF endpoint reads the file, removes it, sends `Cache-Control: private, no-store`, and returns a generic recoverable error while retaining server exception logs. Permissions are still enforced before generation. No database migration is added.

Updated previous tests that required public group scorecards to assert non-disclosure. Added duplicate legacy-job, private-file permission/location/uniqueness, authenticated download cleanup, and error-redaction regressions. Fixed a test fixture that combined monkeypatch with pytest-django settings and left DEBUG deleted during teardown. The existing grading query ceiling remains 56; fewer queries after removing broadcasts are accepted.

## Validation

Current test outcomes and final GitHub status are recorded below after execution. Results apply to this workspace (Python 3.12), not production or real Telegram devices. CI uses Python 3.13.

## Known limitations and security gates

- Complete command/callback and object-scope inventory is outstanding; do not declare Telegram security finished.
- Web grade override integrity, webhook/update deduplication, Mini App replay/session binding, center admin scoping, notification outbox/retry/preferences and concurrent delivery remain open.
- Temporary PDFs from failed generation or non-download callers need a bounded cleanup policy. Temporary location prevents public serving but is not encrypted storage. Student downloads buffer PDF bytes in memory.
- Protected report download permissions and all result/essay/speaking web endpoints still need a comprehensive authorization audit.
- No current rendered UI, accessibility, real-device or performance verification is claimed. No fake scores, delivery-read receipts or release assurances are introduced.
- Full product matrix: PRODUCT_READINESS_MATRIX.md. All unverified later phases remain PARTIAL/BLOCKED.

## Historical report remediation (operator action; not executed)

1. In an authorized GRANDEC-only maintenance session, inventory `MEDIA_ROOT/vedomost`, filenames, ownership, references and serving rules. Do not read/export report contents into logs.
2. Back up database, media and GRANDEC configuration with restricted access; record retention and restore procedure. Keep BESTWAY completely isolated.
3. Prepare a GRANDEC-specific rule preventing unauthenticated access to historical individual/group scorecards. Verify intended authenticated downloads still work and obtain approval before changing live serving configuration.
4. Move historical reports to restricted quarantine only after approval, reference review and backup validation. Do not automatically delete any production files. Consider cache/CDN purge and incident/privacy review based on actual exposure evidence.
5. Verify unauthenticated and unrelated-account denial and permitted downloads. Record exact changes for rollback without reopening known leaks.

## Deployment prerequisites and rollback (prepare only)

- Complete Phase 1 exit criteria: all sensitive entry points reviewed, full backend and PostgreSQL regression, migrations, final-head CI and Security success. Then proceed sequentially to bot product work.
- Record exact reviewed image/commit and existing GRANDEC deployment configuration. Verify database/media backups and restore in isolation. No new migration in this checkpoint; pre-existing accounts.0023 parent-invitation migration must be reviewed if not already applied.
- Legacy deterministic parent invitation links are intentionally invalid. Students must issue a new random invitation from an authenticated account; each expires after 24 hours and is single-use. Existing verified relations remain. Explain expiry/reissue to users; never restore reusable links.
- Preserve the existing safe private reporting routes and communicate that individual results are no longer posted to group chats. Speaking private notification is not yet implemented.
- After separate explicit deployment authorization, change only GRANDEC resources. No merge, production restart, migration, secret change, broadcasts or deployment was executed here.
- Roll back to a reviewed image that retains confidentiality fixes; do not restore unsafe group broadcasts. Keep the group paths disabled if an older image would expose results. Restore data only via an approved recovery plan; no automatic rollback deletion.

## Executed checkpoint evidence

Implementation commit: `6775414f2043ed687be264a6e745de95376aa6eb`, pushed to `feat/grandec-telegram-security-evolution` / existing draft PR #131.

| Check | Actual command / environment | Result |
| --- | --- | --- |
| Full backend pytest | `.venv/bin/pytest tests -q` | 1712 passed, 5 PostgreSQL-only skipped; 85.93s |
| Django canonical runner | `.venv/bin/python manage.py test tests --settings=config.settings.test --noinput` | 1253 tests, OK, 2 skipped |
| PostgreSQL security + grading/quota concurrency | `POSTGRES_TEST_ENABLE=1 POSTGRES_TEST_NAME=lms_pg_security POSTGRES_TEST_USER=grandec_qa POSTGRES_TEST_PASSWORD=<isolated-test-password> POSTGRES_TEST_PORT=55432 .venv/bin/pytest --ds=config.settings.postgres_test tests/test_telegram_security_evolution.py tests/test_telegram_result_privacy.py tests/test_essay_async_grading.py tests/test_subscription_usage_quota.py -q` | 84 passed, no skips; 74.31s |
| Focused privacy / private PDF | `.venv/bin/pytest tests/test_interactive_results_and_tg_sync.py tests/test_telegram_result_privacy.py -q` | 10 passed |
| Django configuration | `manage.py check --settings=config.settings.test` | No issues |
| Migration drift | `manage.py makemigrations --check --dry-run --settings=config.settings.test` | No changes detected |
| Backend lint / whitespace | `.venv/bin/ruff check .`; `git diff --check` | Passed |
| Frontend | `npm ci`; `npm run build`; `npm run lint`; `npm test` in frontend | Passed; 24 UI logic tests passed |
| Browser regression | `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium npm run test:e2e` | 17 passed; 57.6s; mocked API/browser regressions, not live Telegram E2E |

Initial full pytest execution exposed a settings-fixture teardown defect (37 failures, 449 cascading errors). Corrected the fixture and reran the entire suite successfully; no tests disabled. The grading exact-query assertion also required updating because retiring broadcasts reduced queries from 56 to 54; its maximum remains 56. Development pytest/pypdf were aligned with repository version ranges before the final run. Initial browser execution lacked Playwright's bundled executable; rerun used installed system Chromium via the existing configuration option and passed.

Warnings remain: absent local staticfiles, pre-existing Decimal validator and OpenAPI operation-ID/schema warnings. They are not suppressed or represented as resolved. The local PostgreSQL 16 container `grandec-security-qa-20261113` was stopped and removed with its disposable volume after validation.

GitHub Checks HTML for implementation commit 6775414 showed lint and automerge jobs succeeded, with Security, browser, backend and build still in progress at documentation time. Final documentation-head checks must be rechecked; green initial c3499e9 checks do not establish green final-head CI. Git push also reported one moderate Dependabot alert on the default branch; details were not triaged here. Keep PR draft until all Phase 1 gates pass.

### Continuation order

1. Recheck final pushed head and CI/Security on PR #131; resolve actual failures before marking any gate complete.
2. Inventory every sensitive Telegram command/callback and notification/report trigger with role, ownership, group scope and tests. Review current account status and positive verified private identity at delivery time.
3. Harden web grade override transaction/audit/idempotency; finish webhook/Mini App replay/duplicate/session review and notification delivery guarantees.
4. Complete comprehensive Phase 1 review and tests. Only then begin the separate Telegram product-core branch/stack. No later phase is declared complete by this checkpoint.
