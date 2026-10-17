# sovereign-runner — the fleet's own execution runtime (v1)

Machine = runtime. GitHub = state. GitHub Actions is NOT the runtime.

A tiny bun service that executes real development work on fleet repos:
`git clone (depth 1)` -> whitelisted commands -> real output -> JSONL receipts.

## Run
    bun install && bun run dev   # :3020

## API
- GET  /api/health         -> { ok, law: "machine=runtime, GitHub=state" }
- POST /api/jobs           { repo, ref, commands[1..5] } -> { id }
- GET  /api/jobs           -> list
- GET  /api/jobs/:id       -> full steps with real stdout/stderr + exit codes

## Command whitelist (v1)
ls / cat / wc -l / rg / read-only git / node --check / node --version /
bun install / bun test / bun run lint / tsc --noEmit / npm test

Denylist: shell substitution ($, backticks), ~, .., /home, pat.env, vault,
secret, .ssh, upload, &&, ||. Jobs run in an isolated temp dir, removed after.

## Trust boundary (honest)
Executes fleet-owned code on the fleet's own machine — same trust domain as
the agents themselves. No push-back to repos in v1; no secrets in jobs.

## Live-proven
2026-10-17: GridWatch clone -> node --check grid-watch.mjs -> exit 0 (28ms),
git log showed the monitor's own commit b5482aa. ops-forge listings exit 0.
