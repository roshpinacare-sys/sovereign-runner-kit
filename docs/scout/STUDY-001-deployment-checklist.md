# STUDY-001 — deployment-checklist (PinoyFreeCoder) → the SAOS verdict-contract pattern

- **Finding**: `PinoyFreeCoder/deployment-checklist` — ★48, language-agnostic pre-deploy
  checklist with a deep security section, shipped in two consumable forms: a human
  checklist (`checklists/base.md` + stack extensions) and an **agent contract** (`agent.md`).
- **Verdict in ledger**: CAUTION (`no_spdx_license`) — pattern study is allowed and done here;
  **zero bytes were copied** (law 2 of SCOUT-PROTOCOL.md). Everything below is our own design,
  informed by reading theirs.
- **Vet evidence**: static read of README/agent.md/_template.md via API (2026-10-17);
  no install scripts, no CI workflows in repo — no hard signals.

## What they engineered well (the pattern, in our words)

1. **One source of truth, two consumers.** The same checklist serves humans (tick boxes,
   sign off) and agents (a strict output contract). No second copy to drift.
2. **Severity tiers that gate action.** `[BLOCKER]`/`[SHOULD]`/`[NICE]` — a BLOCKER left
   unchecked = no deploy. Tiers convert a document into a *decision function*.
3. **Verify-not-assume + evidence citation.** The agent contract demands, per item:
   `PASS / FAIL / N/A`, each with a file:line / config / command-output citation. N/A needs a reason.
4. **Report-only guardrails.** The agent must NOT deploy, must NOT run destructive commands,
   must NOT fix — it lists fixes and waits for approval. Read-only audit, human pull.
5. **Base + extension layering.** A universal base; stack files only *add* items, never
   replace; a template file makes extension a mechanical act.

## The original SAOS adaptation (what WE built from it — different domain, different shape)

Their pattern is per-deploy human review of one repo. Our domain is an autonomous fleet
scanning *hundreds of external repos* without a human per item. So the adaptation is not a
copy — it inverts the consumer (machine-first) and hardens the failure mode (fail-closed):

| Theirs (deployment-checklist) | Ours (SCOUT-PROTOCOL + scout-scan.py) |
|---|---|
| GO / NO-GO verdict per deploy | `STUDY / CAUTION / REJECT / GONE` per finding, recorded in a dedup ledger with verdict history |
| Agent cites file:line evidence | Every verdict carries `reasons[]` + `evidence{}` (script keys, flagged workflow paths) — a verdict without evidence cannot enter the ledger |
| BLOCKER = no deploy | Hard signal = `REJECT` = **quarantine forever**, record as threat intel; only the owner overturns |
| "Do NOT fix, wait for approval" | Law 8: the scout *proposes* (`STUDY-*.md`), the owner *disposes*; no automated merge into production lanes, ever |
| severity legend in a doc | machine-enforced regex classes in `scripts/scout-scan.py` (install-script network/exec primitives, `curl \| sh`, `pull_request_target`) |
| base.md + stack extensions | `state/scout-sources.json`: base source types (`github_user_repos`, `mcp_catalog`, `web_page`) + registry file — **adding a source is a data edit, never a code edit** |
| run once per release | daily cadence (`scout-loop.yml`), budgeted enrichment (new findings first), route-honest fetch ladder |

## Where this leads (proposals — owner-gated, not self-merged)

1. **Fleet deploy-gate (original)**: an agent-facing checklist lane that audits OUR repos
   before publishing lanes fire — same tier grammar (`BLOCKER/SHOULD/NICE` as
   `gate: red/yellow/green`), same evidence contract, output as a committed receipt.
   Candidate first target: `sovereign-runner-kit` itself (it publishes state).
2. **MCP catalog as standing source (measured working)**: the presentation layer challenges
   browser-like UAs (Cloudflare), but the MCP JSON-RPC data plane answered 200 from a plain
   origin with a neutral UA (2026-10-17, measured) — recall test returned 189 unique curated
   repos across a 12×9 word×category grid. The loop takes a polite rotating slice per day
   (full grid ≈ 3 days); route outcomes are recorded per source, so the fleet builds its own
   reach map over time. New STUDY-grade findings enter the ledger; studies get written here.
3. **Vet-depth ladder (v2)**: today 4 file fetches per repo; next, parse dependency
   manifests for typosquat distance against a pinned allowlist, and diff-vet on
   re-scan (only re-vet repos whose pushed_at moved).

## Lineage statement (honesty)

Read: 2026-10-17, via GitHub API raw reads of `README.md`, `agent.md`,
`checklists/_template.md`, `checklist.md` (heads). No code or text was copied; this
document and `scripts/scout-scan.py` are original SAOS engineering. The ledger records
the source as CAUTION (no SPDX license) — study-only posture, which this study honors.
