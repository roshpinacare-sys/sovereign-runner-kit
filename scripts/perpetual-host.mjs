#!/usr/bin/env bun
/**
 * perpetual-host.mjs — the 24/7 no-operator supervisor of the self-building
 * organs (§4 of the owner's MASTER DIRECTIVE, wave 19.86, task G71-2d,
 * trace 1a16ee130d8a2289, lane claim perpetual-self-build-host →
 * sovereign-runner-kit).
 *
 * What it does, every beat (BEAT_MS, default 60s):
 *   1. probe each organ: commander :3047, architect :3051 (GET /health,
 *      short timeout, loopback) — a dead organ is a FACT, never an exception.
 *   2. decideAction (pure, tested): alive→skip · entry-absent→pending
 *      (fail-soft) · our-live-pid-inside-grace→grace · our-live-pid-past-
 *      grace→wedged (never duplicate) · crash-loop→backoff · else→spawn.
 *   3. spawn lawful organs detached (setsid + per-organ log under /home/z/audit),
 *      verify the port after the grace window, verdict honestly.
 *   4. issue-to-pr: ONE `once` cycle per beat, under its own flock lock —
 *      busy/none-claimable are honest verdicts, never fake green.
 *   5. append sha256 hash-linked receipts (prevHash→hash) to
 *      /home/z/audit/perpetual-host-receipts.jsonl and write the heartbeat
 *      /home/z/audit/perpetual-host-heartbeat.json (atomic tmp→rename).
 *
 * Laws carried from the fleet (measured, not decorative):
 *   - flock single-instance (kernel authority — same pattern as
 *     scripts/fleet-receipts-guard.sh): a second instance exits honestly.
 *   - port-first authority: NEVER spawn an organ whose port is alive
 *     (G92 lesson); double TCP check at spawn time.
 *   - pidfile ownership law: the host never signals any process it did not
 *     spawn itself (only "ours" — recorded pid + cmdline marker match —
 *     may ever be signalled; the loop currently never signals at all).
 *   - fail-honest: pending / crash-loop / wedged / busy are verdicts.
 *   - crash-loop escalation: consecutive failed spawns arm exponential
 *     backoff (60s → cap 30min) — failures are recorded, not hidden.
 *   - scheduled plane: on THIS box the local daemon class is session-bounded
 *     (measured wave 19.85: local rescue daemons died at sandbox session
 *     teardown). systemd/perpetual-host.service is the persistent-host
 *     answer; here the nohup instance runs now.
 *
 * CLI: bun scripts/perpetual-host.mjs   (env: BEAT_MS, GRACE_MS, GIANT_ROOT)
 */
import { createHash } from "node:crypto";
import net from "node:net";
import {
  existsSync, mkdirSync, openSync, closeSync, readFileSync,
  writeFileSync, appendFileSync, renameSync,
} from "node:fs";
import { dirname } from "node:path";
import { spawn as nodeSpawn } from "node:child_process";
import { dlopen, FFIType } from "bun:ffi";

/* ── constants ──────────────────────────────────────────────────────────── */
export const AUDIT_DIR = "/home/z/audit";
export const BUN = "/usr/local/bin/bun";
export const GIANT_ROOT = process.env.GIANT_ROOT || "/home/z/g70/giant";
export const CRASH_THRESHOLD = 3;
export const BACKOFF_BASE_MS = 60_000;
export const BACKOFF_MAX_MS = 1_800_000;
export const RECEIPTS_FILE = `${AUDIT_DIR}/perpetual-host-receipts.jsonl`;
export const HEARTBEAT_FILE = `${AUDIT_DIR}/perpetual-host-heartbeat.json`;
export const LOCK_FILE = `${AUDIT_DIR}/perpetual-host.lock`;
export const PID_FILE = `${AUDIT_DIR}/perpetual-host.pid`;
export const CYCLE_LOCK_FILE = `${AUDIT_DIR}/issue-to-pr.cycle.lock`;

