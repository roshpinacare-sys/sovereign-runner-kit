#!/usr/bin/env node
/**
 * check-role-cards.mjs — חוק-האנטי-דריפה של רישום-התפקידים (19.48).
 * ════════════════════════════════════════════════════════════════════════════
 * דפוס-תורם: msitarzewski/agency-agents scripts/check-divisions.sh — המניפסט מוכיח
 * את עצמו מול-המציאות ב-CI, נכשל-בכנות עם-ראיות (fail-closed, אפס-שתיקה).
 *
 * מה-הוא-אוכף (SAOS-ROLE-CARDS/1):
 *   1. docs/role-cards.json — פרוטוקול מדויק + מערך-roles לא-ריק.
 *   2. כל-ref במניפסט נמצא ב-ROLE-CARDS.md ככותרת `## role-XX · ...`.
 *   3. כל-כותרת role-XX במסמך נמצאת במניפסט (אף-כרטיס-יתום בשום-כיוון).
 *   4. כל-תפקיד נושא liveLanes לא-ריק (חוק-המיפוי-החובה — אנטי-יתום).
 *   5. כל-תפקיד נושא donor (ייחוס-חובה — אנטי-הסתרת-מקורות).
 * אפס-תלות (stdlib בלבד) · אפס-רשת · אפס-סודות.
 *
 * ריצה: node scripts/check-role-cards.mjs [--selftest]
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const DOC = join(HERE, "..", "docs", "ROLE-CARDS.md");
const MANIFEST = join(HERE, "..", "docs", "role-cards.json");

export function checkRoleCards({ doc, manifest } = {}) {
  const docText = doc ?? readFileSync(DOC, "utf8");
  const m = manifest ?? JSON.parse(readFileSync(MANIFEST, "utf8"));
  const problems = [];

  if (m.protocol !== "SAOS-ROLE-CARDS/1") problems.push(`manifest protocol '${m.protocol}' — expected SAOS-ROLE-CARDS/1`);
  const roles = Array.isArray(m.roles) ? m.roles : [];
  if (!roles.length) problems.push("manifest roles empty — an empty registry is not a registry");

  const docRefs = new Set([...docText.matchAll(/^## (role-\d+) ·/gm)].map((x) => x[1]));
  const jsonRefs = new Set(roles.map((r) => r.ref));

  for (const r of roles) {
    if (!/^role-\d+$/.test(String(r.ref ?? ""))) problems.push(`bad ref format '${r.ref}'`);
    if (!docRefs.has(r.ref)) problems.push(`manifest role ${r.ref} has no '## ${r.ref} ·' card in ROLE-CARDS.md`);
    if (!Array.isArray(r.liveLanes) || !r.liveLanes.length) problems.push(`role ${r.ref} has no liveLanes — mapping law (anti-orphan) violated`);
    if (!r.donor || !String(r.donor).trim()) problems.push(`role ${r.ref} has no donor attribution`);
  }
  for (const d of docRefs) if (!jsonRefs.has(d)) problems.push(`doc card ${d} missing from manifest — registry drift`);

  return { ok: problems.length === 0, problems, counts: { manifest: roles.length, doc: docRefs.size } };
}

export function selftest() {
  const t = (name, cond) => { if (!cond) { console.error("SELFTEST-FAIL:", name); process.exitCode = 1; } };
  // דף-תקין
  const good = checkRoleCards({
    doc: "## role-01 · בודק\n## role-02 · שומר\n",
    manifest: { protocol: "SAOS-ROLE-CARDS/1", roles: [ { ref: "role-01", donor: "x", liveLanes: ["a"] }, { ref: "role-02", donor: "y", liveLanes: ["b"] } ] },
  });
  t("consistent doc+manifest → ok", good.ok === true && good.counts.manifest === 2);
  // דריפה: מניפסט בלי-כרטיס
  const drift1 = checkRoleCards({
    doc: "## role-01 · בודק\n",
    manifest: { protocol: "SAOS-ROLE-CARDS/1", roles: [ { ref: "role-01", donor: "x", liveLanes: ["a"] }, { ref: "role-02", donor: "y", liveLanes: ["b"] } ] },
  });
  t("manifest role without doc card → fail", drift1.ok === false && drift1.problems.some((p) => p.includes("role-02")));
  // דריפה: כרטיס בלי-מניפסט
  const drift2 = checkRoleCards({
    doc: "## role-01 · בודק\n## role-09 · יתום\n",
    manifest: { protocol: "SAOS-ROLE-CARDS/1", roles: [ { ref: "role-01", donor: "x", liveLanes: ["a"] } ] },
  });
  t("doc card without manifest entry → fail", drift2.ok === false && drift2.problems.some((p) => p.includes("role-09")));
  // יתום-מסילה
  const orphan = checkRoleCards({
    doc: "## role-01 · בודק\n",
    manifest: { protocol: "SAOS-ROLE-CARDS/1", roles: [ { ref: "role-01", donor: "x", liveLanes: [] } ] },
  });
  t("empty liveLanes → fail (anti-orphan law)", orphan.ok === false && orphan.problems.some((p) => p.includes("liveLanes")));
  // פרוטוקול-זר
  const foreign = checkRoleCards({ doc: "## role-01 · בודק\n", manifest: { protocol: "FOREIGN/1", roles: [ { ref: "role-01", donor: "x", liveLanes: ["a"] } ] } });
  t("foreign protocol → fail", foreign.ok === false && foreign.problems.some((p) => p.includes("protocol")));
  // ייחוס-חסר
  const noDonor = checkRoleCards({ doc: "## role-01 · בודק\n", manifest: { protocol: "SAOS-ROLE-CARDS/1", roles: [ { ref: "role-01", donor: "", liveLanes: ["a"] } ] } });
  t("missing donor → fail", noDonor.ok === false && noDonor.problems.some((p) => p.includes("donor")));

  // הרישום-החי עצמו מוכיח את עצמו
  const live = checkRoleCards();
  if (!live.ok) { console.error("LIVE REGISTRY DRIFT:", live.problems); process.exitCode = 1; }
  else console.log(`live registry: ${live.counts.manifest} roles, doc ${live.counts.doc} cards — consistent`);

  if (process.exitCode) { console.error("check-role-cards selftest: FAILED"); process.exit(process.exitCode); }
  console.log("check-role-cards selftest: 6/6 PASS");
}

const isMain = process.argv[1] && process.argv[1].endsWith("check-role-cards.mjs");
if (isMain && process.argv.includes("--selftest")) { selftest(); process.exit(process.exitCode || 0); }
if (isMain) {
  const r = checkRoleCards();
  if (!r.ok) { console.error("ROLE-CARDS DRIFT (fail-closed):", r.problems); process.exit(1); }
  console.log(`role-cards consistent: ${r.counts.manifest} manifest roles ↔ ${r.counts.doc} doc cards`);
}
