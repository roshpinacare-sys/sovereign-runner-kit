#!/usr/bin/env node
// anchor.mjs — טביעת-אצבע של קבלות-ריצה: SHA-256 → receipts.jsonl → payload-מוכן-לשרשרת.
// חוק-אפס-חשיפה: הקיט לעולם לא מחזיק מפתחות-חתימה. הפרסום-בפועל לשרשרת נעשה
// על-ידי כספת-הבעלים על-המכשיר שלו (steem/hive posting-key) — כאן רק ה-hash + ה-payload.
import { createHash } from "node:crypto";
import { appendFile, mkdir, readFile, writeFile, rename } from "node:fs/promises";
import path from "node:path";

const [, , receiptFile, outDir = "results"] = process.argv;
if (!receiptFile) {
  console.error("usage: node anchor/anchor.mjs <receipt.json> [outDir]");
  process.exit(2);
}

const raw = await readFile(receiptFile, "utf8");
const body = JSON.parse(raw); // פארס = ולידציה: קבלה לא-חוקית לא נחתמת
const digest = createHash("sha256").update(raw, "utf8").digest("hex");

const receipt = {
  sha256: digest,
  anchoredAt: new Date().toISOString(),
  body,
};

await mkdir(outDir, { recursive: true });
await appendFile(path.join(outDir, "receipts.jsonl"), JSON.stringify(receipt) + "\n", "utf8");

// payload פרסום-שרשרת: הכספת של הבעלים לוקחת את הקובץ הזה ומפרסמת בכספת שלו
const payload = {
  title: `sovereign-receipt ${digest.slice(0, 16)}`,
  body: JSON.stringify(receipt.body),
  sha256: digest,
  chain: "steem|hive", // הכספת בוחרת את-השרשרת שלה
  preparedAt: receipt.anchoredAt,
};
const payloadPath = path.join(outDir, "chain-payload.json.tmp");
await writeFile(payloadPath, JSON.stringify(payload, null, 2), "utf8");
await rename(payloadPath, path.join(outDir, "chain-payload.json"));

console.log(`[anchor] receipt signed sha256=${digest}`);
console.log(`[anchor] receipts.jsonl + chain-payload.json → ${outDir}/ (פרסום-סופי = כספת-הבעלים)`);
