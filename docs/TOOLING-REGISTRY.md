# TOOLING-REGISTRY — רישום-הכלים של הרשת

נוצר wave-19.4 (2026-10-18) מהנחיית הבעלים (trace 1a14ec60f8b59e49): «וודא שהאוטונומיה יודעת להשתמש בכלים שעשית והכל ולחזק עוד».

האמת-היחידה: **`tools/registry.json`** (מכונה). המסמך הזה הוא שכבת-האנוש שלו.
הוספת כלי = **עריכת נתונים, לא קוד** (base+extension pattern, STUDY-001).

## החוקים

1. **חוק-הרישום** — כל כלי שהרשת בנתה מוצהר: מה (`purpose`), איפה (`repo`+`path`), איך מפעילים (`invoke`), מה חוזה-הבטיחות (`safety`), מתי נולד (`wave`). אין כלי מחוץ לרישום; אין רישום בלי כלי.
2. **חוק-ההוכחה** — `registry-verify.yml` מדי יום ב-06:23 UTC מוכיח את הרישום **מול המציאות** (fail-closed): כלי שזז/נמחק/שונה = אדום **עם ראיות ב-state/ לפני ההערכה**. הרישום לעולם לא יירקב בשקט, והאוטונומיה לעולם לא תנסה להפעיל כלי שנעלם.
3. **חוק-הכנות** — ריפו פרטי שהמישור המאמת לא רואה נרשם `INVISIBLE-PRIVATE` (כנה — לא ירוק ולא אדום). נתיב חסר או schema שבור = אדום.
4. **חוק-הנתיב-הכתוב** — כלי `write-path` נכנס לרישום רק עם חוזה-הנעילה שלו מוצהר ב-`safety` (למשל: מנעול-הלב-היחיד של הספר הכלכלי). כלי `owner-gated` נרשם עם סימון הבעלים — לעולם לא רץ בלי אישורו המילולי המתועד.

## הכלים (12)

| id | סוג | repo | נתיב | גל |
|---|---|---|---|---|
| fleet-census | read-only | sovereign-runner-kit | scripts/fleet-census.py | 12→18 |
| fleet-rearm-approval | owner-gated | sovereign-runner-kit | scripts/fleet-rearm-approval.py | 14 |
| fleet-actions-enable | owner-gated | sovereign-runner-kit | scripts/fleet-actions-enable.py | 18 |
| scout-scan | read-only | sovereign-runner-kit | scripts/scout-scan.py | 16 |
| scout-digest | read-only | sovereign-runner-kit | scripts/scout-digest.py | 16 |
| deploy-gate | audit | sovereign-runner-kit | scripts/deploy-gate.py | 17 |
| agent-shield | audit | sovereign-runner-kit | scripts/agent-shield.py | 17 |
| capability-gate | law | sovereign-runner-kit | scripts/capability-gate.py | 18 |
| sovereign-runner-register | infra | sovereign-runner-kit | scripts/sovereign-runner-register.sh | 19 |
| fleet-survey | read-only | sovereign-runner-kit | scripts/fleet-survey.py | 19.28 |
| executor-beat | read-only | sovereign-executor | scripts/beat.py | 19→19.4 |
| economy-book-write-path | write-path | sovereign-executor | scripts/beat.py (task economy-book) | 19.2 |
| fleet-economy-book-runner | write-path | fleet-economy | run-economy-beat.mjs | 19.2 |

(הפעלה מלאה וחוזה-בטיחות לכל כלי — בתוך `tools/registry.json` עצמו, שדות `invoke`/`safety`.)

## איך האוטונומיה משתמשת בזה

- **גילוי** — העורקים והסוכנים קוראים את runner-kit (state+docs); הרישום כאן הוא משטח-הגילוי של הכלים. מנוע-המפקד של Autonomy (NETWORK-MANIFEST) יבחין במסילה החדשה מעצמו — חוק-המודעות-העצמית של הבעלים (2026-10-13) עובד.
- **הפעלה** — תמיד דרך ה-`invoke` המוצהר בלבד. לא אלתור, לא עוקפים חוזה-בטיחות.
- **אמת** — `registry-verify` מוכיח יום-יום שה-`invoke` עדיין מציאותי ושהנתיב קיים. סטייה = אדום = הבעלים רואה.
- **כתיבה** — כלי `write-path` רץ רק תחת חוזה-הנעילה שלו ועם קבלות מילים-בלבד. הספר הכלכלי הוא הדוגמה החיה: מחבר-התארח חי → SKIP; המנעול מיושן → ה-executor מאמץ על דקות-חינם.
