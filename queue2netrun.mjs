#!/usr/bin/env node
// queue2netrun.mjs — ops-intake QUEUE.json → netrun task rows (TSV, 4 fields)
// חוזה: NETRUN.md (רשת SAOS). אפס תלות-חוץ: node טהור בלבד.
//
// usage:
//   node queue2netrun.mjs <path-to-QUEUE.json> [--out <tasks-file>] [--dry-run]
//
// mapping (each executable order → one row):
//   id     = q-<order.id sanitized to [a-z0-9-]>
//   repo   = order.repo  (must look like a repo name; else skip with reason)
//   title  = [<severity>] <order.title>   (severity missing → [?])
//   verify = literal `PENDING-DEFINITION`
//
// TRUTH LAW — no invented verify commands:
//   A real verify command cannot be auto-invented from a queue order. Every mapped
//   row carries the literal verify string `PENDING-DEFINITION`, which netrun.sh
//   verify will FAIL on (non-zero) until a human/agent replaces it with a real
//   command that proves completion. This is deliberate: a task without a real
//   verify command cannot pass verification, and that fact stays explicit.
//
// owner-decision orders are NEVER mapped (not agent-executable):
//   stderr: SKIP <order.id> owner-decision: <title>
//
// streams: task rows → stdout (default) or --out file (netrun-ready: header + rows).
//          skips / notes / final summary → stderr. --dry-run never writes files.
// exit:    0 on success (even if every order was skipped — honest zero is a result),
//          2 on unreadable/invalid queue, usage error, or write failure.

import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const VERIFY_PLACEHOLDER = "PENDING-DEFINITION";
const HEADER = ["id", "repo", "title", "verify"].join("\t");
// repo name shape: GitHub-ish — starts alnum, then alnum/._-, no "/", ≤100 chars.
const REPO_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/;

function die(msg, code = 2) {
  process.stderr.write(`queue2netrun: ERROR: ${msg}\n`);
  process.exit(code);
}
function note(msg) {
  process.stderr.write(`queue2netrun: ${msg}\n`);
}

function usage() {
  process.stderr.write(
    "usage: node queue2netrun.mjs <path-to-QUEUE.json> [--out <tasks-file>] [--dry-run]\n" +
    "  rows → stdout (default) or --out file; skips+summary → stderr; --dry-run writes nothing\n"
  );
}

// ---- args ------------------------------------------------------------------
const argv = process.argv.slice(2);
let queuePath = null;
let outPath = null;
let dryRun = false;
for (let i = 0; i < argv.length; i++) {
  const a = argv[i];
  if (a === "--dry-run") {
    dryRun = true;
  } else if (a === "--out") {
    outPath = argv[++i];
    if (!outPath) { usage(); die("--out requires a path"); }
  } else if (a.startsWith("--out=")) {
    outPath = a.slice("--out=".length);
    if (!outPath) { usage(); die("--out requires a path"); }
  } else if (a === "-h" || a === "--help") {
    usage();
    process.exit(0);
  } else if (a.startsWith("-") && a !== "-") {
    usage();
    die(`unknown flag: ${a}`);
  } else {
    if (queuePath !== null) { usage(); die("exactly one QUEUE.json path expected"); }
    queuePath = a;
  }
}
if (!queuePath) { usage(); die("missing <path-to-QUEUE.json>"); }

// ---- read + validate the queue ----------------------------------------------
let raw;
try {
  raw = readFileSync(queuePath, "utf8");
} catch (e) {
  die(`unreadable queue: ${queuePath} (${e.code || e.message})`);
}
let q;
try {
  q = JSON.parse(raw);
} catch (e) {
  die(`invalid queue: not parseable JSON (${e.message})`);
}
if (!q || typeof q !== "object" || Array.isArray(q)) {
  die("invalid queue: root must be a JSON object");
}
if (!Array.isArray(q.orders)) {
  die("invalid queue: orders[] missing or not an array");
}

// guard: never clobber the source queue with --out
if (outPath && path.resolve(outPath) === path.resolve(queuePath)) {
  die(`--out would overwrite the source queue: ${queuePath}`);
}

// ---- mapping -----------------------------------------------------------------
function sanitizeOrderId(s) {
  return String(s ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "");
}
function cleanTitle(s) {
  return String(s ?? "").replace(/[\t\r\n]+/g, " ").trim();
}
function short(s, n = 60) {
  const t = cleanTitle(s);
  return t.length > n ? t.slice(0, n - 1) + "…" : t;
}

const rows = [];
const reasons = new Map(); // reason → count
const seenIds = new Set();

function skip(orderId, reason, detail) {
  reasons.set(reason, (reasons.get(reason) || 0) + 1);
  process.stderr.write(`SKIP ${orderId} ${reason}${detail ? `: ${detail}` : ""}\n`);
}

for (let i = 0; i < q.orders.length; i++) {
  const o = q.orders[i];
  const ref = (o && typeof o === "object" && o.id) ? o.id : `<orders[${i}]>`;

  if (!o || typeof o !== "object" || Array.isArray(o)) {
    skip(ref, "malformed-order", "not an object");
    continue;
  }
  // owner-decision: not agent-executable — never a netrun row, always explicit.
  if (o.kind === "owner-decision") {
    skip(o.id, "owner-decision", short(o.title));
    continue;
  }
  if (!o.id || typeof o.id !== "string" || !o.id.trim()) {
    skip(ref, "missing-id", "order has no id");
    continue;
  }
  if (o.status && o.status !== "OPEN") {
    skip(o.id, `status-${o.status}`, short(o.title));
    continue;
  }
  if (typeof o.repo !== "string" || !REPO_RE.test(o.repo)) {
    skip(o.id, "bad-repo", typeof o.repo === "string" ? short(o.repo, 40) : String(o.repo));
    continue;
  }
  if (typeof o.title !== "string" || !o.title.trim()) {
    skip(o.id, "missing-title", "order has no title");
    continue;
  }
  const sid = sanitizeOrderId(o.id);
  if (!sid) {
    skip(o.id, "unnameable-id", "id sanitizes to empty");
    continue;
  }
  const nid = `q-${sid}`;
  if (seenIds.has(nid)) {
    skip(o.id, "duplicate-id", nid);
    continue;
  }
  seenIds.add(nid);
  const sev = typeof o.severity === "string" && o.severity.trim() ? o.severity.trim() : "?";
  rows.push(`${nid}\t${o.repo}\t[${sev}] ${cleanTitle(o.title)}\t${VERIFY_PLACEHOLDER}`);
}

// ---- output ------------------------------------------------------------------
if (dryRun) {
  if (outPath) note("dry-run — no files written (--out ignored)");
} else if (outPath) {
  try {
    writeFileSync(outPath, [HEADER, ...rows].join("\n") + "\n", "utf8");
    note(`wrote ${rows.length} row(s) + header → ${outPath}`);
  } catch (e) {
    die(`write failed: ${outPath} (${e.code || e.message})`);
  }
}

for (const r of rows) process.stdout.write(r + "\n");

const reasonSummary = [...reasons.entries()].map(([k, v]) => `${k}=${v}`).join(" ");
note(`mapped=${rows.length} skipped=${q.orders.length - rows.length}${reasonSummary ? ` (${reasonSummary})` : ""}`);
process.exit(0);
