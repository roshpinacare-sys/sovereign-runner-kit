# capability-gate — the authenticated-grant pattern, originally ours (STUDY-003)

**Lineage (honesty law):** STUDY-003 read fatedier/frp (★109,967, Apache-2.0) via the
GitHub API — README head, tree, conf listing — and extracted a PATTERN: reach is
capability-gated (authenticate before any mapping is honored), not port-scanned into
existence. `scripts/capability-gate.py` is that pattern re-implemented from zero in
our stack. Zero bytes copied; no frp code, config, or text appears anywhere in this
repo. Owner approval: «תמשיך תעשה את זה בעצמך ... תמשיך ודחוף» 2026-10-18
(IM zai-web session web-16cb7ad8, trace 1a14d58a69eb45f1).

## The five laws (fail-closed, selftest-proven daily)

| Law | Statement | Proof |
|---|---|---|
| L1 deny-closed | unknown route, missing token, unreadable OR malformed registry → DENY. A gate that cannot verify denies; it never falls open. | checks 3–6 |
| L2 fingerprints only | the registry holds sha256(token) — 64 lowercase hex — never token material. | checks 7–8 |
| L3 constant-time | comparison via `hmac.compare_digest`; no early-exit match. | check 9 |
| L4 issue-once | `--issue` prints the token once to stdout (memory-only); only the fingerprint persists. | check 1–2 cycle |
| L5 evidence-clean | verdicts carry reason codes; denial evidence never echoes the presented material. | check 8, 10 |

Selftest receipt: `state/capability-gate-last-run.json` (lane `capability-gate.yml`,
daily 07:53Z + dispatch, receipt-before-eval order).

## Consumer contract (how a mini-service mounts it)

```bash
# one-time per route (operator surface — the token is printed ONCE, never stored):
python3 scripts/capability-gate.py --issue svc/my-route

# at every consumer request, before honoring the route:
CAP_TOKEN="$presented" python3 scripts/capability-gate.py --gate svc/my-route
# exit 0 = allow, exit 1 = deny (reason on stdout, evidence-clean)
```

Node/bun consumers may import the same law natively: registry in
`state/capability-registry.json`, comparison `crypto.timingSafeEqual` over sha256,
deny-closed on any anomaly — mirror the five laws exactly; the Python file is the
reference implementation and the selftest is the contract.

## Where it plugs in (owner-gated adoption)

- **Sandbox gateway** (`XTransformPort` routing): today port-routing carries no
  capability check; a gateway iteration can require a capability per protected route
  before forwarding. NOT wired here — machine infra is owner territory; the gate
  ships as the drop-in decision function.
- **Fleet mini-services** (bus, chat, any TCP surface): mount `gate()` first line —
  same shape frp taught: authenticate, THEN map.

## What this closes

STUDY-003's proposal #1 ("token-gated mini-service registry — a future gateway
iteration can adopt the authenticated-grant shape") is now ORIGINAL ENGINEERING in
the kit, standing and self-proving, instead of a proposal. Proposal #2
(fleet-to-fleet direct transfer study) remains study-only until a real requirement
exists (honesty law: no speculative surfaces).
