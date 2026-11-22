# Private media — deployment, migration and rollback plan

**Not deployed.** This document describes how the owner can roll out Stage 1 / S1 (private receipts, tuition proofs and
speaking audio). Nothing here was applied to any server.

## What changes

| Layer | Change | PR |
|---|---|---|
| Django | Receipts / proofs / speaking audio are served only by `GET /api/v1/files/{payment-receipts,subscription-receipts,tuition-proofs,speaking}/…`, after an object-level check (404 for anyone not allowed). API and Django admin stop emitting `/media/…` URLs for them. Responses: `Cache-Control: private, no-store`, `nosniff`, sandbox CSP, attachment for anything but raster images/audio. | code PR (`claude/stage1-private-files`) |
| Frontend | Pages fetch these files with the Bearer header and show a blob URL. | code PR |
| nginx | `/media/(receipts\|tuition/proofs\|speaking/audio)/…` → **404**; new `internal` location `/_private_media/` for `X-Accel-Redirect`. Applied to `deploy/nginx/nginx.conf` (production, mounted by `docker-compose.prod.yml`), `nginx-ssl.conf`, `nginx-http.conf` and the dev `nginx.conf`. | this PR (`claude/stage1-nginx-private-media`) |
| Env | optional `PRIVATE_MEDIA_ACCEL_PREFIX=/_private_media/` (default empty = Django streams the file). | – |

**No database migration and no file move.** Existing files stay exactly where they are (`MEDIA_ROOT/receipts/…`, `tuition/proofs/…`,
`speaking/audio/…`); only the way they are reached changes.

## Deployment order (each step is independently safe)

1. **Deploy the code PR first** (backend + frontend). With today's nginx everything keeps working: the new endpoints stream through Django.
   Old API clients holding a `/media/…` URL keep working until step 2.
2. **Deploy the nginx PR.** Validate before reload: `nginx -t` inside the container, then `deploy/scripts/verify_private_media_nginx.sh`
   on any machine with nginx (it exercises the *real* production blocks with a stub upstream). Reload nginx (`nginx -s reload`; no downtime).
3. *(Optional, performance)* set `PRIVATE_MEDIA_ACCEL_PREFIX=/_private_media/` in the web container environment and restart `web`.
   nginx then streams the bytes and handles `Range` requests; Django only authorizes. Skip it and Django streams (fine at current volumes).
4. **Post-deploy checks** (production-only, not verifiable in CI):
   * As an owner, open *My subscription* → receipt thumbnails load; open a speaking result → audio plays.
   * Unauthenticated `curl -I https://grandec.uz/media/receipts/<any existing path>` → `404`.
   * Unauthenticated `curl -I https://grandec.uz/api/v1/files/payment-receipts/1/` → `401/403`.
   * As another student: the same URL for somebody else's receipt → `404`.
   * Django admin → *Payment receipts*: previews load (session auth works for the same-origin download view).
   * `access.log`: no `200` for `/media/receipts|tuition|speaking`.

## Known behavioural notes

* Previously issued `/media/receipts/…` links stop working after step 2 — intended (that is the exposure being closed).
* **Files that were ever public should be treated as exposed.** Anyone who held a URL could read it. Rotating or deleting historical
  receipts is a business decision; do it deliberately (not automated here).
* The Django admin's *edit* form for `subscriptions.PaymentReceipt` / `payments.PaymentReceipt` still renders the stock file widget whose
  "Currently:" link points at `/media/…` and will 404. Use the preview (payments) or the download endpoint
  (`/api/v1/files/subscription-receipts/<id>/`) instead.
* Teachers and center admins get **no** implicit access to students' receipts or recordings (only the owner and platform admins, plus
  users explicitly granted `payments.view_paymentreceipt` / `subscriptions.view_paymentreceipt`, or tuition-view permission for proofs).
  If a review workflow needs more, grant it deliberately.
* Public media (avatars, topic images, exam audio/images, logos) is unchanged and still served by `/media/`.
  Exam listening audio under `exams/audio/` is public by URL; see the ledger (S7) before relying on it for restricted exams.

## Rollback

* nginx: `git revert` this PR (or redeploy the previous `deploy/nginx/nginx.conf`) and reload. Files were never moved, so old URLs work again immediately.
* Code: revert the code PR; the API returns `/media/…` URLs again. Unset `PRIVATE_MEDIA_ACCEL_PREFIX` first if it was set.
* Order for a full rollback: nginx first (re-opens `/media/`), then code.
