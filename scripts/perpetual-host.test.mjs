/**
 * perpetual-host.test.mjs — deterministic offline suite for the perpetual
 * self-build host supervisor core (§4 MASTER DIRECTIVE, wave 19.86, G71-2d).
 *
 * Laws under contract:
 *  - decideAction: port-first authority (never duplicate a live organ),
 *    fail-soft pending (entry absent), grace window, wedged detection,
 *    crash-loop backoff escalation.
 *  - receipt chain: sha256 hash-linked (prevHash→hash), tamper-detectable,
 *    same shape spirit as fleet-receipts-guard-core.py (mode/at/prevHash/payload).
 *  - pidfile ownership law: never kill anything we did not spawn (only
 *    "ours" — recorded pid + matching cmdline marker — may ever be signalled).
 *  - port probe: injected net executor (zero real sockets in tests).
 *  - issue-to-pr cadence: one lawful cycle per beat, own-lock respected.
 *
 * Zero network. Zero real clock (now injected). Zero organ code imported.
 */
import { describe, test, expect } from "bun:test";
import {
  giantRootCandidates,
  discoverGiantRoot,
  daemonOrgans,
  CRASH_THRESHOLD,
  decideAction,
  updateCrash,
  nextBackoffMs,
  buildReceipt,
  verifyReceipts,
  pidOwnership,
  maySignal,
  probePort,
  probeHealth,
  decideIssueCycle,
  buildHeartbeat,
} from "./perpetual-host.mjs";

const BASE = 60_000;
const MAXB = 1_800_000;
const GRACE = 12_000;

/* ── decideAction — the supervisor's only lawful moves ─────────────────── */
describe("decideAction", () => {
  const dead = { alive: false, entryExists: true, now: 10_000, graceMs: GRACE, port: 3047, organ: "commander" };

  test("alive port → skip (port-first authority, zero duplicates)", () => {
    const d = decideAction({ ...dead, alive: true });
    expect(d.action).toBe("skip");
    expect(d.verdict).toBe("alive");
    expect(d.reason).toContain("port-first");
  });

  test("entry file absent → skip/pending (fail-soft, honest)", () => {
    const d = decideAction({ ...dead, entryExists: false });
    expect(d.action).toBe("skip");
    expect(d.verdict).toBe("pending");
    expect(d.reason).toContain("pending");
  });

  test("dead + entry present + no spawn record → lawful spawn", () => {
    const d = decideAction({ ...dead });
    expect(d.action).toBe("spawn");
    expect(d.verdict).toBe("spawn");
  });

  test("our spawn alive inside grace window → skip/grace (boot patience)", () => {
    const d = decideAction({ ...dead, spawnRecord: { pid: 4242, at: 10_000 - 5_000, pidAlive: true } });
    expect(d.action).toBe("skip");
    expect(d.verdict).toBe("grace");
  });

  test("our spawn alive but port dead past grace → skip/wedged (never duplicate)", () => {
    const d = decideAction({ ...dead, spawnRecord: { pid: 4242, at: 10_000 - GRACE - 60_000, pidAlive: true } });
    expect(d.action).toBe("skip");
    expect(d.verdict).toBe("wedged");
    expect(d.reason).toContain("no duplicate");
  });

  test("our spawn died + under crash threshold → spawn retry (honest retry law)", () => {
    const d = decideAction({
      ...dead,
      spawnRecord: { pid: 4242, at: 10_000 - GRACE - 60_000, pidAlive: false },
      crash: { consecutive: CRASH_THRESHOLD - 1, backoffUntil: 10_000 + BASE },
    });
    expect(d.action).toBe("spawn");
  });

  test("our spawn died + crash-loop active → backoff (no spawn spray)", () => {
    const d = decideAction({
      ...dead,
      spawnRecord: { pid: 4242, at: 10_000 - GRACE - 60_000, pidAlive: false },
      crash: { consecutive: CRASH_THRESHOLD, backoffUntil: 10_000 + 240_000 },
    });
    expect(d.action).toBe("backoff");
    expect(d.verdict).toBe("crash-loop");
    expect(d.reason).toContain("crash-loop");
  });

  test("our spawn died + backoff expired → spawn (retry after cool-down)", () => {
    const d = decideAction({
      ...dead,
      now: 10_000 + 300_000,
      spawnRecord: { pid: 4242, at: 10_000 - GRACE - 60_000, pidAlive: false },
      crash: { consecutive: CRASH_THRESHOLD + 2, backoffUntil: 10_000 + 240_000 },
    });
    expect(d.action).toBe("spawn");
  });
});

