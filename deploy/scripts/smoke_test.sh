#!/usr/bin/env bash
# Post-deploy smoke test (staging and production). Read-only HTTP checks.
#   deploy/scripts/smoke_test.sh https://staging.example.uz
set -euo pipefail
BASE="${1:?base URL}"
fail=0
code() { curl -sS -o /dev/null -m 15 -w "%{http_code}" "$1" || echo 000; }

for i in $(seq 1 24); do
  [ "$(code "$BASE/healthz/")" = "200" ] && break
  echo "waiting for $BASE/healthz/ ($i)"; sleep 5
done
check() { # name url expected...
  local name="$1" url="$2"; shift 2
  local got; got="$(code "$url")"
  for want in "$@"; do [ "$got" = "$want" ] && { echo "ok   $name -> $got"; return; }; done
  echo "FAIL $name -> $got (expected $*)"; fail=1
}
check "health"                 "$BASE/healthz/"                         200
check "SPA shell"              "$BASE/"                                 200
check "login page"             "$BASE/login"                            200
check "API requires auth"      "$BASE/api/auth/me/"                     401 403
check "private receipt refused"      "$BASE/media/receipts/smoke-probe.jpg"     404
check "private audio refused"        "$BASE/media/speaking/audio/smoke.webm"    404
check "private essay audio refused"  "$BASE/media/essays/audio/smoke.wav"       404
exit "$fail"
