# AGENT-COORDINATION.md — Fleet-wide multi-agent anti-overwrite protocol

> מטרה: 9 סוכנים עובדים במקביל על אותם ריפואים. קובץ זה הוא רישום-התיאום הקנוני.
> כל סוכן חייב לקרוא אותו לפני עבודה, לרשום את עצמו, ולעדכן סטטוס לאחר דחיפה.
> Goal: 9 agents working concurrently on the same repos. This file is the canonical
> claim registry. Read it before touching anything; append your claim; update status after push.

## החוקים / The Rules (binding)

1. **אסור force-push. לעולם.** / **Never force-push. Ever.** History rewrite requires explicit owner approval recorded here first.
2. **תג-קומיט.** כל קומיט מתחיל ב-`[phase0-<agent-tag>]`, למשל `[phase0-zai]`. / Every commit message starts with your agent tag.
3. **תביעה לפני עריכה.** עדכן את טבלת התביעות למטה *באותו קומיט* שמכיל את התיקון הראשון שלך בריפו (או קומיט נפרד קודם). / Claim a repo+scope in the table below in (or before) your first commit touching it.
4. **לולאת משיכה.** לפני כל push: `git pull --rebase origin main`; אם נדחה — משוך מחדש, בדוק אם התיקון כבר קיים ב-main; אם כן — ותר על הקומיט שלך ועדכן סטטוס. / Pull --rebase before push; on rejection re-check whether your fix already landed; if so, drop your commit.
5. **היקף אחד לכל תביעה** — ריפו + רשימת קבצים. אין לגעת בקבצים שמתחת לתביעה פעילה של סוכן אחר. / Claim scope = repo + file list. Don't touch files under another agent's active claim.
6. **אימות אחרי דחיפה.** `git fetch origin && git show origin/main:<path>` — הוכח או גלה שנכשלת. / Verify after push from a fresh fetch. Report failure honestly.
7. **איסור הדפסת סודות.** בשום פלט, קומיט, או קובץ — רק נתיבים וספירות. / Never print secret material. Paths and counts only.
8. **אמת בלבד.** כל טענה חייבת קומיט/hash/פלט-אימות. אין "בוצע" בלי הוכחה. / Every claim carries a commit hash or verification output. No "done" without proof.

## רישום סוכנים / Agent registry

| Agent tag | Sandbox | Started (UTC) | Status |
|---|---|---|---|
| `zai` | Z.ai Code sandbox | 2026-10-17 | ACTIVE — executing Phase 0 |

(סוכנים אחרים: הוסיפו שורה / Other agents: add your row)

## טבלת תביעות / Claims registry

| Repo | Agent | Scope (files) | Status | Commit |
|---|---|---|---|---|
| sovereign-runner-kit | zai | AGENT-COORDINATION.md, SECURITY-INCIDENT-2026-10.md | IN PROGRESS | — |
| TruthRail | zai | .github/workflows/exposure-gate.yml | IN PROGRESS | — |
| FleetHQ | zai | .github/workflows/office-ci.yml, .github/workflows/office-3d.yml | IN PROGRESS | — |
| saos-control-center | zai | src/app/api/vault/login/route.ts | IN PROGRESS | — |
| Saosmartwallet | zai | .gitignore + untrack db/custom.db | IN PROGRESS | — |
| vault-home | zai | vaultlib.sh, boot-sovereign.sh (discovery/self-register hardening) | IN PROGRESS | — |
| saos-dex | zai | VERIFIED-NO-CHANGE (WIF@WORKLOG_PHASE6.md:46 = false positive, base58check invalid; no HEAD edit) | DONE | — |
| sandbox-private | zai | VERIFIED-NO-CHANGE (vault-backup.enc not git-tracked, not on disk) | DONE | — |
| Project-files | zai | pending re-triage of .env inside zips | PENDING | — |

## Phase 0 checklist (secret-triage + breakage stop)

- [x] PAT validity verified (HTTP 200, login roshpinacare-sys)
- [x] offline base58check validation of WIF-shaped string — false positive, evidence intact
- [x] vault-backup.enc tracking myth — disproven, not tracked
- [ ] CI YAML `branches: ain]` corruption fixed (TruthRail ×1, FleetHQ ×2)
- [ ] saos-control-center login/route.ts:116 parse error fixed (`atch` → `match`)
- [ ] Saosmartwallet live vault db untracked from HEAD
- [ ] vault-home token-discovery unwrap + wrap self-registration gated by default
- [ ] SECURITY-INCIDENT-2026-10.md rotation runbook published
- [ ] post-push verification from fresh fetches

## החלטות שדורשות בעלים / Decisions requiring the owner (not agent-executable)

1. **רוטציית מפתחות** של כל סוד שחשוף-היסטורית (רשימה ב-SECURITY-INCIDENT-2026-10.md). רוטציה = פעולת בעלים.
2. **שכתוב היסטוריה** (git filter-repo) לכל הסודות ההיסטוריים — דורש תיאום כל-צי + force-push מאושר.
3. השבתת `saos-desk` live+armed ורוטציית מפתחות-חיילים — רץ על מכונת המפעיל, לא בסנדבוקס.
