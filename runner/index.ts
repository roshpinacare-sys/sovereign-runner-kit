// Sovereign Runner v1 — the fleet's own execution runtime.
// Machine = runtime. GitHub = state. Actions = NOT the runtime.
// Executes real development work on fleet repos: clone -> whitelisted commands -> receipts.
// Trust boundary (honest): runs fleet-owned code on the fleet's own machine, same trust
// domain as the agents themselves. Command whitelist + denylist below; no push, no secrets.

import { mkdirSync, rmSync, appendFileSync, existsSync, readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import { createHash, timingSafeEqual, randomBytes } from 'crypto';

const PORT = Number(process.env.RUNNER_PORT) || 3020;  // T-594 ENV mobility: :3020 is the platform's own ZAI service (T-539) — runners boot on RUNNER_PORT, default preserved
const WORKROOT = '/home/z/runner-work';
const RECEIPTS = join(WORKROOT, 'receipts.jsonl');
const OWNER = 'roshpinacare-sys';
const TOKEN = existsSync('/home/z/my-project/upload/pat.env')
  ? (await Bun.file('/home/z/my-project/upload/pat.env').text()).trim()
  : '';

if (!existsSync(WORKROOT)) mkdirSync(WORKROOT, { recursive: true });

type Step = { cmd: string; exit: number | null; out: string; ms: number; timeout?: boolean };
type Job = {
  id: string; repo: string; ref: string; commands: string[];
  status: 'queued' | 'cloning' | 'running' | 'success' | 'failed';
  createdAt: string; startedAt?: string; finishedAt?: string;
  steps: Step[]; cloneError?: string; note?: string;
};

const jobs = new Map<string, Job>();
let chain: Promise<void> = Promise.resolve();
const started = new Date().toISOString();

// ---- security: deny first, then allow ----
const DENY = [
  /\$/, /`/, /~/, /\.\./, /\/home/i, /pat\.env/i, /vault/i, /secret/i, /\.ssh/i, /upload/i,
  /&&/, /\|\|/,
];
const ALLOW: RegExp[] = [
  /^ls( -[a-z]+)*( [\w./-]+)?$/,
  /^cat [\w./-]+$/,
  /^wc -l [\w./-]+$/,
  /^rg [^"'`]* [\w./-]+$/,
  /^git (status|log --oneline( -n \d+)?|rev-parse HEAD)$/,
  /^node --check [\w./-]+$/,
  /^node --version$/,
  // bun install removed (directive 1a173c6ac120ccb1 §1): postinstall scripts = arbitrary code
  // execution from any anonymous job submitter. Install once, supervised, at runner boot —
  // not from the request plane.
  /^bun test( [\w./@-]*)?$/,
  /^bun run lint$/,
  /^bunx? tsc --noEmit( [\w./@-]*)?$/,
  /^npm test( --[\w=@.-]*)?$/,
];
function validateCommands(cmds: unknown): string[] | string {
  if (!Array.isArray(cmds) || cmds.length < 1 || cmds.length > 5) return 'commands: 1..5 strings';
  for (const c of cmds) {
    if (typeof c !== 'string' || c.length === 0 || c.length > 300) return 'bad command length';
    if (DENY.some((r) => r.test(c))) return `denied: ${c}`;
    if (!ALLOW.some((r) => r.test(c.trim()))) return `not whitelisted: ${c}`;
  }
  return cmds as string[];
}

async function run(cmd: string, cwd: string, timeoutMs: number): Promise<Step> {
  const t0 = Date.now();
  const proc = Bun.spawn(['bash', '-lc', cmd], { cwd, stdout: 'pipe', stderr: 'pipe' });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; proc.kill(9); }, timeoutMs);
  const [out, err] = await Promise.all([new Response(proc.stdout).text(), new Response(proc.stderr).text()]);
  const exit = await proc.exited;
  clearTimeout(timer);
  const text = (out + (err ? `\n[stderr]\n${err}` : '')).slice(0, 8000);
  return { cmd, exit, out: text, ms: Date.now() - t0, timeout: timedOut || undefined };
}

function processJob(job: Job): void {
  chain = chain.then(async () => {
    const dir = join(WORKROOT, job.id);
    job.status = 'cloning'; job.startedAt = new Date().toISOString();
    try {
      mkdirSync(dir, { recursive: true });
      const url = TOKEN
        ? `https://x-access-token:${TOKEN}@github.com/${OWNER}/${job.repo}.git`
        : `https://github.com/${OWNER}/${job.repo}.git`;
      const clone = await run(`git clone --depth 1 --branch ${job.ref} ${url} src`, dir, 90_000);
      if (clone.exit !== 0) {
        // PAT redaction: never echo clone output verbatim — it embeds the token URL on failure
        job.cloneError = clone.out.replace(/x-access-token:[^@]*@/g, 'x-access-token:REDACTED@').slice(0, 2000);
        job.status = 'failed'; job.finishedAt = new Date().toISOString();
      } else {
        const src = join(dir, 'src');
        job.status = 'running';
        for (const cmd of job.commands) {
          const step = await run(cmd.trim(), src, 300_000);
          job.steps.push(step);
          if (step.exit !== 0) break;
        }
        job.status = job.steps.every((s) => s.exit === 0 && !s.timeout) ? 'success' : 'failed';
        job.finishedAt = new Date().toISOString();
      }
    } catch (e: any) {
      job.cloneError = String(e?.message ?? e).slice(0, 1000);
      job.status = 'failed'; job.finishedAt = new Date().toISOString();
    } finally {
      try { rmSync(dir, { recursive: true, force: true }); } catch {}
      appendFileSync(RECEIPTS, JSON.stringify({
        id: job.id, repo: job.repo, ref: job.ref, status: job.status,
        commands: job.commands, exits: job.steps.map((s) => s.exit),
        ms: job.steps.reduce((a, s) => a + s.ms, 0),
        createdAt: job.createdAt, finishedAt: job.finishedAt,
      }) + '\n');
      if (jobs.size > 25) {
        const oldest = [...jobs.values()].filter((j) => j.finishedAt).sort((a, b) => a.createdAt.localeCompare(b.createdAt))[0];
        if (oldest) jobs.delete(oldest.id);
      }
    }
  });
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
}