/* ── crash-loop bookkeeping ────────────────────────────────────────────── */
describe("updateCrash + nextBackoffMs", () => {
  test("recovered resets the crash state", () => {
    const c = updateCrash({ consecutive: 5, backoffUntil: 9_999 }, "recovered", 10_000, BASE, MAXB);
    expect(c.consecutive).toBe(0);
    expect(c.backoffUntil).toBe(0);
  });

  test("failure increments consecutive and arms exponential backoff", () => {
    const c = updateCrash(null, "spawn-failed", 10_000, BASE, MAXB);
    expect(c.consecutive).toBe(1);
    expect(c.backoffUntil).toBe(10_000 + nextBackoffMs(1, BASE, MAXB));
  });

  test("backoff doubles per consecutive failure", () => {
    expect(nextBackoffMs(1, BASE, MAXB)).toBe(60_000);
    expect(nextBackoffMs(2, BASE, MAXB)).toBe(120_000);
    expect(nextBackoffMs(3, BASE, MAXB)).toBe(240_000);
  });

  test("backoff is capped at max (no unbounded silence)", () => {
    expect(nextBackoffMs(20, BASE, MAXB)).toBe(MAXB);
    expect(nextBackoffMs(20, BASE, MAXB) <= MAXB).toBe(true);
  });
});

/* ── hash-linked receipt chain (tamper-evident) ────────────────────────── */
describe("receipt chain", () => {
  test("genesis receipt: prevHash null + 64-hex hash", () => {
    const r = buildReceipt(null, "2026-10-24T17:30:00.000Z", { beat: 1 });
    expect(r.mode).toBe("receipt");
    expect(r.prevHash).toBe(null);
    expect(r.hash).toMatch(/^[0-9a-f]{64}$/);
  });

  test("chain of three verifies ok", () => {
    const r1 = buildReceipt(null, "2026-10-24T17:30:00.000Z", { beat: 1 });
    const r2 = buildReceipt(r1.hash, "2026-10-24T17:31:00.000Z", { beat: 2 });
    const r3 = buildReceipt(r2.hash, "2026-10-24T17:32:00.000Z", { beat: 3 });
    const v = verifyReceipts([r1, r2, r3]);
    expect(v.ok).toBe(true);
    expect(v.firstBadIndex).toBe(null);
  });

  test("tampered payload breaks verification at the tampered index", () => {
    const r1 = buildReceipt(null, "2026-10-24T17:30:00.000Z", { beat: 1 });
    const r2 = buildReceipt(r1.hash, "2026-10-24T17:31:00.000Z", { beat: 2 });
    const forged = { ...r2, payload: { beat: 999 } };
    const v = verifyReceipts([r1, forged]);
    expect(v.ok).toBe(false);
    expect(v.firstBadIndex).toBe(1);
  });

  test("broken prevHash link fails closed", () => {
    const r1 = buildReceipt(null, "2026-10-24T17:30:00.000Z", { beat: 1 });
    const r2 = buildReceipt("not-the-real-prev", "2026-10-24T17:31:00.000Z", { beat: 2 });
    const v = verifyReceipts([r1, r2]);
    expect(v.ok).toBe(false);
    expect(v.firstBadIndex).toBe(1);
  });

  test("empty chain verifies (fresh ledger is lawful)", () => {
    expect(verifyReceipts([]).ok).toBe(true);
  });

  test("reordered history breaks verification (append-only law)", () => {
    const r1 = buildReceipt(null, "2026-10-24T17:30:00.000Z", { beat: 1 });
    const r2 = buildReceipt(r1.hash, "2026-10-24T17:31:00.000Z", { beat: 2 });
    const v = verifyReceipts([r2, r1]);
    expect(v.ok).toBe(false);
  });
});

