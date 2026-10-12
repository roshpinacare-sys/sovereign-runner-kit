# ToS-COMPLIANCE — תאימות-GitHub של-השכבה-הריבונית

שאלת-הבעלים: "וודא שגיטהאב לא יעיפו אותנו על משהו — תראה תקנון שלא יעיפו לי את החשבון."

מה שנבדק **מהמקורות-הרשמיים** (נשלף-חי מהשרת שלהם, 2026-10-12):

## 1. Self-hosted runners — מותר ומוצהר-במפורש, וחינם
מקור: `docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners` (נשלף, HTTP 200):

> "Self-hosted runners: Give you more control of hardware… **Are free to use with GitHub Actions**, but you are responsible for the cost of maintaining your runner machines."

**משמעות:** הרשמת המכשיר שלנו כ-runner = שימוש-רשמי נתמך. ריצות-workflow על החומרה שלנו **לא צורכות דקות-כלל** — כולל בריפו-הפרטי (Sandbox). זה הפתרון-הישיר למיצוי-המכסה.

## 2. מה אסור באמת (Acceptable Use Policies — נשלף, HTTP 200)
מקור: `docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies`:

> §4 Spam and Inauthentic Activity: "We do not allow content or activity on GitHub that is: **automated excessive bulk activity** and coordinated inauthentic activity… **cryptocurrency mining**…"

וכן מופיעים סעיפים: **"6. Services Usage Limits"**, **"9. Excessive Bandwidth Use"**.

**משמעות מול העשייה שלנו:**

| סעיף | מה אסור | מה אנחנו עושים | עמידה |
|---|---|---|---|
| AUP §4 | כרייה על-הפלטפורמה שלהם | אין כרייה; עיגון-קבלות = hash של תוצאות-ריצה, חתימה על המכשיר שלנו | ✅ |
| AUP §4 | "automated excessive bulk activity" | מסילות-מדידה: ~10-20 קריאות-API לריצה, כל 15-120 דק' — עומס-זעיר, מתון | ✅ |
| AUP §6/§9 | שימוש-מופרז בשירותים/רוחב-פס | push קבלות-JSON קטנות; אפס-הפצה, אפס-ספאם | ✅ |
| ToS כללי | תוכן-מזויף/חשבונות-כוזבים | הכל חתום-trace-ID, כנות-כפויה | ✅ |

## 3. ההיגיון המשפטי-המהנדסי
- הריצות הכבדות **עוברות לחומרה שלנו** (Forge/self-hosted) — העומס על-שרתי-GitHub **קטן**, לא גדל.
- GitHub מקבל: push של קבלות-מדידה לריפואים-שלנו = השימוש-המיועד של המוצר ("production, testing, deployment" של התוכנה שלנו).
- קריאות-API: REST limit מאומת = 5,000/שעה ל-token. סריקה-מלאה של 9 הזנות ≈ 12 קריאות. מרווח-ביטחון ×400.

## 4. קווים-אדומים-פנימיים (חוקי-הקיט — נאכפים בקוד)
1. אף-קריאה-חוזרת בלי backoff — כשל = רישום-כנה, לא ניסיון-בזבוז.
2. אין כתיבה לריפו של בעל-מסילה-אחר (רק `results/` שלנו).
3. אין מפתחות-חתימה בקיט — רק דיגסטים; החתימה בכספת-הבעלים.
4. כל-ריצה מפיקה קבלה חתומה — אפס-ריצה "שקטה".
