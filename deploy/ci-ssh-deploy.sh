#!/usr/bin/env bash
# Runs ON THE GITHUB RUNNER: syncs versioned config to a VPS and runs
# deploy/remote-deploy.sh there. Used by both the staging and the production
# job so both run the identical procedure.
#
# Env (all required unless noted): IMS_IMAGE_TAG IMAGE_NAME DEPLOY_DOMAIN
#   VPS_HOST VPS_USER VPS_SSH_KEY (base64 private key) [VPS_SSH_PORT]
#   GHCR_USER GHCR_READ_TOKEN [OPENROUTER_API_KEY]
set -euo pipefail
: "${IMS_IMAGE_TAG:?}" "${IMAGE_NAME:?}" "${DEPLOY_DOMAIN:?}" "${VPS_HOST:?}" "${VPS_USER:?}" "${VPS_SSH_KEY:?}"
: "${GHCR_USER:?}" "${GHCR_READ_TOKEN:?}"
case "$IMS_IMAGE_TAG" in
  sha-[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) echo "Refusing to deploy a mutable or malformed tag: $IMS_IMAGE_TAG (need sha-xxxxxxx)"; exit 2 ;;
esac

mkdir -p ~/.ssh && chmod 700 ~/.ssh
printf '%s' "$VPS_SSH_KEY" | base64 -d > ~/.ssh/lms_deploy_key
chmod 600 ~/.ssh/lms_deploy_key
ssh-keygen -y -f ~/.ssh/lms_deploy_key >/dev/null # fail fast: key must parse
printf 'IMS_IMAGE_TAG=%s\nIMAGE_NAME=%s\nGHCR_USER=%s\nGHCR_READ_TOKEN=%s\nOPENROUTER_API_KEY=%s\nDEPLOY_DOMAIN=%s\n' \
  "$IMS_IMAGE_TAG" "$IMAGE_NAME" "$GHCR_USER" "$GHCR_READ_TOKEN" "${OPENROUTER_API_KEY:-}" "$DEPLOY_DOMAIN" > /tmp/lms_deploy.env
chmod 600 /tmp/lms_deploy.env
cleanup_ci() { rm -f /tmp/lms_deploy.env ~/.ssh/lms_deploy_key; }
trap cleanup_ci EXIT

SSH_BASE="-i $HOME/.ssh/lms_deploy_key -o BatchMode=yes -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=6 -o StrictHostKeyChecking=accept-new"
SSH="ssh -p ${VPS_SSH_PORT:-22} $SSH_BASE $VPS_USER@$VPS_HOST"
SCP="scp -P ${VPS_SSH_PORT:-22} $SSH_BASE"
# Versioned config: scp writes directly onto final paths (same inode; Docker
# bind mounts follow inodes). VPS-only files (.env.prod, secrets) never synced.
# shellcheck disable=SC2086
$SCP /tmp/lms_deploy.env "$VPS_USER@$VPS_HOST:/tmp/lms_deploy.env"
# shellcheck disable=SC2086
$SCP docker-compose.prod.yml "$VPS_USER@$VPS_HOST:/opt/lms/docker-compose.prod.yml"
# shellcheck disable=SC2086
$SCP deploy/preflight.sh deploy/vps_watchdog.py deploy/vps-watchdog.service "$VPS_USER@$VPS_HOST:/opt/lms/deploy/"
# shellcheck disable=SC2086
$SSH 'mkdir -p /opt/lms/deploy/scripts'
# shellcheck disable=SC2086
$SCP deploy/scripts/backup_db.sh "$VPS_USER@$VPS_HOST:/opt/lms/deploy/scripts/backup_db.sh"
# shellcheck disable=SC2086
$SCP deploy/nginx/nginx-main.conf deploy/nginx/nginx-http.conf deploy/nginx/nginx-ssl.conf "$VPS_USER@$VPS_HOST:/opt/lms/deploy/nginx/"
# shellcheck disable=SC2086
$SSH 'bash -s' < deploy/remote-deploy.sh
