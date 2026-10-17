# NETRUN.md — חוזה-הרצת-המשימות של הרשת (netrun v1)

> הרשת מבצעת דברים — כולל פיתוח אמיתי — לא רק מפרסמת ארטיפקטים בגיטהאב.
> חוזה זה הוא פרוטוקול-הביצוע המינימלי שכל סוכן ברשת יכול להריץ כמות שהוא.
> This file IS the executor contract: minimal, real, runnable by any agent.

## הרצה / Run

```bash
bash netrun.sh status            # כל המשימות והמצב (נגזר מ-locks/ ו-proof/ — אין שדה-סטטוס להשחתה)
bash netrun.sh claim <id>        # תפיסה אטומית (mkdir lock); מי שני מקבל LOCKED ויוצא 1
bash netrun.sh verify <id>       # מריץ את פקודת-האימות; יציאה לא-אפס = כשל אמיתי
bash netrun.sh done <id> [note]  # רישום-סיום; ההוכחה היא proof/<id>.md
```

טבלת-המשימות: `tasks.tsv` קודם; אם אינו קיים (שיבוט-טרי) — `tasks.example.tsv`
כ-fallback, כדי ש-status/verify יעבדו מיד. לעבודה אמיתית — צרו tasks.tsv מקומי.

## פורמט משימה / Task format (TSV, 4 שדות)

```
id	repo	title	verify
ex-1	Domain	dex-mirror workflow green: ...	cd ../Domain && ! grep -Rq "ain]" .github/workflows && echo WF-CLEAN
```

- **id** — מזהה קצר ויחיד; מול ה-QUEUE: מזהה-סדר-העבודה עצמו.
- **repo** — הריפו-יעד בארגון (השיבוט המקומי נמצא אח לתיקיית-ה-kit).
- **title** — מה נדרש, ללא קישוט.
- **verify** — פקודת bash אמיתית; verify חייב לצאת 0 כדי שהמשימה תיחשב מאומתת.

## קבלות / Proof convention

- הפועל (worker) כותב `proof/<id>.md`: מה שונה (קובץ:שורה), סיכום-פלטים אמיתיים
  של פקודות-האימות, sha של הקומיט, ומגבלות-כנות.
- המתאם (orchestrator) — ולא הפועל — ממזג את הקבלות אל ה-worklog המרכזי.

## חוקים / Laws (binding)

1. **חוק-אמת / TRUTH LAW** — איסור מוחלט על mock/fake/placeholder. אפס אמיתי הוא
   תוצאה לגיטימית; כישלון-כנה עם ראיות הוא תוצאה לגיטימית. verify שנכשל חייב
   לצאת לא-אפס — אין "ירוק מדומה" ואין הסתרת-אדום.
2. **חוק-התנגשויות / COLLISION LAW** — מקומי: תפיסה אטומית `mkdir locks/<id>`
   (מי שני נדחה, יוצא 1). חוצה-סנדבוקסים: רשמו repo+קבצים ב-AGENT-COORDINATION.md
   **לפני** העריכה הראשונה; `git pull --rebase` לפני כל push; אסור force-push;
   דחיית-push פירושה שמישהו נחת קודם — rebase ובדקו מחדש אם התיקון כבר קיים.
3. **חוק-סודות / SECRETS LAW** — חומר-מפתח, טוקן או סוד: לעולם לא במשימות,
   בקבלות או בפלט. נתיבים וספירות בלבד.

## חיווט / Wire-in

- **הזנה (upstream feed):** `ops-intake/ops/QUEUE.json` — סדרי-עבודה פתוחים,
  כל אחד עם `readyPrompt`. המיפוי לשורת-netrun:
  `QUEUE {id, repo, readyPrompt}` → `netrun row {id, repo, title, verify}`
  (title מתמצת את ה-readyPrompt; verify היא המדידה האמיתית שמוכיחה סיום).
- **צרכנים (consumers):** סוכנים רשומים ב-AGENT-COORDINATION.md (claim → work →
  proof) ו-ops-forge.
- **כנות:** הקומיט הזה *מקים* את החוזה; צריכה-חיה אוטומטית של ה-QUEUE היא הגל
  הבא — אינה מובטחת כאן. עד אז מייצרים שורות ידנית מה-QUEUE — ללא mock.