/* ── pidfile ownership law (never kill what we did not spawn) ──────────── */
describe("pidfile ownership law", () => {
  test("no pidfile content → none", () => {
    expect(pidOwnership(null, { alive: true, cmdline: "x", marker: "m", selfPid: 1 })).toBe("none");
    expect(pidOwnership("", { alive: true, cmdline: "x", marker: "m", selfPid: 1 })).toBe("none");
  });

  test("recorded pid dead → stale (safe to adopt by port law)", () => {
    expect(pidOwnership("4242", { alive: false, cmdline: "", marker: "m", selfPid: 1 })).toBe("stale");
  });

  test("recorded pid alive + cmdline carries our marker → ours", () => {
    expect(
      pidOwnership("4242", { alive: true, cmdline: "bun mini-services/organ-commander/index.ts beat", marker: "mini-services/organ-commander/index.ts", selfPid: 1 })
    ).toBe("ours");
  });

  test("recorded pid alive + foreign cmdline → foreign-live (never touched)", () => {
    expect(
      pidOwnership("4242", { alive: true, cmdline: "nginx: master process nginx -g daemon off;", marker: "mini-services/organ-commander/index.ts", selfPid: 1 })
    ).toBe("foreign-live");
  });

  test("recorded pid == our own pid → self (never self-signal)", () => {
    expect(pidOwnership("77", { alive: true, cmdline: "bun scripts/perpetual-host.mjs", marker: "m", selfPid: 77 })).toBe("self");
  });

  test("garbage pidfile → none", () => {
    expect(pidOwnership("not-a-pid", { alive: true, cmdline: "x", marker: "m", selfPid: 1 })).toBe("none");
  });

  test("maySignal: only ours may ever be signalled (kill law)", () => {
    expect(maySignal("ours")).toBe(true);
    expect(maySignal("none")).toBe(false);
    expect(maySignal("stale")).toBe(false);
    expect(maySignal("foreign-live")).toBe(false);
    expect(maySignal("self")).toBe(false);
  });
});

/* ── port probe with injected net executor (zero real sockets) ─────────── */
describe("probePort (injected net executor)", () => {
  test("open port → alive", async () => {
    const calls = [];
    const r = await probePort(async (host, port, timeoutMs) => {
      calls.push({ host, port, timeoutMs });
      return true;
    }, 3047);
    expect(r).toBe(true);
    expect(calls[0].port).toBe(3047);
    expect(calls[0].host).toBe("127.0.0.1");
  });

  test("closed port → dead (honest)", async () => {
    const r = await probePort(async () => false, 3049);
    expect(r).toBe(false);
  });
});

/* ── health probe with injected fetch (zero network) ───────────────────── */
describe("probeHealth (injected fetch)", () => {
  test("200 json body → alive + body captured", async () => {
    const fetchImpl = async () => ({ status: 200, json: async () => ({ ok: true, host: "saos-organ-commander" }) });
    const r = await probeHealth(fetchImpl, 3047, "/health", 100);
    expect(r.alive).toBe(true);
    expect(r.body.host).toBe("saos-organ-commander");
  });

  test("non-json organ body → alive, body null (honest shape)", async () => {
    const fetchImpl = async () => ({ status: 200, json: async () => { throw new Error("not json"); } });
    const r = await probeHealth(fetchImpl, 3049, "/health", 100);
    expect(r.alive).toBe(true);
    expect(r.body).toBe(null);
  });

  test("fetch throws (refused/timeout) → alive:false + honest error", async () => {
    const fetchImpl = async () => { throw new Error("ConnectionRefused"); };
    const r = await probeHealth(fetchImpl, 3047, "/health", 100);
    expect(r.alive).toBe(false);
    expect(r.error).toContain("ConnectionRefused");
  });
});

/* ── issue-to-pr cycle cadence ─────────────────────────────────────────── */
describe("decideIssueCycle", () => {
  test("lock free + gap honored → one lawful run", () => {
    const d = decideIssueCycle({ lockFree: true, now: 100_000, lastAt: 0, minGapMs: 55_000 });
    expect(d.run).toBe(true);
    expect(d.verdict).toBe("run");
  });

  test("lock held → busy (respect its own locks)", () => {
    const d = decideIssueCycle({ lockFree: false, now: 100_000, lastAt: 0, minGapMs: 55_000 });
    expect(d.run).toBe(false);
    expect(d.verdict).toBe("busy");
  });

  test("within min gap → gap skip (one cycle per beat max)", () => {
    const d = decideIssueCycle({ lockFree: true, now: 100_000, lastAt: 100_000 - 10_000, minGapMs: 55_000 });
    expect(d.run).toBe(false);
    expect(d.verdict).toBe("gap");
  });
});

