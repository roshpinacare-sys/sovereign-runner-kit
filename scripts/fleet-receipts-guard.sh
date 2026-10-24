#!/usr/bin/env bash
# fleet-receipts-guard.sh — מגן-מסילת-הקבלות של fleet-economy (רץ-מתמיד מקומי, §2+§8).
# ═════════════════════════════════════════════════════════════════════════════
# המחלקה-שנמדדה: vault-seal storm `vault-sync -s ours` בולע-את-מסילת-הקבלות
# (lib/receipt-sign.ts + 3 נלווים) — הישרדות-שנמדדה 2m17s. מדידה כל-5 דק ·
# שחזור byte-TRUE מ-blobs-מאומצים בלבד · דחיפת-FF בלבד (אפס-כוח) · קבלות-hash-linked.
# חוקים: מופע-יחיד (flock+UNITY) · ה-bash לא-מחליט — הליבה-הנבדקת מחליטה
# (scripts/fleet-receipts-guard-core.py, suite 13/13) · fail-closed אין-מקור-מאומץ.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
FE="${FE_REPO:-/home/z/audit/fleet-economy}"
STATE_DIR="$REPO/state/fleet-receipts-guard"
LOG="$STATE_DIR/guard.jsonl"
RECEIPTS="$STATE_DIR/receipts.jsonl"
ADOPTED="$STATE_DIR/adopted.json"
CYCLE="${FRG_CYCLE:-300}"
CORE="$REPO/scripts/fleet-receipts-guard-core.py"
mkdir -p "$STATE_DIR"