/* ── G78-i (trace 1a17d85ab0537c95): GIANT_ROOT discovery law ─────────────
 * Measured class: sandbox resets erase the old default root (/home/z/g70/giant)
 * and every organ port dies at session teardown. The supervisor must DISCOVER
 * a lawful organ worktree instead of trusting one dead constant: env first,
 * then the estate convention, then the g70 legacy path, then the audit clone.
 * Fail-honest null when NO candidate carries the commander entry — the loop
 * records "pending" and never spawns from a root that cannot run organs. */
export function giantRootCandidates(env = process.env) {
  const cands = [
    env.GIANT_ROOT || null,
    "/home/z/estate/giant",
    "/home/z/g70/giant",
    "/home/z/audit/giant",
  ].filter(Boolean);
  return [...new Set(cands)];
}

export function discoverGiantRoot(exists = existsSync, env = process.env) {
  for (const root of giantRootCandidates(env)) {
    if (exists(`${root}/mini-services/organ-commander/index.ts`)) return root;
  }
  return null;
}

/** daemon organs under supervision (entry-file gated → architect is fail-soft) */
export function daemonOrgans(giantRoot = discoverGiantRoot() ?? GIANT_ROOT) {
  return [
    {
      organ: "commander", port: 3047, healthPath: "/health",
      entry: `${giantRoot}/mini-services/organ-commander/index.ts`,
      cwd: giantRoot,
      cmd: [BUN, "mini-services/organ-commander/index.ts", "beat"],
      log: `${AUDIT_DIR}/organ-commander.log`,
      marker: "mini-services/organ-commander/index.ts",
      graceMs: Number(process.env.GRACE_MS || 12_000),
    },
    {
      organ: "architect", port: 3051, healthPath: "/health", // G78-i cure: operative bind is :3051 (cycle.ts PORT — live-measured; :3049 was stale drift → infinite respawn)
      entry: `${giantRoot}/mini-services/saos-architect-daemon/index.ts`,
      cwd: giantRoot,
      cmd: [BUN, "mini-services/saos-architect-daemon/index.ts", "beat"],
      log: `${AUDIT_DIR}/saos-architect-daemon.log`,
      marker: "mini-services/saos-architect-daemon/index.ts",
      graceMs: Number(process.env.GRACE_MS || 12_000),
    },
  ];
}

/** the §9.3 self-building worker — not a daemon: one lawful cycle per beat.
 *  G78-i: root resolved at CALL time (sandbox resets erase module-load roots). */
export function issueOrgan() {
  const giantRoot = discoverGiantRoot() ?? GIANT_ROOT;
  return {
    organ: "issue-to-pr",
    entry: `${giantRoot}/mini-services/issue-to-pr/index.ts`,
    cwd: giantRoot,
    lock: CYCLE_LOCK_FILE,
    log: `${AUDIT_DIR}/issue-to-pr.log`,
    timeoutMs: 300_000,
  };
}

/* ══ PURE CORE (deterministic, offline-tested — zero io) ═════════════════ */

/**
 * The only lawful moves of the supervisor, decided from measured facts.
 * Order matters: alive → pending → grace → wedged → crash-loop backoff → spawn.
 */
export function decideAction(input) {
  const { alive, entryExists, now, spawnRecord, crash, graceMs, port } = input;
  if (alive) return { action: "skip", verdict: "alive", reason: `port-first authority: ${port} already alive` };
  if (!entryExists) return { action: "skip", verdict: "pending", reason: "entry file absent — fail-soft pending, retry next beat" };
  const rec = spawnRecord;
  if (rec && rec.pidAlive) {
    if (now - rec.at < graceMs) {
      return { action: "skip", verdict: "grace", reason: `our spawn pid ${rec.pid} alive inside grace window (${graceMs}ms)` };
    }
    return { action: "skip", verdict: "wedged", reason: `our pid ${rec.pid} alive but port dead past grace — no duplicate spawn (fail-closed), recorded honestly` };
  }
  if (crash && crash.consecutive >= CRASH_THRESHOLD && now < crash.backoffUntil) {
    return { action: "backoff", verdict: "crash-loop", reason: `crash-loop: ${crash.consecutive} consecutive failed spawns — backoff until ${new Date(crash.backoffUntil).toISOString()}` };
  }
  return { action: "spawn", verdict: "spawn", reason: `port ${port} dead + entry present → lawful spawn` };
}

