#!/usr/bin/env bash
# _token.sh — מקור-הטוקן למסילות (על-המכשיר בלבד; לעולם לא בקיט/בגיט).
# סדר-קדימויות: env SOVEREIGN_PAT → .secrets/pat.env לצד-הקיט → ~/.sovereign/pat.env
GH_AUTH=()
if [ -n "${SOVEREIGN_PAT:-}" ]; then
  GH_AUTH=("authorization: Bearer ${SOVEREIGN_PAT}")
else
  for p in "$(dirname "${BASH_SOURCE[0]}")/../.secrets/pat.env" "$HOME/.sovereign/pat.env"; do
    if [ -f "$p" ]; then
      T=$(grep -o 'github_pat_[A-Za-z0-9_]*\|ghp_[A-Za-z0-9]*' "$p" | head -1 || true)
      if [ -n "${T:-}" ]; then GH_AUTH=("authorization: Bearer ${T}"); break; fi
    fi
  done
fi
