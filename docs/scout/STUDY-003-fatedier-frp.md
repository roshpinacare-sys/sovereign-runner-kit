# STUDY-003 — fatedier/frp (★109,967) → the reach-inversion pattern

- **Finding**: `fatedier/frp` — ★109,967, Apache-2.0, Go, active (pushed 2026-10-15).
  "A fast reverse proxy to help you expose a local server behind a NAT or firewall
  to the internet." TCP/UDP/HTTP/HTTPS + P2P connect mode.
- **Verdict in ledger**: STUDY — permissive license, no hard signals at vet.
- **Read**: README head, root tree, `conf/` listing (frpc.toml / frps.toml +
  full_example pair), via GitHub API only, 2026-10-18. Zero bytes copied.

## What they engineered well (the pattern, in our words)

1. **Reach inversion.** A roaming client behind NAT dials *out* to a public server;
   the server then exposes mapped ports on its side. Reach is achieved with zero
   inbound firewall rules — the client keeps initiating, the server only answers.
   A sovereign-but-roaming node stays reachable without owning network perimeter.
2. **Authenticated capability grant.** The client authenticates to the server with
   a shared token *before any proxy mapping is honored*. Reach requests are
   capability-gated, not port-scanned into existence.
3. **Config-as-registry, base + full extension.** `frpc.toml`/`frps.toml` minimal
   bases plus `*_full_example.toml` as the documented extension surface — the same
   base+extension shape we adopted from STUDY-001, independently invented here.
4. **Health-check-first failover.** Proxies declare health checks; traffic routes
   to live endpoints and routes around dead ones. Reach is a *measured* property,
   not an assumed one.

## The original SAOS adaptation

Our fleet already lives this pattern's core insight without the tunnel: every agent
lane is a "client behind NAT" (GitHub-hosted runners) that dials out to its chain
RPCs and APIs, and the owner reaches the fleet *through git* — a committed receipt
is a published port. What wave-17 adds is the measurement half:

- The **scout route ladder** (direct → wayback → honest-blocked) and the census's
  new **repo-level Actions kill-switch sweep** (wave-17) are our reach map: every
  route outcome recorded, every wall measured, nothing assumed reachable.
- **STUDY-002's Law 9 + agent-shield (wave-17)** gate what the outside can hand our
  agents; frp's authenticated-grant idea is the *inbound* mirror.

## Where this leads (proposals — owner-gated per law 8)

1. **Token-gated mini-service registry**: our gateway routes by port
   (`XTransformPort`) with no capability check; a future gateway iteration can
   adopt the authenticated-grant shape — token before route — implemented
   originally in our stack when that work is scheduled.
2. **Fleet-to-fleet direct transfer study**: frp's P2P/visitor mode is the shape
   for direct hive/steem receipt sync between roaming nodes; study-only until a
   real requirement exists.

## Lineage statement (honesty)

Read 2026-10-18 via GitHub API (repo meta, README.md head, root listing, conf/
listing). No code or text copied; this document, the deploy-gate lane, and the
agent-shield lane are original SAOS engineering informed by studied patterns.
Ledger entry `fatedier/frp` (STUDY) carries this study as its integration record.