export function nextBackoffMs(consecutive, baseMs = BACKOFF_BASE_MS, maxMs = BACKOFF_MAX_MS) {
  const ms = baseMs * Math.pow(2, Math.max(0, consecutive - 1));
  return Math.min(ms, maxMs);
}

/** outcome: "spawn-failed" escalates, "recovered" resets. */
export function updateCrash(crash, outcome, now, baseMs = BACKOFF_BASE_MS, maxMs = BACKOFF_MAX_MS) {
  if (outcome === "recovered") return { consecutive: 0, backoffUntil: 0 };
  const consecutive = (crash?.consecutive ?? 0) + 1;
  return { consecutive, backoffUntil: now + nextBackoffMs(consecutive, baseMs, maxMs) };
}

/* ── hash-linked receipts (same shape spirit as fleet-receipts-guard-core) ── */
function canonical(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  const keys = Object.keys(value).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
}

export function buildReceipt(prevHash, at, payload) {
  const body = { mode: "receipt", at, prevHash, payload };
  return { ...body, hash: createHash("sha256").update(canonical(body)).digest("hex") };
}

export function verifyReceipts(rows) {
  let prev = null;
  for (let i = 0; i < rows.length; i++) {
    const r = rows[i];
    if (r.prevHash !== prev) return { ok: false, firstBadIndex: i, reason: "broken prevHash link" };
    const body = { mode: r.mode, at: r.at, prevHash: r.prevHash, payload: r.payload };
    if (createHash("sha256").update(canonical(body)).digest("hex") !== r.hash) {
      return { ok: false, firstBadIndex: i, reason: "hash mismatch (tamper)" };
    }
    prev = r.hash;
  }
  return { ok: true, firstBadIndex: null };
}

/* ── pidfile ownership law ───────────────────────────────────────────────── */
/** ownership of the process recorded in a pidfile, from measured facts only. */
export function pidOwnership(pidfileText, proc) {
  if (!pidfileText || !pidfileText.trim()) return "none";
  const rec = parseInt(pidfileText.trim().split(/\s+/)[0], 10);
  if (!Number.isFinite(rec) || rec <= 0) return "none";
  if (rec === proc.selfPid) return "self";
  if (!proc.alive) return "stale";
  return proc.cmdline && proc.cmdline.includes(proc.marker) ? "ours" : "foreign-live";
}

/** the kill law: ONLY a process we spawned and still own may ever be signalled. */
export function maySignal(ownership) {
  return ownership === "ours";
}

/* ── probes (production executors live below; tests inject their own) ────── */
export async function probePort(netExec, port, host = "127.0.0.1") {
  return netExec(host, port, 1500);
}

export async function probeHealth(fetchImpl, port, healthPath, timeoutMs = 1500) {
  try {
    const r = await fetchImpl(`http://127.0.0.1:${port}${healthPath}`, { signal: AbortSignal.timeout(timeoutMs) });
    let body = null;
    try { body = await r.json(); } catch { /* non-JSON alive organ — honest */ }
    return { alive: true, status: r.status, body };
  } catch (e) {
    return { alive: false, error: e instanceof Error ? e.message.slice(0, 120) : String(e).slice(0, 120) };
  }
}

