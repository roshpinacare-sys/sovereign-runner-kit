#!/usr/bin/env bash
# integrity-verify — ורדיקט-כנה של המכשיר: STASIS + ריצות אחרונות. קריאה-בלבד.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/_token.sh"
OUT="${1:-results/integrity.jsonl}"
mkdir -p "$(dirname "$OUT")"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
STASIS=$(curl -s --max-time 15 ${GH_AUTH:+-H "${GH_AUTH[0]}"} "https://raw.githubusercontent.com/roshpinacare-sys/Domain/main/agents/STASIS.json")
ACTIVE=$(echo "$STASIS" | grep -o '"active": *[a-z]*' | head -1 | grep -o '[a-z]*$' || echo "unknown")
MODE=$(echo "$STASIS" | grep -o '"mode": *"[^"]*"' | head -1 | cut -d'"' -f4 || echo "unknown")
RUNS=$(curl -s --max-time 15 ${GH_AUTH:+-H "${GH_AUTH[0]}"} "https://api.github.com/repos/roshpinacare-sys/Domain/actions/runs?per_page=10")
GREEN=$(echo "$RUNS" | grep -o '"conclusion": *"success"' | wc -l)
RED=$(echo "$RUNS" | grep -o '"conclusion": *"failure"' | wc -l)
VERDICT="honest-mixed"
if [ "$RED" -eq 0 ] && [ "$GREEN" -gt 0 ]; then VERDICT="honest-green"; fi
if [ "$GREEN" -eq 0 ] && [ "$RED" -gt 0 ]; then VERDICT="honest-red"; fi
printf '{"at":"%s","stasis":{"active":"%s","mode":"%s"},"domainRuns":{"success10":%s,"failure10":%s},"verdict":"%s","by":"device-integrity"}\n' \
  "$NOW" "$ACTIVE" "$MODE" "$GREEN" "$RED" "$VERDICT" >> "$OUT"
echo "[integrity] stasis: active=$ACTIVE mode=$MODE · Domain 10 runs: $GREEN green / $RED red => $VERDICT"