// ---- §1 hardening (directive 1a173c6ac120ccb1): runner token gate — fail-closed ----
// POST /api/jobs executes repo code; the request plane MUST authenticate. Law:
//  · env RUNNER_TOKEN, else file /home/z/coord-work/vault/operator-token (vault-auth
//    custody file, shared with giant lib/vault-auth.ts), else self-minted 0600 (fail-closed
//    by construction: the caller cannot know it, every mutation 401s until custody sets it).
//  · header x-runner-token OR x-saos-operator; sha256+timingSafeEqual (no length/timing leak).
//  · GET /api/health stays open (transparency is the product); job listing requires token too
//    (job metadata + output echo is not public material).
function runnerToken(): string {
  const env = (process.env.RUNNER_TOKEN || '').trim();
  if (env) return env;
  try {
    const t = readFileSync('/home/z/coord-work/vault/operator-token', 'utf8').trim();
    if (t) return t;
  } catch { /* absent — self-mint below */ }
  const t = randomBytes(32).toString('hex');
  try {
    mkdirSync('/home/z/coord-work/vault', { recursive: true });
    writeFileSync('/home/z/coord-work/vault/operator-token', t + '\n', { mode: 0o600 });
  } catch { /* read-only fs — token lives only in this process's memory (still fail-closed) */ }
  console.error('[runner] RUNNER_TOKEN self-minted (0600 /home/z/coord-work/vault/operator-token) — set custody to operate remotely');
  return t;
}
const RT = runnerToken();
function runnerAuth(req: Request): Response | null {
  const provided = req.headers.get('x-runner-token') ?? req.headers.get('x-saos-operator') ?? '';
  if (!provided || !RT) return json({ ok: false, error: 'runner-token-required (x-runner-token; fail-closed)' }, 401);
  const a = createHash('sha256').update(provided, 'utf8').digest();
  const b = createHash('sha256').update(RT, 'utf8').digest();
  return timingSafeEqual(a, b) ? null : json({ ok: false, error: 'runner-unauthorized' }, 401);
}

Bun.serve({
  port: PORT,
  hostname: '127.0.0.1', // directive 1a173c6ac120ccb1 §1 — loopback bind; gateway-borne traffic still reaches via Caddy, which is why the token gate exists
  async fetch(req) {
    const url = new URL(req.url);
    const p = url.pathname;
    if (p === '/api/health') {
      const active = [...jobs.values()].filter((j) => !j.finishedAt).length;
      return json({ ok: true, service: 'sovereign-runner', v: 1, started, active, total: jobs.size, machine: 'sandbox', law: 'machine=runtime, GitHub=state', gate: 'x-runner-token (fail-closed on mutations + job reads)' });
    }
    if ((p === '/api/jobs' || !!p.match(/^\/api\/jobs\/[\w-]+$/))) {
      const deny = runnerAuth(req);
      if (deny) return deny;
    }
    if (p === '/api/jobs' && req.method === 'POST') {
      try {
        const body = (await req.json()) as { repo?: string; ref?: string; commands?: unknown };
        const repo = (body.repo ?? '').trim();
        const ref = (body.ref ?? 'main').trim() || 'main';
        if (!/^[A-Za-z0-9_.-]{1,100}$/.test(repo)) return json({ error: 'bad repo name' }, 400);
        if (!/^[A-Za-z0-9._\-/]{1,100}$/.test(ref)) return json({ error: 'bad ref' }, 400);
        const cmds = validateCommands(body.commands);
        if (typeof cmds === 'string') return json({ error: cmds }, 400);
        const job: Job = {
          id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
          repo, ref, commands: cmds, status: 'queued', createdAt: new Date().toISOString(), steps: [],
        };
        jobs.set(job.id, job);
        processJob(job);
        return json({ id: job.id }, 201);
      } catch {
        return json({ error: 'bad json' }, 400);
      }
    }
    if (p === '/api/jobs' && req.method === 'GET') {
      const list = [...jobs.values()].sort((a, b) => b.createdAt.localeCompare(a.createdAt)).map((j) => ({
        id: j.id, repo: j.repo, ref: j.ref, status: j.status, createdAt: j.createdAt,
        finishedAt: j.finishedAt, exits: j.steps.map((s) => s.exit),
      }));
      return json({ jobs: list });
    }
    const m = p.match(/^\/api\/jobs\/([\w-]+)$/);
    if (m && req.method === 'GET') {
      const j = jobs.get(m[1]);
      return j ? json(j) : json({ error: 'not found' }, 404);
    }
    return json({ error: 'no route' }, 404);
  },
});

console.log(`sovereign-runner v1 listening on :${PORT}`);
