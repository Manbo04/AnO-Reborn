#!/usr/bin/env bash
# Quick SSL/DNS check for affairsandorder.com — run after Cloudflare/Railway changes.
set -euo pipefail

check_host() {
  local host="$1"
  echo "=== $host ==="
  if ! dig +short "$host" | head -3 | grep -q .; then
    echo "DNS: NO RECORDS"
    return 1
  fi
  echo "DNS: $(dig +short "$host" | tr '\n' ' ')"
  if echo | openssl s_client -connect "${host}:443" -servername "$host" 2>/dev/null \
    | openssl x509 -noout -subject -issuer -dates 2>/dev/null; then
    echo "SSL: OK"
  else
    echo "SSL: FAILED or unreachable"
    return 1
  fi
  code=$(curl -sI -o /dev/null -w "%{http_code}" "https://${host}/" --max-time 15 || echo "000")
  echo "HTTPS GET /: HTTP $code"
  echo
}

check_host "affairsandorder.com"
check_host "www.affairsandorder.com" || true

echo "Done. See docs/DOMAIN_AND_EMAIL_SETUP.md if www fails or certs are invalid."
