#!/usr/bin/env bash
# fresh-oracle — גיל 9 הזנות מול המכסות, נמדד מהמכשיר. פלט: JSONL כנה.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/_token.sh"
OUT="${1:-results/fresh-oracle.jsonl}"
mkdir -p "$(dirname "$OUT")"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TS=$(date -u +%s)
declare -a FEEDS=(
  "foreman|FleetHQ|office/state/office-state.json|130"
  "pulse|Domain|office/data.json|30"
  "live|Domain|agents/office-live.json|150"
  "grid|Domain|agents/grid-truth.json|95"
  "recruit|Domain|agents/recruitment.json|1600"
  "ventures|Domain|agents/ventures.json|1600"
  "orders|Sandbox|ops/office/work-orders.json|35"
  "integrity|Sandbox|ops/integrity/verdict.json|95"
  "products|Domain|marketing/products.json|2880"
)
for f in "${FEEDS[@]}"; do
  IFS='|' read -r KEY REPO PATH_ CAP <<< "$f"
  LAST_COMMIT=$(curl -s --max-time 15 ${GH_AUTH:+-H "${GH_AUTH[0]}"} "https://api.github.com/repos/roshpinacare-sys/$REPO/commits?path=$PATH_&per_page=1" \
    | grep -o '"date": *"[^"]*"' | head -1 | cut -d'"' -f4 || true)
  if [ -n "${LAST_COMMIT:-}" ]; then
    CTS=$(date -u -d "$LAST_COMMIT" +%s 2>/dev/null || echo "")
    AGE=$(( CTS ? (TS - CTS) / 60 : -1 ))
    if [ "$AGE" -lt 0 ]; then AGE="null"; STATE="unknown"
    elif [ "$AGE" -le "$CAP" ]; then STATE="fresh"
    elif [ "$AGE" -le $((CAP*2)) ]; then STATE="aging"; else STATE="stale"; fi
  else AGE="null"; STATE="unknown"; fi
  printf '{"at":"%s","feed":"%s","repo":"%s","ageMin":%s,"capMin":%s,"state":"%s","by":"device-fresh-oracle"}\n' \
    "$NOW" "$KEY" "$REPO" "$AGE" "$CAP" "$STATE" >> "$OUT"
  echo "[oracle] $KEY: ${AGE}m/${CAP} => $STATE"
done
echo "[oracle] wrote $(wc -l < "$OUT") lines total"
