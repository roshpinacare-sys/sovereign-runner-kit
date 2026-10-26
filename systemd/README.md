# systemd/ — the scheduled plane of sovereign-runner-kit

Units that carry the 24/7 cadence on a **persistent host** (the owner's device).
On the sandbox box there is no systemd (PID 1 = tini, measured 2026-10-24) and
every locally-armed daemon is session-bounded (measured wave 19.85: both rescue
daemons died at sandbox session teardown minutes after arming, cycle-1 receipts
proving correct execution before death). These units are the constitutional
answer: `Restart=always` + kernel-flock single-instance + hash-linked receipts.

## Units

| unit | what it keeps alive | port(s) |
|---|---|---|
| `forge.service` | the estate execution engine (existing) | 3100 |
| `perpetual-host.service` | the self-building organs supervisor (§4 MASTER DIRECTIVE): organ-commander, saos-architect-daemon (fail-soft), issue-to-pr §9.3 cycle | 3047 / 3049 |
| `saos-hsm-runtime.service` | the production HSM signing runtime (§3.1, wave 20.1 — Saosmartwallet packages/hsm-runtime): token-gated SIGN-ONLY signing API, vault-path-only, deny-by-default, no broadcast route | 3155 |

## Install (persistent host)

```bash
cp systemd/forge.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now forge
cp systemd/perpetual-host.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now perpetual-host
```

## perpetual-host — what to verify after install

- `systemctl status perpetual-host` — active, restarting only on crash
- `curl -s http://127.0.0.1:3047/health` — organ-commander revived by the host
- `/home/z/audit/perpetual-host-heartbeat.json` — breathing every BEAT_MS (60s default)
- `/home/z/audit/perpetual-host-receipts.jsonl` — sha256 hash-linked (prevHash→hash), tamper-evident
- `/home/z/audit/perpetual-host.log` — honest verdicts (`alive|grace|wedged|pending|crash-loop|spawned-ok|spawn-failed|busy|no-work`)

## Laws encoded (scripts/perpetual-host.mjs, suite 34/34 green)

- flock single-instance (kernel authority) — a second instance exits honestly
- port-first authority — never duplicates a live organ (double TCP check)
- pidfile ownership law — never signals any process it did not spawn
- fail-soft pending — an organ whose entry file is not landed yet is recorded
  as `pending` and retried next beat (architect :3049 behaves this way until
  the wave lead lands it)
- crash-loop escalation — consecutive spawn failures arm exponential backoff
  (60s doubling, 30min cap), recorded in the heartbeat, never hidden

Falsifiable prediction: on a persistent host, this unit carries the beat across
session teardown and reboots; on this sandbox box only the nohup instance runs,
and it dies with the session — that boundary is measured and honest.
