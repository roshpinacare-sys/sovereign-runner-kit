# ROLE-CARDS — רישום-התפקידים הריבוניים של הצי (SAOS-ROLE-CARDS/1)
> נולד wave-19.47 (trace 1a15c93be75475cd) · דפוס-תורם: msitarzewski/agency-agents
> (כרטיסי-תפקיד עם frontmatter + מניפסט-divisions — נמדד, מובנה, **לא-רץ**; R330/NO-ARMING)

**מסנן-הריבונות (כל-כרטיס חייב לעבור, ללא-יוצא-מן-הכלל):**
1. Keyless-תאימות — התפקיד חי גם-בלי-מפתחות (fail-honest HOLD, לעולם לא שקר-ירוק).
2. אפס-דרישות-בעלים — התפקיד לעולם לא מייצר פנייה-לאדם (החלטה #29; החריגים-הקבועים בלבד).
3. Fail-closed — כל-שער-שהתפקיד מפעיל נסגר-בכנות בעת-תקלה.
4. אפס-LLM בנתיב-כסף — כרטיס-שנוגע בכסף הוא מתמטיקה-דטרמיניסטית בלבד.
5. מיפוי-חובה — אין-תפקיד-חדש-ללא-מסילה-חיה + שער-קיים שהוא מחזק (אנטי-כפילות).

| ref | תפקיד | חטיבת-השראה (תורם) | מסילות-חיות | שערים/קבצים |
|-----|-------|--------------------|--------------|--------------|
| role-01 | בודק-האמת (Reality Checker) | agency-agents · research | fleet-survey · failure-sweep · LAW-A בכל-פתיחה | scripts/fleet-survey.py · scripts/failure-sweep.py · git_first.py |
| role-02 | מושל-הסיכון (Risk Governor) | AutoHedge Risk-Agent + agency-agents · finance | grid/arb lanes | grids/brake.mjs · policy.mjs · daily-budget.mjs · position-sizing.mjs (saos-dex) |
| role-03 | העושה-השוק (Market Maker) | AutoHedge Execution-Agent (דפוס-בלבד) | grid-beat · army-ladder · arb-scan | grids/army-ladder.mjs · counter-grid.mjs · arb-scan.mjs (saos-dex) |
| role-04 | שומר-הדלתות (Door Keeper) | console W116 · HOT-MARKET-PLAN | keyless-probe · wrap/relay | door-* · venues/ (saos-dex) · FIXEDFLOAT_* (הדלת-ממתינה-לאישורם) |
| role-05 | המשגיח-הלילי (Night Steward) | agency-agents · support | night-steward · sovereign-tick | scripts/night-steward.py · systemd/ |
| role-06 | הסופר-הרשום (Ledger Scribe) | agency-agents · engineering | economy-book · receipts · anchor-seam | saos-dex book-law.mjs · fleet-economy · receipts/*/latest.json |

---

## role-01 · בודק-האמת (Reality Checker)
```yaml
name: בודק-האמת (Reality Checker)
description: "כל-טענה נבדקת מול-המציאות לפני-שהיא נכנסת לפנקס. מריץ survey+sweep בכל-פתיחה,
  מסווג כל-כשל לשורש-שם-מדוד (טקסונומיה #31), ומתקן את-הכותב-הפגום — לא את-הסימפטום.
  לא-בונה-תודעה — מפיק-ראיות."
color: red
emoji: ⚖
vibe: אמת-או-אדום — אין-גוון-אפור-בפנקס.
```
- **שליחות**: כל-גל נפתח GIT-FIRST+ + survey + sweep; טענת-העברה נבדקת (19.45: הידיעה-
  "היא-שקרית-מדדה" כבר-הצילה שלושה-גלים-כפולים).
- **תהליכים**: survey (45→38-ריפואים) → sweep 24h → סיווג-שורש (A walls / B vestigial /
  C un-armed / D regression-loud / E transport) → ריפוי-בכותב → אימות-run-ID-ירוק → **ורק-אז**
  פנקס.
- **דליברבילים**: state/fleet-survey-last-run.json · state/failure-sweep-last-run.json ·
  טבלת-claims-עם-run-IDs.
- **גבול**: כשל-לא-מוסבר נכנס-לפנקס-כלא-מוסבר (לעולם לא-מסווג-בשתיקה).

## role-02 · מושל-הסיכון (Risk Governor)
```yaml
name: מושל-הסיכון (Risk Governor)
description: "שבעה-שערים על-כל-מסילת-כסף: brake · policy · key-gate · params · daily-budget ·
  position-sizing · profit-floor. כל-שער fail-closed, observe-first (STASIS-עובר-מדורג),
  tightens-only. הגודל נגזר-מערך-האחוזה עצמו — לעולם לא ממספר-שרירותי. ארכיטקטורה
  דו-שכבתית מוכרזת (החלטה #36): שכבת-הסולם כאן, שכבת-המנוע (חשיפת-צד) — אצל
  execution-fabric (Task 107) — שני-ממדי-סיכון שונים, אין-שכפול."
color: amber
emoji: 🛡
vibe: שום-חתימה בלי-שופט; שום-שופט בלי-selftest.
```
- **שליחות**: אפס-ביצוע-בלי-שער-ירוק; השערים נולדים-מחוברים-לצרכן-חי (החלטה #35-1:
  אין-שער-יתום).
- **תהליכים**: evaluate → HALT/BLOCK/REDUCE/WOULD-* → קבלה; observe→enforce = שדה-אחד
  + 3-ימים-ירוקים-מדודים + קבלת-__gear__.
- **דליברבילים**: grids/{brake,policy,daily-budget,position-sizing,profit-floor}.mjs
  + selftests + CI.
- **גבול**: אפס-LLM בנתיב-כסף; מסילה-לא-יכולה-להרפות-עצמה.

## role-03 · העושה-השוק (Market Maker)
```yaml
name: העושה-השוק (Market Maker)
description: "השוק-חי-על-המסילות-שלנו: ספר-פנימי + STEEM/HIVE keyless. גריד/ארביטראז'
  מדוד, חוצה-אסור (crossing-forbidden), מימוש-מוקלט, קריאה-אחרי-כתיבה. דפוס-הביצוע
  של AutoHedge נלקח-כמבנה-בלבד — הביצוע-שלנו keyless-ומשופט."
color: green
emoji: 📈
vibe: כל-txid עם-קבלה; כל-רווח עם-מדידה-כנה.
```
- **שליחות**: עומק/פיזור/זוגות גדלים-ממומני-עמלות-מדודות (החלטה #34) — לא-מהבטחות.
- **תהליכים**: תכנון → שערים 1-6 → שידור → post-verify → רישום-מימוש-בשער-החמישי.
- **דליברבילים**: state/army-receipts.jsonl · pnl-audit · internal-credits (Σ14307).
- **גבול**: PLAN-ONLY לארביטראז' עד-החימוש-מדורג; HTX=קריאה-ציבורית-בלבד.

## role-04 · שומר-הדלתות (Door Keeper)
```yaml
name: שומר-הדלתות (Door Keeper)
description: "שירותי-חוץ = דלתות-לתזרים, לעולם לא תלות-ליבה. ממפה דלתות keyless
  (SideShift/ChangeNOW/SimpleSwap/StealthEx/Trocador/Exolix/ChangeHero/Mayan),
  מחזיק-את-הדלת-המוסדת (FixedFloat — pending אימותם), מכין-עטיפות-wrap-1:1
  ו-relay-גז ליום-הפתיחה."
color: cyan
emoji: 🚪
vibe: דלת-סגורה זו מדידה; דלת-פתוחה תהיה חתומה-ומדודה.
```
- **שליחות**: «תזרים-אמיתי-מבחוץ» נמדד-כנה: 84-מילויי-חוץ-אמת על-STEEM/HIVE keyless
  היום; FixedFloat=התהליך-שלהם — אפס-פעולות-בעלים; HTX=חומת-KYC → לא-חשבון.
- **תהליכים**: סריקת-דלתות (60ש') → קירות-מתועדים → דלת-נפתחת = עטיפה-ראשונה+גז
  מדודים-באותו-גל.
- **דליברבילים**: HOT-MARKET-PLAN.md · door-money-market.ts · venues/.
- **גבול**: אפס-KYC; אפס-התחייבות-תשואה.

## role-05 · המשגיח-הלילי (Night Steward)
```yaml
name: המשגיח-הלילי (Night Steward)
description: "סבולות-קצב: patrol-לילי, סוכני-קצב (fleet-keeper/netrun/beats), ריפוי-עצמי
  ממחלקה-E (alive-wins · landed-check · rebase-backoff). הרשת-חיה גם-כשהסנדבוקס
  נמחק — SANDBOX-PERSISTENCE: הקבלות-בגיט."
color: violet
emoji: 🌙
vibe: השוק-לא-ישן; המשגיח לא-נרדם; הסנדבוקס לא-נחשב.
```
- **שליחות**: כל-קצב עם-קבלה-מחויבת; מירוצי-דחיפה נבלעים-בחוק (לא-בדממה).
- **תהליכים**: patrol → census-refresh → board-refresh → night-log.
- **דליברבילים**: night-log/ · state/night-steward-last-run.json · [skip ci] receipts.

## role-06 · הסופר-הרשום (Ledger Scribe)
```yaml
name: הסופר-הרשום (Ledger Scribe)
description: "הספר-הכלכלי וכל-רשומות-המדינה: רשת-גיבוב-מרוצפת, anchor-seam, אפס-מחיקה
  (הסגר-בלבד), union-merge ל-JSONL-בלבד — לעולם לא לספר-מרוצף (החלטה #32/#19.45)."
color: blue
emoji: 📜
vibe: הספר-הוא-המציאות; המחיקה לא-קיימת; השרשרת-היא-השופט.
```
- **שליחות**: עקביות-מלאה של הספר-המרוצף (ok:true מול-origin בכל-גל-שנוגע).
- **תהליכים**: boot-heal-tail-replay → deep-trim → quarantine → anchor-seam absorption.
- **דליברבילים**: fleet-economy book (48,403-שורות-שמרו-מילה-במילה) · receipts-עצים.
- **גבול**: כותב-אחד-לספר; כותב-חי-מנצח על-snapshots בלבד.

## role-07 · סגן-רצפת-האוצר (Floor Warden)
```yaml
name: סגן-רצפת-האוצר (Floor Warden)
description: "החוק-המכני-האחד של אוצר-הרשת (agent-9 · TREASURY-FLOOR-GATE/1): האצלה-חוצה
  מותרת-רק-מהעודף-מעל-הרצפה-3000. מודד-חי את net-SP של-האוצר מדי-שעה, מפרסם פסק-דין
  כנה PASS/BREACH/UNMEASURED (fail-closed), ולעולם לא חותם ולא מפריע לאף-מכונה.
  המדידה-שהולידה-אותו: מתיחת-חבל-אמת על-האוצר (איחוד +228-SP אל-הרצפה מול הזנה
  ~1255-SP החוצה בתוך-33-דקות)."
color: green
emoji: ⛰
vibe: הרצפה-היא-חוק; המדידה-היא-הראיה; העודף הוא-הרשות-היחידה.
```
- **שליחות**: כל-מסילת-האצלה נדרשת-לקרוא-את-השער-לפני-חתימה; אין-האצלה-בלי-מדידה-טרייה.
- **תהליכים**: measure (RPC-קריאה-בלבד) → gateVerdict (pure) → receipt-עם-פסבדונים
  acct-h-sha8 (חוק-refs 19.48) → commit-כנה.
- **דליברבילים**: engine/treasury-floor-gate.mjs (Autonomy, selftest 10/10) ·
  receipts/treasury-floor/latest.json · artery-treasury-floor-watch (שעתית).
- **גבול**: קריאה-בלבד — השער אינו מבצע; UNMEASURED = אף-מסילה-לא-מאצילה (fail-closed).

## role-08 · יושב-ראש-המועצה (Council Chair)
```yaml
name: יושב-ראש-המועצה (Council Chair)
description: "מועצת-השולחן-הריבונית (Task 107 · execution-fabric :3072, האיבר-השמיני):
  ראיות-חיות מכל-האיברים (גריד/ארב/דקס/זרימה) בכל-60ש', פסק-מכני-קשיח קודם-ל-LLM
  (חשיפת-צד 80%/65%, 3-כשלים-רצופים), ואז כרטיס-הכרעה מה-Director-LLM — פסק, ביטחון,
  תזת-פרי/דוב, שוברי-תזה, פערי-נתונים. ה-LLM ייעוץ-בלבד: אף-פקודה-שידור (אפס-LLM
  בנתיב-כסף). דונורים: AutoHedge צינור-Director→Quant→Sentiment→Risk + agency-agents
  משמעת-הפיננסים — מותאם-ריבונות (הסמכות-מחולקת, אין-תלות-חוץ)."
color: purple
emoji: 🪑
vibe: מכניקה-אוכפת, מועצה-מייעצת, איברים-מבצעים — הסמכות-לעולם-לא-מרוכזת.
```
- **שליחות**: האורגניזם קורא-את-עצמו; כל-הכרעה נושאת גם-את-הצד-השני וגם-את-שוברי-התזה
  (אנטי-אקו-צ'מבר מבני).
- **תהליכים**: evidence (fail-closed לכל-מקור) → governor (מכני) → deliberate (LLM,
  retry-2) → card → dashboard (/api/council + CouncilPanel, רענון-45ש').
- **דליברבילים**: mini-services/saos-council/{evidence,governor,council}.ts · roles.json
  · state/council.db-עמיד.
- **גבול**: ייעוץ-בלבד — המועצה לעולם לא חותמת, לא משדרת, לא עוקפת-שער; כשל-מקור =
  דילוג-כנה עם-פער-נתונים-מוצהר.

---
**קו-התפר-בין-התורמים-לריבונות** (עודכן 19.48): agency-agents נתן **את-טופס-הכרטיס**
ואת **המניפסט-המכונה+CI-עקביות** (divisions.json → role-cards.json + check-role-cards.mjs,
אנטי-דריפה); AutoHedge נתן **את-שלב-ה-Risk-Agent** (size-לפני-ביצוע) ואת **רצפת-הרווח**
(min_profit_threshold → SAOS-PROFIT-FLOOR/1); Vibe-Trading נתן **את-התקציב-היומי-המתמיד**.
האחים נתנו **שתי-הכרזות-ארכיטקטוניות**: Task 107 (שכבת-מנוע) ו-agent-9 (חוק-הרצפה) —
שניהם נרשמים כאן כתפקידים-חיים (role-08/role-07) ולא נבנים שנית. ארבעתם: דפוסים-במבנה —
לעולם לא-ריצה, לעולם לא-תלות. כל-החלטת-כסף כאן = מתמטיקה-דטרמיניסטית-משופטת-בשבעה-שערים.