/* ── issue-to-pr cadence (one lawful cycle per beat, own lock respected) ──── */
export function decideIssueCycle({ lockFree, now, lastAt, minGapMs }) {
  if (lockFree === false) return { run: false, verdict: "busy", reason: "issue-to-pr cycle lock held — another worker owns it" };
  if (lastAt && now - lastAt < minGapMs) return { run: false, verdict: "gap", reason: `min gap ${minGapMs}ms since last cycle — one cycle per beat max` };
  return { run: true, verdict: "run", reason: "cycle lock free + gap honored → one lawful §9.3 cycle" };
}

/* ── heartbeat shape (audit convention: {ts, pid, beats, lastVerdict, organs}) ── */
export function buildHeartbeat({ nowIso, pid, beats, lastVerdict, uptimeMs, organs }) {
  return { ts: nowIso, pid, beats, lastVerdict, uptimeMs, organs };
}

/* ══ RUNTIME IO (real world) ═════════════════════════════════════════════ */

/* flock via libc — kernel-held advisory lock on a process-lifetime fd
   (LOCK_EX|LOCK_NB = 6). Process death releases it; no stale locks. */
const LIBC = dlopen("libc.so.6", { flock: { args: [FFIType.i32, FFIType.i32], returns: FFIType.i32 } });

function acquireFlock(path) {
  mkdirSync(dirname(path), { recursive: true });
  const fd = openSync(path, "a");
  const rc = LIBC.symbols.flock(fd, 6);
  if (rc !== 0) { closeSync(fd); return null; }
  return fd;
}

/** real net executor for probePort — a raw TCP connect IS the port truth. */
export function tcpConnect(host, port, timeoutMs) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port });
    const done = (v) => { try { s.destroy(); } catch { /* already gone */ } resolve(v); };
    s.setTimeout(timeoutMs, () => done(false));
    s.once("connect", () => done(true));
    s.once("error", () => done(false));
  });
}

function procInfo(pid, marker, selfPid) {
  try {
    const cmdline = readFileSync(`/proc/${pid}/cmdline`, "utf8").replace(/\0/g, " ").trim();
    return { alive: true, cmdline, marker, selfPid };
  } catch {
    return { alive: false, cmdline: "", marker, selfPid };
  }
}

/** detached spawn: setsid + per-organ append log — survives this process. */
function spawnDetached(spec, pidFile) {
  mkdirSync(dirname(spec.log), { recursive: true });
  const logFd = openSync(spec.log, "a");
  const child = nodeSpawn("setsid", spec.cmd, {
    cwd: spec.cwd, stdio: ["ignore", logFd, logFd], detached: true,
  });
  child.unref();
  const pid = child.pid;
  closeSync(logFd);
  writeFileSync(pidFile, JSON.stringify({ pid, at: Date.now(), organ: spec.organ, cmd: spec.cmd }));
  return pid;
}

function atomicWriteJson(path, obj) {
  const tmp = `${path}.tmp`;
  writeFileSync(tmp, JSON.stringify(obj, null, 1) + "\n");
  renameSync(tmp, path);
}

/* ══ THE LOOP ════════════════════════════════════════════════════════════ */

const nowMs = () => Date.now();
const nowIso = () => new Date().toISOString();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function loadChainPrevHash() {
  try {
    const rows = readFileSync(RECEIPTS_FILE, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l));
    const v = verifyReceipts(rows);
    if (!v.ok) {
      console.error(`[perpetual-host] persisted receipt chain TAMPERED at ${v.firstBadIndex} (${v.reason}) — starting a fresh honest chain`);
      return null;
    }
    return rows.length > 0 ? rows[rows.length - 1].hash : null;
  } catch {
    return null; // no ledger yet — genesis
  }
}

function state() {
  const organs = {};
  for (const spec of daemonOrgans()) {
    organs[spec.organ] = { verdict: null, alive: false, detail: "", attempts: 0, crashLoop: false, consecutiveFails: 0, backoffUntil: 0, lastAt: null };
  }
  organs.issueToPr = { verdict: null, lastStatus: null, lastExit: null, lastAt: null };
  return {
    startedAt: nowMs(), startedIso: nowIso(), beats: 0, lastVerdict: null,
    organs, spawnRecords: {}, crash: {}, inFlight: false,
  };
}

