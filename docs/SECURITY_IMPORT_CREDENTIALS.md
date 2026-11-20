# Imported student credentials — security remediation

## Behavior after this fix

Both student CSV import paths create an independent, randomly generated initial
password that is **never returned in an API response or sent via email**.

- For rows with a real email address, the system sends a password setup link
  using the existing Django password-reset token flow. The token lasts one
  hour and is invalid after a successful password change.
- For enterprise rows without an email address, an internal placeholder
  address is generated to preserve existing data behavior. **No email is sent.**
  The API reports `manual_setup_required`; staff must collect a real email,
  update the account through an authorized flow, and then use password reset.
- Pre-existing accounts are skipped by the enterprise importer rather than
  silently attached to a learning center based only on a matching email.
- Only center administrators and platform administrators can invoke the
  enterprise bulk-import endpoint.

## Deployment follow-up: existing accounts

Changing the import code does **not** invalidate previously issued shared
passwords. Before announcing the fix as complete for production:

1. Identify accounts created by the old enterprise import path using trusted
   operational records. Do not infer ownership solely from a user's email.
2. Force credential reset for those accounts through the approved admin process,
   notify their owners, and invalidate existing authenticated sessions/tokens as
   appropriate. Never email a password.
3. Verify production `SITE_URL` uses an HTTPS origin and outgoing email works.
4. Run `python manage.py test tests.test_enterprise_import_credentials` and
   the broader security suite; do not deploy if tests or mail integration fail.
5. Validate manual onboarding for rows missing a real email.

Do **not** automatically lock or reset every student account based only on
matching a known password string: that could disrupt unrelated accounts. Such
remediation needs an audited, scoped operations procedure.

## Change scope

This PR closes the predictable/plaintext **new-import credential** issue.
It does not address the separate speaking media, CSRF, or tenant-wide access
control findings from the security audit.
