#!/usr/bin/env bash
# netrun v1.1 — מנוע-ריצת-משימות מינימלי לרשת SAOS (החוזה המבצע; ראו NETRUN.md)
# Minimal task runner for the SAOS network: claim → execute → verify → proof.
#
# verbs:
#   status              — כל המשימות והמצב (נגזר מ-locks/ ו-proof/, אין שדה-סטטוס להשחתה)
#   claim <id>          — תפיסה אטומית (mkdir lock) — מי שני, מקבל LOCKED ויוצא 1
#   verify <id>         — מריץ את פקודת-האימות של המשימה; חייבת לצאת 0; כשל = יציאה לא-אפס
#   done <id> [note]    — רישום-סיום (ההוכחה היא proof/<id>.md של הסוכן)
#
# חוק-אמת / truth law: איסור מוחלט על mock/fake/placeholder.
# אפס אמיתי הוא תוצאה לגיטימית; כישלון-כנה עם ראיות הוא תוצאה לגיטימית.
# verify שנכשל חייב לצאת לא-אפס — אין "ירוק מדומה".
# סודות לעולם לא נכנסים למשימות, לפלט או לקבלות — נתיבים וספירות בלבד.
#
# טבלת-משימות: tasks.tsv קודם; בשיבוט-טרי (אין tasks.tsv) — tasks.example.tsv.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"; cd "$DIR"
mkdir -p locks proof
CMD="${1:-status}"; ID="${2:-}"

TASKS="tasks.tsv"
if [ ! -f "$TASKS" ]; then
  TASKS="tasks.example.tsv"
  [ -f "$TASKS" ] || { echo "NO-TASKS: neither tasks.tsv nor tasks.example.tsv present"; exit 2; }
  echo "NOTE: tasks.tsv missing — using example table: $TASKS" >&2
fi

task_verify() { awk -F'\t' -v i="$ID" 'NR>1 && $1==i {print $4}' "$TASKS"; }

case "$CMD" in
  status)
    printf "%-5s %-22s %-9s %s\n" ID REPO STATE TITLE
    tail -n +2 "$TASKS" | while IFS=$'\t' read -r id repo title _; do
      st="open"; [ -d "locks/$id" ] && st="claimed"; [ -f "proof/$id.md" ] && st="done"
      printf "%-5s %-22s %-9s %s\n" "$id" "$repo" "$st" "$title"
    done
    ;;
  claim)
    [ -n "$ID" ] || { echo "usage: netrun.sh claim <id>"; exit 2; }
    mkdir "locks/$ID" 2>/dev/null || { echo "LOCKED: $ID — already claimed (atomic mkdir lock)"; exit 1; }
    echo "CLAIMED $ID @ $(date -u +%FT%TZ)"
    ;;
  verify)
    [ -n "$ID" ] || { echo "usage: netrun.sh verify <id>"; exit 2; }
    V="$(task_verify)"
    [ -n "$V" ] || { echo "NO-TASK: $ID"; exit 1; }
    echo "VERIFY $ID → $V"
    if bash -c "$V"; then
      echo "VERIFY-OK $ID"
    else
      rc=$?
      echo "VERIFY-FAIL $ID (exit $rc) — honest failure is a valid result; attach evidence" >&2
      exit "$rc"
    fi
    ;;
  done)
    [ -n "$ID" ] || { echo "usage: netrun.sh done <id> [note]"; exit 2; }
    echo "done $ID @ $(date -u +%FT%TZ) — ${3:-}" >> "proof/$ID.done"
    echo "DONE $ID — proof: proof/$ID.md (+ .done)"
    ;;
  *)
    echo "usage: netrun.sh {status|claim <id>|verify <id>|done <id> [note]}"
    exit 2
    ;;
esac