async function probeOrgan(spec) {
  const h = await probeHealth((u, o) => fetch(u, o), spec.port, spec.healthPath, 1500);
  return h;
}

function refreshSpawnRecord(spec, records) {
  const rec = records[spec.organ];
  if (!rec) return null;
  const info = procInfo(rec.pid, spec.marker, process.pid);
  return { ...rec, pidAlive: info.alive && info.cmdline.includes(spec.marker) };
}

async function superviseDaemon(spec, st, receipts) {
  const o = st.organs[spec.organ];
  const health = await probeOrgan(spec);
  const entryExists = existsSync(spec.entry);
  const spawnRecord = refreshSpawnRecord(spec, st.spawnRecords);
  const decision = decideAction({
    alive: health.alive, entryExists, now: nowMs(),
    spawnRecord, crash: st.crash[spec.organ] ?? null,
    graceMs: spec.graceMs, port: spec.port, organ: spec.organ,
  });
  o.alive = health.alive;
  o.detail = health.alive
    ? `HTTP ${health.status}${health.body?.host ? ` host=${health.body.host}` : ""}`
    : (health.error ?? "dead port");

  if (decision.action === "spawn") {
    // port-first double check: a raw TCP connect is the final authority
    const portAlive = await probePort(tcpConnect, spec.port);
    if (portAlive) {
      o.verdict = "alive";
      receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "probe", organ: spec.organ, verdict: "alive", detail: "tcp double-check: port alive — zero duplicates" }));
      return;
    }
    const pid = spawnDetached(spec, `${AUDIT_DIR}/perpetual-host-${spec.organ}.pid`);
    st.spawnRecords[spec.organ] = { pid, at: nowMs() };
    o.attempts += 1;
    receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "spawn", organ: spec.organ, verdict: "spawned", detail: `pid ${pid} → ${spec.log} (grace ${spec.graceMs}ms)` }));
    await sleep(spec.graceMs);
    const after = await probeOrgan(spec);
    const rec = refreshSpawnRecord(spec, st.spawnRecords);
    if (after.alive) {
      o.verdict = "spawned-ok"; o.alive = true; o.detail = `HTTP ${after.status} after grace`;
      st.crash[spec.organ] = updateCrash(st.crash[spec.organ], "recovered", nowMs());
      receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "spawn", organ: spec.organ, verdict: "spawned-ok", detail: `port ${spec.port} alive after grace (pid ${pid})` }));
    } else {
      o.verdict = rec?.pidAlive ? "spawned-no-port" : "spawn-failed";
      o.detail = after.error ?? "dead after grace";
      if (!rec?.pidAlive) {
        st.crash[spec.organ] = updateCrash(st.crash[spec.organ], "spawn-failed", nowMs());
        const c = st.crash[spec.organ];
        o.consecutiveFails = c.consecutive; o.backoffUntil = c.backoffUntil;
        o.crashLoop = c.consecutive >= CRASH_THRESHOLD;
        receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "spawn", organ: spec.organ, verdict: "spawn-failed", detail: `pid ${pid} died within grace (consecutive=${c.consecutive}, backoffUntil=${c.backoffUntil})` }));
      } else {
        receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "spawn", organ: spec.organ, verdict: "spawned-no-port", detail: `pid ${pid} alive but port ${spec.port} not listening after grace` }));
      }
    }
    return;
  }

  o.verdict = decision.verdict;
  o.detail = decision.reason;
  if (decision.verdict === "wedged") {
    receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "probe", organ: spec.organ, verdict: "wedged", detail: decision.reason }));
  } else if (decision.verdict === "crash-loop") {
    const c = st.crash[spec.organ];
    o.crashLoop = true; o.consecutiveFails = c.consecutive; o.backoffUntil = c.backoffUntil;
    receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "probe", organ: spec.organ, verdict: "crash-loop", detail: decision.reason }));
  } else if (decision.verdict === "pending") {
    receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "probe", organ: spec.organ, verdict: "pending", detail: decision.reason }));
  }
  // verdict "alive"/"grace" — steady state; beat receipt records them
}

