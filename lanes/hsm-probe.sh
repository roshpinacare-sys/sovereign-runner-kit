#!/usr/bin/env bash
# hsm-probe — measure the Saosmartwallet production HSM signing runtime (:3057)
# ==============================================================================
# Device-lane (sovereign-runner-kit law: measurement → honest JSONL → receipt).
# The runtime under probe: Saosmartwallet packages/hsm-runtime (wave G77-d,
# 2026-10-26) — deny-by-default signing service, custody outside git.
#
# WIRING (fail-honest): this lane is ADDED, not auto-scheduled. Registration
# into the Forge cron plane (the kit's scheduler) is an Instance-0 action:
#   Forge cron trigger: bash "$RUNNER_KIT/lanes/hsm-probe.sh" every 15 min
# Until that lands, run it manually or via any local heartbeat host. No cloud
# Actions dependency by design (the kit's zero-minutes law).
#
# MEASUREMENT (read-only by default):
#   1. GET /health                       → bare liveness (200 {"ok":true})
#   2. GET /status WITHOUT token         → MUST be 503 (fail-closed law)
#   3. GET /status WITH custody token    → 200 (counts only)
#   Opt-in signing smoke (writes one audit entry in the runtime's chain):
#     HSM_PROBE_SIGN=1 bash lanes/hsm-probe.sh
#
# SECRETS LAW: the bearer token is read from env HSM_RUNTIME_TOKEN, or from
# the 0600 custody file /home/z/coord-work/vaults/saosmartwallet/runtime.env —
# NEVER from the kit, NEVER printed. Loose-perm custody file ⇒ probe reports
# state "custody-breach" (fail-honest) and refuses to read it.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-results/hsm-runtime.jsonl}"
mkdir -p "$(dirname "$OUT")"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
BASE="${HSM_PROBE_URL:-http://127.0.0.1:3057}"
CUSTODY_ENV="${HSM_CUSTODY_ENV:-/home/z/coord-work/vaults/saosmartwallet/runtime.env}"

TOKEN=""
if [ -n "${HSM_RUNTIME_TOKEN:-}" ]; then
  TOKEN="$HSM_RUNTIME_TOKEN"
elif [ -f "$CUSTODY_ENV" ]; then
  PERMS=$(stat -c '%a' "$CUSTODY_ENV" 2>/dev/null || echo "000")
  if [ "$PERMS" = "600" ]; then
    TOKEN=$(sed -n 's/^HSM_RUNTIME_TOKEN=//p' "$CUSTODY_ENV" | head -1 | tr -d '\r\n')
  else
    printf '{"at":"%s","service":"hsm-runtime","state":"custody-breach","detail":"runtime.env perms %s, refusing to read (fail-honest)","by":"device-hsm-probe"}\n' \
      "$NOW" "$PERMS" >> "$OUT"
    echo "[hsm-probe] custody-breach: runtime.env perms $PERMS — refusing to read"
    exit 1
  fi
fi

HEALTH_CODE=$(curl -s -o /tmp/hsm-probe-health.$$ -m 5 -w '%{http_code}' "$BASE/health" 2>/dev/null || echo "000")
HEALTH_OK=$(grep -c '"ok":true' /tmp/hsm-probe-health.$$ 2>/dev/null || true)
rm -f /tmp/hsm-probe-health.$$
DENY_CODE=$(curl -s -o /dev/null -m 5 -w '%{http_code}' "$BASE/status" 2>/dev/null || echo "000")

STATE="down"
DETAIL="no-token-path"
if [ "$HEALTH_CODE" = "200" ] && [ "${HEALTH_OK:-0}" -ge 1 ]; then
  if [ "$DENY_CODE" = "503" ] && [ -n "$TOKEN" ]; then
    # alive + deny-by-default holds + custody token available → authenticate
    AUTH_CODE=$(curl -s -o /tmp/hsm-probe-status.$$ -m 5 -w '%{http_code}' -H "Authorization: Bearer $TOKEN" "$BASE/status" 2>/dev/null || echo "000")
    AUDIT_OK=$(grep -o '"audit":{"ok":[a-z]*' /tmp/hsm-probe-status.$$ 2>/dev/null | grep -o '[a-z]*$' || echo "unknown")
    rm -f /tmp/hsm-probe-status.$$
    if [ "$AUTH_CODE" = "200" ]; then
      STATE="healthy"
      DETAIL="health=200 deny=503 auth=200 auditChain=$AUDIT_OK"
    else
      STATE="degraded"
      DETAIL="health=200 deny=503 auth=$AUTH_CODE"
    fi
  elif [ "$DENY_CODE" = "503" ]; then
    STATE="unauthenticated"   # alive + deny-by-default holds, but no custody token available to this lane
    DETAIL="health=200 deny=503 token=absent"
  else
    STATE="broken-deny"
    DETAIL="health=200 but deny=$DENY_CODE (expected 503 — deny-by-default law violated?)"
  fi
else
  STATE="down"
  DETAIL="health=$HEALTH_CODE deny=$DENY_CODE"
fi

printf '{"at":"%s","service":"hsm-runtime","port":3057,"health":%s,"denyByDefault":"%s","auth":"%s","state":"%s","detail":"%s","by":"device-hsm-probe"}\n' \
  "$NOW" "${HEALTH_CODE:-0}" "measured" "measured" "$STATE" "$DETAIL" >> "$OUT"
echo "[hsm-probe] $STATE ($DETAIL)"

# Opt-in signing smoke — REAL signature roundtrip (opt-in because it appends
# one audit entry to the runtime's hash chain; measurement-only default).
if [ "${HSM_PROBE_SIGN:-0}" = "1" ] && [ -n "$TOKEN" ] && [ "$STATE" = "healthy" ]; then
  SIGN_CODE=$(curl -s -o /tmp/hsm-probe-sign.$$ -m 8 -w '%{http_code}' \
    -X POST -H "Authorization: Bearer $TOKEN" -H "content-type: application/json" \
    -d "{\"keyId\":\"hsm/secp256k1/primary\",\"payload\":\"device-lane probe $(date -u +%s)\"}" \
    "$BASE/sign" 2>/dev/null || echo "000")
  SIG_FPR=$(grep -o '"fingerprint":"[^"]*"' /tmp/hsm-probe-sign.$$ 2>/dev/null | head -1 | cut -d'"' -f4)
  rm -f /tmp/hsm-probe-sign.$$
  printf '{"at":"%s","service":"hsm-runtime","probe":"sign","http":%s,"fingerprint":"%s","by":"device-hsm-probe"}\n' \
    "$NOW" "$SIGN_CODE" "${SIG_FPR:-none}" >> "$OUT"
  echo "[hsm-probe] sign: $SIGN_CODE fingerprint=${SIG_FPR:-none}"
fi
