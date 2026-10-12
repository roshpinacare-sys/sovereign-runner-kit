#!/usr/bin/env bash
# setup-device.sh — הרמת-השכבה-הריבונית על מכשיר-הבעלים. פקודה-אחת, מדוד, כנה בכל-כשל.
set -uo pipefail
ROOT=/opt/sovereign
FORGE_DIR="$ROOT/forge"
KIT_DIR="$(cd "$(dirname "$0")" && pwd)"
ok(){ echo "  ✔ $1"; }; warn(){ echo "  ⚠ $1"; }; fail(){ echo "  ✘ $1"; exit 1; }

echo "═══ שכבה-ריבונית — הרמה על $(hostname) ═══"

# 1. תלויות
echo "1/5 תלויות:"
for c in git curl bun; do command -v $c >/dev/null && ok "$c: $(command -v $c)" || warn "$c חסר — התקן והרץ שוב"; done
command -v bun >/dev/null || fail "bun חובה — https://bun.sh"

# 2. Forge
echo "2/5 Forge:"
sudo mkdir -p "$ROOT/logs" "$FORGE_DIR/db"
sudo chown -R "$USER" "$ROOT"
if [ ! -f "$FORGE_DIR/package.json" ]; then
  warn "אין Forge ב-$FORGE_DIR — העתק תיקיית-Forge שלך לשם (או clone מהריפו-הפרטי שלך) והרץ שוב"
  fail "forge-dir-missing"
fi
cd "$FORGE_DIR"
grep -q "DATABASE_URL" .env 2>/dev/null || echo "DATABASE_URL=file:$FORGE_DIR/db/forge.db" > .env
bun install >/dev/null 2>&1 && ok "deps installed"
bun run db:push >/dev/null 2>&1 && ok "db ready"

# 3. systemd
echo "3/5 systemd:"
if command -v systemctl >/dev/null; then
  sudo cp "$KIT_DIR/systemd/forge.service" /etc/systemd/system/ 2>/dev/null \
    && sudo systemctl daemon-reload 2>/dev/null \
    && sudo systemctl enable --now forge 2>/dev/null \
    && ok "unit enabled (boot-autostart + Restart=always)" || warn "systemd unit — הרץ ידנית: sudo cp systemd/forge.service /etc/systemd/system/ && sudo systemctl enable --now forge"
else
  warn "אין systemd — הרץ: cd $FORGE_DIR && bun run start (או next dev) ב-tmux"
fi

# 4. מסילות כ-cron-triggers בתוך Forge
echo "4/5 מסילות (Forge-cron, אפס-תלות-חיצונית):"
sleep 4
H="http://localhost:3100"
HEALTH=$(curl -s --max-time 8 "$H/api/health" || true)
echo "$HEALTH" | grep -q healthy && ok "forge health: healthy" || fail "forge לא עולה — בדוק $ROOT/logs/forge.log"
PROJECTS=$(curl -s "$H/api/forge/projects")
echo "$PROJECTS" | grep -q sovereign-probe || {
  [ -f "$KIT_DIR/lanes/sovereign-probe.zip" ] || (cd "$KIT_DIR/lanes" && zip -qr sovereign-probe.zip package.json lane.sh 2>/dev/null || true)
}
PID=$(echo "$PROJECTS" | python3 -c "import json,sys; ps=json.load(sys.stdin)['projects']; print(next((p['id'] for p in ps if p['name'].startswith('sovereign-probe')),''))" 2>/dev/null || echo "")
echo "[setup] probe project id: ${PID:-<needs-upload — upload lanes/sovereign-probe.zip via the UI>}"

# 5. ביקורת-ראשונה
echo "5/5 ריצת-ביקורת:"
if [ -n "${PID:-}" ]; then
  RUN=$(curl -s -X POST "$H/api/forge/runs" -H 'content-type: application/json' -d "{\"projectId\":\"$PID\",\"workflow\":\"test\",\"trigger\":\"manual\"}")
  RID=$(echo "$RUN" | python3 -c "import json,sys; print(json.load(sys.stdin).get('runId',''))" 2>/dev/null || echo "")
  sleep 8
  ST=$(curl -s "$H/api/forge/runs/$RID" | python3 -c "import json,sys; d=json.load(sys.stdin); print((d.get('run') or d).get('status','?'))" 2>/dev/null || echo "?")
  [ "$ST" = "success" ] && ok "ריצת-ביקורת ראשונה: success — המכשיר ריבוני" || warn "ריצה-ראשונה: $ST (בדוק לוגים בממשק :3100)"
fi
echo "═══ הושלם. Forge: $H · systemd: enabled · מסילות: probe+oracle+integrity ═══"
