#!/usr/bin/env bash
# sovereign-probe — מסילת-חיים של המכשיר הריבוני (מדידה בלבד, אפס-זיוף)
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/_token.sh"
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[probe] device: $(uname -srm) · $(date -u +%Y-%m-%dT%H:%M:%SZ)"
DISK=$(df -h / | awk 'NR==2{print $5}')
MEM=$(free -m 2>/dev/null | awk 'NR==2{printf "%.0f/%.0fMB", $3, $2}' || echo "n/a")
LOAD=$(uptime | sed 's/.*load average: //')
echo "[probe] disk: $DISK used · mem: $MEM · load: $LOAD"
FEEDS=(
  "Domain|office/data.json"
  "FleetHQ|office/state/office-state.json"
  "Sandbox|ops/office/work-orders.json"
)
PASS=0; TOTAL=0
for f in "${FEEDS[@]}"; do
  REPO="${f%%|*}"; PATH_="${f##*|}"
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 ${GH_AUTH:+-H "${GH_AUTH[0]}"} "https://raw.githubusercontent.com/roshpinacare-sys/$REPO/main/$PATH_")
  TOTAL=$((TOTAL+1)); [ "$CODE" = "200" ] && PASS=$((PASS+1))
  echo "[probe] $REPO/$PATH_ => HTTP $CODE"
done
echo "[probe] RESULT: $PASS/$TOTAL feeds reachable"
[ "$PASS" -eq "$TOTAL" ] || { echo "[probe] honest-FAIL"; exit 1; }
echo "[probe] PASS @ $START"