/** ONE issue-to-pr cycle per beat under its own flock; honest busy/no-work. */
async function superviseIssueCycle(st, receipts, minGapMs) {
  const o = st.organs.issueToPr;
  const gapOk = decideIssueCycle({ lockFree: true, now: nowMs(), lastAt: o.lastAtMs ?? 0, minGapMs });
  if (!gapOk.run) { o.verdict = gapOk.verdict; o.detail = gapOk.reason; return; }
  const organ = issueOrgan(); // G78-i: root resolved at call time
  if (!existsSync(organ.entry)) { o.verdict = "pending"; o.detail = "runner entry absent — fail-soft pending"; return; }

  mkdirSync(dirname(organ.log), { recursive: true });
  const logFd = openSync(organ.log, "a");
  appendFileSync(logFd, `\n[perpetual-host] cycle dispatch ${nowIso()}\n`);
  // the flock wrapper IS the own-lock respect: exit code 1 = someone else owns it
  const child = nodeSpawn("flock", ["-n", organ.lock, BUN, "mini-services/issue-to-pr/index.ts", "once"], {
    cwd: organ.cwd, stdio: ["ignore", logFd, logFd],
  });
  closeSync(logFd);
  let done = false;
  const timer = setTimeout(() => {
    if (!done) { try { child.kill("SIGKILL"); } catch { /* already gone */ } }
  }, organ.timeoutMs);
  const exit = await new Promise((resolve) => {
    child.once("exit", (code, signal) => { done = true; resolve({ code, signal }); });
    child.once("error", (err) => { done = true; resolve({ code: -1, error: err.message }); });
  });
  clearTimeout(timer);
  o.lastAt = nowIso(); o.lastAtMs = nowMs(); o.lastExit = exit.code ?? null;
  if (exit.code === 1) {
    o.verdict = "busy"; o.detail = "cycle lock held — another worker owns the §9.3 loop";
  } else if (exit.signal) {
    o.verdict = "timeout"; o.detail = `cycle exceeded ${organ.timeoutMs}ms — killed our own spawn (signal ${exit.signal})`;
  } else if (exit.code === 0) {
    const status = readLastCycleStatus(organ.log);
    o.verdict = status ?? "done";
    o.lastStatus = status;
    o.detail = "one §9.3 cycle completed — status in log";
  } else {
    o.verdict = "cycle-error"; o.detail = `exit ${exit.code}${exit.error ? ` (${exit.error})` : ""}`;
  }
  receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "cycle", organ: "issue-to-pr", verdict: o.verdict, detail: String(o.detail).slice(0, 160) }));
}

function readLastCycleStatus(logPath) {
  try {
    const tail = readFileSync(logPath, "utf8").slice(-4000); // runner prints pretty multi-line JSON — scan the tail
    const matches = [...tail.matchAll(/"status"\s*:\s*"([a-z-]+)"/g)];
    const last = matches[matches.length - 1];
    return last ? last[1] : null;
  } catch { return null; }
}