say() { printf '{"t":"%s","loop":"fleet-receipts-guard","msg":"%s"}\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" >> "$LOG"; }

# UNITY: רק-תהליך-מוקלט-חי-נחשב (pgrep-רגיל מתאים-גם-את-מעטפת-הכלי-שמכילה-את-שם-הסקריפט — דיוק-נמדד)
if [ -f "$STATE_DIR/guard.pid" ]; then
  OLD="$(cat "$STATE_DIR/guard.pid" 2>/dev/null || true)"
  if [ -n "$OLD" ] && [ "$OLD" != "$$" ] && [ -d "/proc/$OLD" ] && tr '\0' ' ' < "/proc/$OLD/cmdline" 2>/dev/null | grep -q "fleet-receipts-guard.sh"; then
    say "UNITY: guard $OLD alive — exiting"; exit 0
  fi
fi
exec 9>"$STATE_DIR/.guard.lock" || exit 1
flock -n 9 || { say "LOCK: held — exiting"; exit 0; }
echo $$ > "$STATE_DIR/guard.pid"
say "guard armed (pid $$, cycle ${CYCLE}s, rail=4, target=$FE)"

# adopted.json — המקורות-המאומצים {path: blobSha} (cd2b77a lineage, byte-TRUE suite 14/14)
if [ ! -f "$ADOPTED" ]; then
  python3 - "$ADOPTED" <<'PYEOF'
import json, subprocess, sys
rail = ["lib/receipt-sign.ts","tests/receipt-sign.test.ts","state/audit/verify_signatures.py","state/audit/receipt-2026-10-23-wave1980.json"]
out = {}
for p in rail:
    r = subprocess.run(["git","-C","/home/z/audit/fleet-economy","rev-parse","--verify","-q",f"cd2b77a:{p}"],capture_output=True,text=True)
    if r.returncode == 0 and r.stdout.strip():
        out[p] = r.stdout.strip()
json.dump(out, open(sys.argv[1],"w"), indent=1)
PYEOF
  say "baseline seeded from cd2b77a lineage ($(python3 -c "import json;print(len(json.load(open('$ADOPTED'))))" 2>/dev/null) blobs)"
fi

receipt_chain_prev() { tail -1 "$RECEIPTS" 2>/dev/null | python3 -c "import json,sys
try: print(json.load(sys.stdin)['hash'])
except Exception: print('null')"; }

append_receipt() { # $1 = payload-json-string
  local at prev out
  at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  prev="$(receipt_chain_prev)"
  out="$(printf '{"at":"%s","prev":%s,"payload":%s}' "$at" "$prev" "$1" | python3 -c "
import json,sys,importlib.util
spec=importlib.util.spec_from_file_location('c','$CORE'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
d=json.load(sys.stdin)
r=m.build_receipt(None if d['prev'] in ('null',None) else d['prev'], d['at'], d['payload'])
print(json.dumps(r, sort_keys=True))")" || { say "receipt-cli-failed"; return 1; }
  printf '%s\n' "$out" >> "$RECEIPTS"
  printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['hash'])" 2>/dev/null
}

measure_tree() { # פלט: JSON {path: blobSha|""} על origin/main של fleet-economy
  git -C "$FE" rev-parse --verify -q origin/main >/dev/null 2>&1 || git -C "$FE" fetch origin main >/dev/null 2>&1
  python3 - <<'PYEOF'
import json, subprocess
rail = ["lib/receipt-sign.ts","tests/receipt-sign.test.ts","state/audit/verify_signatures.py","state/audit/receipt-2026-10-23-wave1980.json"]
tree = {}
for p in rail:
    r = subprocess.run(["git","-C","/home/z/audit/fleet-economy","rev-parse","--verify","-q","origin/main:"+p],capture_output=True,text=True)
    tree[p] = r.stdout.strip() if r.returncode == 0 else ""
print(json.dumps(tree, sort_keys=True))
PYEOF
}

CYCLE_N=0
while true; do
  CYCLE_N=$((CYCLE_N+1))
  TIP="$(git -C "$FE" rev-parse origin/main 2>/dev/null || echo unknown)"
  TREE="$(measure_tree)" || { say "cycle $CYCLE_N: measure-failed — honest skip"; sleep "$CYCLE"; continue; }
  ADOPTED_JSON="$(python3 -c "import json,sys;print(json.dumps(json.load(open('$ADOPTED'))))" 2>/dev/null || echo '{}')"
  OUT="$(printf '{"tree":%s,"adopted":%s}' "$TREE" "$ADOPTED_JSON" | python3 "$CORE")" || { say "core-failed"; sleep "$CYCLE"; continue; }
  NSWALLOW="$(printf '%s' "$OUT" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['swallows']))")"
  NALERT="$(printf '%s' "$OUT" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['alerts']))")"

  if [ "$NSWALLOW" = "0" ]; then
    if [ "$NALERT" != "0" ]; then
      say "cycle $CYCLE_N: tip ${TIP:0:9} — rail intact, $NALERT content-drift alert(s) (never fought)"
      append_receipt "{\"cycle\":$CYCLE_N,\"tip\":\"$TIP\",\"verdict\":\"ALERT-ONLY\",\"alerts\":$NALERT}" >/dev/null
    else
      say "cycle $CYCLE_N: tip ${TIP:0:9} — rail intact (0 swallows, 0 alerts)"
    fi
    sleep "$CYCLE"; continue
  fi

  PLANERR="$(printf '%s' "$OUT" | python3 -c "import json,sys;print(json.load(sys.stdin)['planError'] or '')")"
  if [ -n "$PLANERR" ]; then
    say "cycle $CYCLE_N: $NSWALLOW swallows but rescue REFUSED: $PLANERR"
    append_receipt "{\"cycle\":$CYCLE_N,\"tip\":\"$TIP\",\"verdict\":\"RESCUE-REFUSED\",\"planError\":\"$PLANERR\"}" >/dev/null
    sleep "$CYCLE"; continue
  fi

  say "cycle $CYCLE_N: SWALLOW STORM — $NSWALLOW rail paths absent at ${TIP:0:9}: executing tested rescue plan"
  WORKTREE="/tmp/frg-rescue-$$"
  git -C "$FE" fetch origin main >/dev/null 2>&1
  TIP="$(git -C "$FE" rev-parse origin/main 2>/dev/null || echo unknown)"
  git -C "$FE" worktree add --detach "$WORKTREE" origin/main --quiet 2>>"$LOG" || { say "worktree-add-failed"; sleep "$CYCLE"; continue; }
  RESCUED=""; OK_ALL=1
  while IFS=$'\t' read -r path from; do
    [ -z "$path" ] && continue
    BLOB="${from#blob:}"
    if git -C "$FE" cat-file -e "$BLOB" 2>/dev/null; then
      mkdir -p "$WORKTREE/$(dirname "$path")"
      git -C "$FE" cat-file blob "$BLOB" > "$WORKTREE/$path" && RESCUED="$RESCUED $path"
    else
      say "adopted blob $BLOB missing for $path — refusing partial rescue"; OK_ALL=0
    fi
  done < <(printf '%s' "$OUT" | python3 -c "import json,sys
for a in json.load(sys.stdin)['plan']: print(a['path']+'\t'+a['from'])")

  if [ "$OK_ALL" != "1" ] || [ -z "$RESCUED" ]; then
    say "rescue aborted (nothing restored or missing source) — honest skip"
    git -C "$FE" worktree remove --force "$WORKTREE" 2>>"$LOG" || true
    sleep "$CYCLE"; continue
  fi

  ( cd "$WORKTREE" && git add -A && git commit -q -m "fix(economy-receipts): guard rescue$RESCUED — byte-identical reland from adopted blobs (fleet-receipts-guard cycle $CYCLE_N)

- ours-merge wipe class measured again on the receipts rail (survival census 2m17s class)
- rescue plan emitted by the tested core (scripts/fleet-receipts-guard-core.py, suite 13/13)
- byte-identical blobs from adopted baseline; zero invented content; FF-only push
- receipt: sovereign-runner-kit state/fleet-receipts-guard/receipts.jsonl (hash-linked)" ) || { say "commit-failed"; git -C "$FE" worktree remove --force "$WORKTREE" 2>>"$LOG" || true; sleep "$CYCLE"; continue; }

  if git -C "$WORKTREE" push origin HEAD:main 2>>"$LOG"; then
    H="$(append_receipt "{\"cycle\":$CYCLE_N,\"tip\":\"$TIP\",\"verdict\":\"RESCUED\",\"paths\":\"$RESCUED\"}")"
    say "RESCUED$RESCUED — pushed FF, receipt ${H:0:12}"
  else
    say "push-failed (race) — will re-measure next cycle (honest skip, no force)"
  fi
  git -C "$FE" worktree remove --force "$WORKTREE" 2>>"$LOG" || true
  sleep "$CYCLE"
done