/* ── heartbeat shape contract ──────────────────────────────────────────── */
describe("buildHeartbeat", () => {
  test("carries ts/pid/beats/lastVerdict/organs trio (audit convention)", () => {
    const organs = {
      commander: { verdict: "alive", alive: true },
      architect: { verdict: "pending", alive: false },
      issueToPr: { verdict: "no-work" },
    };
    const hb = buildHeartbeat({ nowIso: "2026-10-24T17:30:00.000Z", pid: 123, beats: 7, lastVerdict: "alive", uptimeMs: 420_000, organs });
    expect(hb.ts).toBe("2026-10-24T17:30:00.000Z");
    expect(hb.pid).toBe(123);
    expect(hb.beats).toBe(7);
    expect(hb.lastVerdict).toBe("alive");
    expect(Object.keys(hb.organs).sort()).toEqual(["architect", "commander", "issueToPr"]);
    expect(hb.organs.architect.verdict).toBe("pending");
  });
});

/* ── G78-i (trace 1a17d85ab0537c95): GIANT_ROOT discovery law ──────────────
 * Measured class (sandbox reset #7): the default GIANT_ROOT /home/z/g70/giant
 * is GONE and every organ port died at session teardown. The supervisor must
 * DISCOVER the organ worktree from lawful candidates (env first, then the
 * estate convention, then the audit clone) and fail-honest null when none
 * carries the commander entry — never spawn from a root that cannot run. */
describe("giantRootCandidates + discoverGiantRoot (G78-i)", () => {
  test("env override is first candidate, duplicates removed, order lawful", () => {
    const cands = giantRootCandidates({ GIANT_ROOT: "/x/one" });
    expect(cands[0]).toBe("/x/one");
    expect(cands).toContain("/home/z/estate/giant");
    expect(cands).toContain("/home/z/g70/giant");
    expect(cands).toContain("/home/z/audit/giant");
    const uniq = new Set(cands);
    expect(uniq.size).toBe(cands.length);
  });

  test("no env → estate convention first (organ worktree is estate law)", () => {
    const cands = giantRootCandidates({});
    expect(cands[0]).toBe("/home/z/estate/giant");
  });

  test("discoverGiantRoot: first candidate WITH the commander entry wins", () => {
    const exists = (p) => p === "/b/mini-services/organ-commander/index.ts";
    const root = discoverGiantRoot(exists, { GIANT_ROOT: "" });
    // /b is not a lawful candidate — with empty env the real candidates are
    // estate/g70/audit; simulate estate carrying the entry:
    expect(root).toBe(null); // none of the real candidates exist in this fixture
    const root2 = discoverGiantRoot(
      (p) => p === "/home/z/g70/giant/mini-services/organ-commander/index.ts",
      {}
    );
    expect(root2).toBe("/home/z/g70/giant"); // estate absent → g70 discovered
  });

  test("discoverGiantRoot: env override wins over all conventions", () => {
    const exists = (p) => p.endsWith("/mini-services/organ-commander/index.ts");
    const root = discoverGiantRoot(exists, { GIANT_ROOT: "/custom/root" });
    expect(root).toBe("/custom/root");
  });

  test("discoverGiantRoot: null when no candidate has the entry (fail-honest)", () => {
    const root = discoverGiantRoot(() => false, { GIANT_ROOT: "" });
    expect(root).toBe(null);
  });

  test("daemonOrgans: discovered root feeds organ entry/cwd paths", () => {
    const organs = daemonOrgans("/fake/root");
    expect(organs.length).toBe(2);
    expect(organs[0].entry).toBe("/fake/root/mini-services/organ-commander/index.ts");
    expect(organs[1].entry).toBe("/fake/root/mini-services/saos-architect-daemon/index.ts");
    expect(organs.every((o) => o.cwd === "/fake/root")).toBe(true);
  });
});

/* ── G78-i: organ port truth law (measured drift cure) ─────────────────────
 * Measured live: the architect daemon binds :3051 (cycle.ts PORT=3051 — the
 * operative port, live health measured) while the supervisor spec said :3049
 * → port-first authority could NEVER see the organ alive → infinite respawn
 * (EADDRINUSE honest exits) = supervision lie. New law: the spec's port MUST
 * equal the organ's actual bind — asserted by contract, cured once. */
describe("daemonOrgans port truth (G78-i)", () => {
  test("architect spec supervises the operative :3051 (cycle.ts PORT)", () => {
    const organs = daemonOrgans("/fake/root");
    const architect = organs.find((o) => o.organ === "architect");
    expect(architect.port).toBe(3051);
  });
  test("commander spec supervises :3047 (README + measured live)", () => {
    const organs = daemonOrgans("/fake/root");
    const commander = organs.find((o) => o.organ === "commander");
    expect(commander.port).toBe(3047);
  });
});