async function beat(st, sink, beatMs) {
  const specs = daemonOrgans();
  for (const spec of specs) await superviseDaemon(spec, st, sink);
  await superviseIssueCycle(st, sink, Math.max(1000, beatMs - 5000));

  st.beats += 1;
  const verdicts = specs.map((s) => st.organs[s.organ].verdict ?? "?");
  st.lastVerdict = verdicts.join("|");
  sink.push(buildReceipt(sink.prevHash, nowIso(), {
    kind: "beat", organ: "perpetual-host", verdict: st.lastVerdict,
    detail: `beats=${st.beats} issueToPr=${st.organs.issueToPr.verdict ?? "skipped"}`,
  }));
  const hb = buildHeartbeat({
    nowIso: nowIso(), pid: process.pid, beats: st.beats, lastVerdict: st.lastVerdict,
    uptimeMs: nowMs() - st.startedAt,
    organs: JSON.parse(JSON.stringify(st.organs)),
  });
  atomicWriteJson(HEARTBEAT_FILE, hb);
  console.info(`[perpetual-host] beat ${st.beats} verdict=${st.lastVerdict} issueToPr=${st.organs.issueToPr.verdict ?? "skipped"}`);
}

function flushReceipts(sink) {
  if (sink.arr.length === 0) return;
  appendFileSync(RECEIPTS_FILE, sink.arr.map((r) => JSON.stringify(r)).join("\n") + "\n");
  sink.arr.length = 0;
}

/** receipt sink: a real array + hash-chain head (prevHash→hash, append-only). */
function makeReceiptSink(prevHash) {
  const arr = [];
  return {
    arr,
    get prevHash() { return prevHash; },
    push(receipt) { prevHash = receipt.hash; arr.push(receipt); return receipt; },
  };
}

export async function main() {
  const beatMs = Math.max(5_000, Number(process.env.BEAT_MS || 60_000));
  mkdirSync(AUDIT_DIR, { recursive: true });

  // single instance — kernel flock authority (receipts-guard pattern)
  const lockFd = acquireFlock(LOCK_FILE);
  if (lockFd === null) {
    console.error(`[perpetual-host] LOCK: ${LOCK_FILE} held — another instance is alive, exiting honestly`);
    process.exit(0);
  }
  writeFileSync(PID_FILE, JSON.stringify({ pid: process.pid, at: nowMs(), startedIso: nowIso() }));

  const prevHash = loadChainPrevHash();
  const receipts = makeReceiptSink(prevHash);
  console.info(`[perpetual-host] armed pid=${process.pid} beat=${beatMs}ms prevHash=${prevHash ? prevHash.slice(0, 12) : "genesis"} organs=${daemonOrgans().map((s) => `${s.organ}:${s.port}`).join(",")}+issue-to-pr`);
  receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "boot", organ: "perpetual-host", verdict: "armed", detail: `pid ${process.pid}, beat ${beatMs}ms, chain ${prevHash ? "continued" : "genesis"}` }));
  flushReceipts(receipts);

  const st = state();
  const onSignal = (sig) => {
    console.info(`[perpetual-host] ${sig} — honest shutdown receipt, then exit`);
    receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "shutdown", organ: "perpetual-host", verdict: "sigterm", detail: `beats=${st.beats} lastVerdict=${st.lastVerdict}` }));
    flushReceipts(receipts);
    try { closeSync(lockFd); } catch { /* kernel releases anyway */ }
    process.exit(0);
  };
  process.on("SIGTERM", () => onSignal("SIGTERM"));
  process.on("SIGINT", () => onSignal("SIGINT"));

  const tick = async () => {
    if (st.inFlight) { console.info("[perpetual-host] beat skipped — previous beat still in flight (single-flight law)"); return; }
    st.inFlight = true;
    try { await beat(st, receipts, beatMs); }
    catch (e) {
      console.error(`[perpetual-host] beat crash (honest): ${e instanceof Error ? e.stack?.split("\n").slice(0, 4).join(" | ") : String(e)}`);
      receipts.push(buildReceipt(receipts.prevHash, nowIso(), { kind: "beat", organ: "perpetual-host", verdict: "beat-error", detail: String(e instanceof Error ? e.message : e).slice(0, 160) }));
    }
    finally {
      flushReceipts(receipts);
      st.inFlight = false;
    }
  };

  await tick(); // beat 1 immediately
  setInterval(() => void tick(), beatMs);
}

if (import.meta.main) void main();
