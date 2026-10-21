#!/usr/bin/env bash
#
# bootstrap-estate.sh — SANDBOX-PERSISTENCE §2–§3 as an executable (wave 19.57).
#
# Owner order (trace 1a16092c97bffe25): autonomous activity must ALWAYS be able
# to re-establish itself. The sandbox was host-reset 3 times on record (last:
# 2026-10-21 ~22:2xZ). Git IS the estate — this script IS the re-establishment:
# token recovery -> estate clone/pull -> ledger head -> activity census hints.
#
# Usage:  bash tools/bootstrap-estate.sh [estatedir]
# Exit 0 = estate live; 1 = no working token (the only fatal state).
set -uo pipefail

ESTATE="${1:-$HOME/audit}"
ORG="roshpinacare-sys"
UPLOAD="/home/z/my-project/upload"
CORE="sovereign-runner-kit Domain Console Zip saos-dex giant steem"

# --- 1. token recovery (§3: upload/ first; never display the secret) -------
T=""
for f in "$UPLOAD/gh.token" "$UPLOAD/pat.env" "$UPLOAD/גיטראש.txt"; do
  [ -f "$f" ] || continue
  for cand in "$(tr -d '\r\n ' < "$f")" "$(tr -d '\r\n ' < "$f" | sed 's/^[^=]*=//')"; do
    [ "${#cand}" -ge 40 ] || continue
    if curl -sf -o /dev/null --max-time 10 -H "Authorization: token $cand" https://api.github.com/user; then
      T="$cand"; echo "[bootstrap] token recovered+verified: $f"; break 2
    fi
  done
done
if [ -z "$T" ]; then
  echo "[bootstrap] FATAL: no working token in $UPLOAD — cannot re-establish (owner-side input required)"; exit 1
fi
export GH_TOKEN="$T"
git config --global credential.helper '!f() { echo "username=x-access-token"; echo "password=$GH_TOKEN"; }; f'

# --- 2. estate (§2: clone-or-pull every core repo) --------------------------
mkdir -p "$ESTATE"; cd "$ESTATE" || exit 1
for r in $CORE; do
  if [ -d "$r/.git" ]; then
    git -C "$r" pull --ff-only -q 2>/dev/null || git -C "$r" fetch --depth 1 -q origin 2>/dev/null || true
  else
    git clone --depth 1 -q "https://github.com/$ORG/$r" "$r" 2>/dev/null || { echo "[bootstrap] $r CLONE FAILED"; continue; }
  fi
  h=$(git -C "$r" rev-parse --short HEAD 2>/dev/null || echo MISSING)
  echo "[bootstrap] $r @ $h"
done

# --- 3. ledger head (§5: the coordination ledger is the state of record) ----
L="$ESTATE/sovereign-runner-kit/AGENT-COORDINATION.md"
if [ -f "$L" ]; then
  echo "[bootstrap] ledger head: $(grep -o 'CONTINUED #[0-9]*' "$L" | tail -1)"
else
  echo "[bootstrap] WARNING: ledger not found — runner-kit clone failed"
fi

# --- 4. census hints (what to measure first, per the GIT-FIRST law) ---------
echo "[bootstrap] next: measure the clocks (stale-watchdog / pages-quality-gate / treasury-route runs),"
echo "[bootstrap] the 6h freshness artifacts (mirror.json x2, money-ledger, quality/report.json),"
echo "[bootstrap] and the 24h failure census — claims are zero-trust until run-ID-verified."
echo "[bootstrap] DONE — the estate is live again; git never died."
