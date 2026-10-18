# SOVEREIGN-EXECUTION — the free architecture (owner directive 2026-10-18)

**The owner's law:** no payments, no exposing private repos, everything sovereign on
our network, everything working — until the architecture PROVES the 1000/day claim.
**The measured wall:** private repos fail Actions at runner startup (org minutes/
spending limit — owner-only billing setting). Public repos are unlimited-free.

## The three free planes (no payment anywhere)

| Plane | Cost | What | Status |
|---|---|---|---|
| **Hosted-public** (`sovereign-executor` repo) | 0 — unlimited free public minutes | consolidated `fleet-beat` carrying fleet tasks incl. the OWNER-APPROVED write-path `economy-book` task; pseudonymous receipts | LIVE (hourly; write-path executed 2026-10-18, owner verbatim in `beat-tasks.json`) |
| **Self-hosted** (owner machines) | 0 — self-hosted runners consume no minutes | any lane declaring `runs-on: [self-hosted, sovereign]`; QUEUES (honest waiting) until a runner connects instead of instant-failing | script ready: `sovereign-runner-register.sh` (owner lane) |
| **Minute-lean scheduling** | 0 | fewer, longer, consolidated beats instead of many tiny runs | applied by design in the beat |

## The smart separation (what stays private)

- Private repos keep ALL content, books, and state. Nothing is exposed.
- The executor plane clones private repos only through the encrypted
  `SOVEREIGN_PAT` secret, in-memory, and publishes **pseudonymous** receipts only
  (`p-<sha256[:7]>` — undecodable without the owner's private name list).
- **Secret-surface law:** the executor allows ONLY `schedule` + `workflow_dispatch`
  triggers — no `pull_request` trigger may ever exist there (a fork PR could reach
  the secret). This law is written into the workflow header and the beat re-reads it.

## The private-lane routing law (for the 13 active private workflows)

`runs-on: [self-hosted, sovereign]` → jobs QUEUE until the owner's machine connects
(better: honest waiting, zero cost) — OR the task graduates into the executor beat as
a read-only task. Write-path tasks (books, pushes to private repos) are owner-gated —
and the first one is now EXECUTED (owner approval verbatim 2026-10-18, trace
1a14dd29d3341489): the `economy-book` task runs the book repo's OWN unmodified runner
under the book's own single-writer heartbeat lock. The lock IS the safety model: host
writer alive → honest SKIP; lock stale (sandbox wiped) → the executor adopts on free
minutes and the book keeps breathing. Receipts carry outcome words only — no book
content ever lands on the public plane. Every credential-bearing error string is
scrubbed (`clean()` leak-law) before anything can reach a public receipt.

## The 1000/day bridge (honest instrument, no fakes)

Measured today (receipts, not hopes):
- The yield engine is LIVE: verdict INTEL-OK, selftest 1823/1823 PASS, 480 candidates
  scanned per cycle, curation voter active on the chain (public receipt:
  `Autonomy/receipts/fleet-yield/last.json`).
- The bridge instrument (`yield-snapshot` task) now measures the cadence hourly on
  free minutes: receipts/day, voter status, engine health — the baseline series the
  owner needs to see move.

The gap math (why the wall mattered): the engines that could compound toward
1000/day sit on lanes that could not run. Free execution (this document) removes the
execution wall; the compounding levers — more voting capital, more engine cycles/day,
more lanes on free planes — are now unblocked and MEASURED instead of assumed.
