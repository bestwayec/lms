#!/usr/bin/env bash
# Verifies the private-media rules of deploy/nginx/nginx.conf against a REAL nginx.
# It extracts the three relevant location blocks verbatim into a throw-away server on
# 127.0.0.1:18080, puts a stub upstream behind /api/ that answers like Django in
# X-Accel-Redirect mode, and checks that private uploads are unreachable by URL while
# public media and the authorized path still work. Touches nothing outside a temp dir.
#   usage: deploy/scripts/verify_private_media_nginx.sh [path/to/nginx.conf]
set -euo pipefail
CONF="${1:-deploy/nginx/nginx.conf}"
command -v nginx >/dev/null || { echo "nginx is required"; exit 2; }
W="$(mktemp -d /var/tmp/lms-nginx-verify.XXXXXX)"; chmod 755 "$W"
cleanup() { [ -f "$W/nginx.pid" ] && nginx -c "$W/nginx.conf" -s stop 2>/dev/null || true; [ -f "$W/stub.pid" ] && kill "$(cat "$W/stub.pid")" 2>/dev/null || true; rm -rf "$W"; }
trap cleanup EXIT
mkdir -p "$W/media/receipts/2026/11" "$W/media/speaking/audio" "$W/media/tuition/proofs" "$W/media/avatars" "$W/logs"
echo -n SECRET-RECEIPT > "$W/media/receipts/2026/11/a.png"; echo -n SECRET-AUDIO > "$W/media/speaking/audio/v.wav"
echo -n SECRET-PROOF > "$W/media/tuition/proofs/p.pdf";     echo -n PUBLIC-AVATAR > "$W/media/avatars/me.png"
chmod -R a+rX "$W"
python3 - "$CONF" "$W" <<'PY'
import sys
src=open(sys.argv[1]).read(); W=sys.argv[2]
def block(start):
    i=src.index(start); k=src.index("{",i); depth=0
    while True:
        if src[k]=="{": depth+=1
        elif src[k]=="}":
            depth-=1
            if depth==0: return src[i:k+1]
        k+=1
parts=[block("location ~ ^/media/(receipts|tuition/proofs|speaking/audio)/"),block("location /media/ {"),block("location /_private_media/")]
body="\n".join(parts).replace("/app/media/",W+"/media/")
open(W+"/nginx.conf","w").write(f"""worker_processes 1; pid {W}/nginx.pid; error_log {W}/logs/error.log;
events {{ worker_connections 32; }}
http {{ access_log off; client_body_temp_path {W}/t1; proxy_temp_path {W}/t2; fastcgi_temp_path {W}/t3; uwsgi_temp_path {W}/t4; scgi_temp_path {W}/t5;
  server {{ listen 127.0.0.1:18080;
{body}
    location /api/ {{ proxy_pass http://127.0.0.1:18081; }} }} }}
""")
open(W+"/stub.py","w").write('''
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("X-Accel-Redirect","/_private_media/receipts/2026/11/a.png")
        self.send_header("Cache-Control","private, no-store, max-age=0"); self.send_header("Content-Type","image/png"); self.end_headers()
    def log_message(self,*a): pass
HTTPServer(("127.0.0.1",18081),H).serve_forever()
''')
PY
python3 "$W/stub.py" & echo $! > "$W/stub.pid"
nginx -t -c "$W/nginx.conf" 2>&1 | tail -n1; nginx -c "$W/nginx.conf"; sleep 1
fail=0
check() { # path expected_status expected_body_substring
  local code body; code=$(curl -s -o "$W/body" -w '%{http_code}' --path-as-is "http://127.0.0.1:18080$1"); body=$(cat "$W/body")
  if [ "$code" = "$2" ] && { [ -z "${3:-}" ] || [[ "$body" == *"$3"* ]]; } && { [ "$2" = 200 ] || [[ "$body" != *SECRET* ]]; }; then echo "ok   $code $1"; else echo "FAIL $code $1 (wanted $2 ${3:-})"; fail=1; fi; }
check /media/receipts/2026/11/a.png 404
check /media/speaking/audio/v.wav 404
check /media/tuition/proofs/p.pdf 404
check //media//receipts//2026/11/a.png 404
check /media/receipts/../receipts/2026/11/a.png 404
check '/media/%72eceipts/2026/11/a.png' 404
check /media/avatars/me.png 200 PUBLIC-AVATAR
check /_private_media/receipts/2026/11/a.png 404
check /api/v1/files/payment-receipts/1/ 200 SECRET-RECEIPT
h=$(curl -s -D - -o /dev/null http://127.0.0.1:18080/api/v1/files/payment-receipts/1/ | tr -d '\r'); echo "$h" | grep -qi '^cache-control: private, no-store' && echo "ok   authorized response keeps Cache-Control: private, no-store" || { echo "FAIL private cache header lost"; fail=1; }
[ "$fail" = 0 ] && echo "PRIVATE MEDIA NGINX CHECKS PASSED" || { echo "PRIVATE MEDIA NGINX CHECKS FAILED"; exit 1; }
