# hsm-runtime boot proof — G77-d (wave 20.1)

**What this proves:** `Saosmartwallet · packages/hsm-runtime` — the production
HSM signing runtime (owner directive §3.1, the component measured as
"רכיב הארנק והחתימות המרובה עדיין מוגדר כפרוטוטיפ — טרם-נפרס") — **boots and
serves on sovereign-runner-kit**, answers an honest per-capability health
plane, signs with keys it cannot expose, and refuses every wrong path. The
machine-checkable receipt is `boot-proof.json` (same directory).

- **Date:** 2026-10-26 (UTC) · **Task:** G77-d · **Branch:**
  `Saosmartwallet feat/hsm-production`
- **Boot:** `bun packages/hsm-runtime/bin/hsm-runtime.ts --serve --port 3155`
  via nohup on this sandbox box (session-bounded — the persistent host runs the
  systemd unit `systemd/saos-hsm-runtime.service`). Listening line captured
  verbatim; vault dir is a PATH, never a key.

## Measured matrix (all probes captured in boot-proof.json)

| Probe | Result | Meaning |
|---|---|---|
| `GET /health` (no auth) | **200** `{ok:true, mode:"SIGN-ONLY", broadcast:"DISABLED"}` | bare liveness — zero operational data |
| `GET /status` (no credential) | **401** `HSM_E_AUTH_MISSING` | deny-by-default |
| `GET /status` (wrong token) | **403** `HSM_E_AUTH_INVALID` | constant-time compare, no oracle |
| `POST /broadcast` | **404** | the side-effect law is STRUCTURAL — the route does not exist |
| `GET /status` (armed) | **200** `vault:OPEN · signing:READY · token:SET · keys:{ed25519:1, secp256k1-wif:1}` | per-capability verdicts, measured |
| `POST /keys` (armed) | **200** ids/types/meta only | fixture provenance carried in meta |
| `POST /sign/steem` (fixture posting key, custom_json) | **200** receipt `digest/txId/wireSha256` | steem-family wire truth |
| `POST /sign/bytes` (fixture ed25519 key) | **200** receipt `digest/wireSha256/signatureHex` | ed25519 route |
| `POST /sign/steem` (posting key × `transfer`) | **422** `HSM_E_ROLE_POLICY` | funds-class ops refuse posting authority |
| oversized body | **413** `HSM_E_BODY_TOO_LARGE` | bounded inputs |

## `--once` CI provability (honest exit codes, measured)

| Environment | Exit |
|---|---|
| armed + fixture vault (READY) | **0** — proof receipt `27f92c89…be512ca` (ed25519, fixture key) |
| open vault + no token | **4** BLOCKED-AUTH |
| open vault + token + zero keys | **3** NO-KEYS |
| no vault + no token | **2** SEALED |

## Honest limits (loud, not hidden)

1. **READY here means fixture keys.** Every signing proof used SELF-GENERATED
   fixture keys minted in-session (provenance string carried in vault meta).
   Zero soldier/real custody keys are loaded — key loading is the owner's
   custody flow, and the runtime will honestly report NO-KEYS until then.
2. **The sandbox boot is session-bounded** (the fleet's measured lesson): the
   nohup instance was stopped after the proof. Persistence on the owner device
   is the systemd unit's job (`Restart=always`).
3. **The kit holds no keys** — receipts and a systemd unit only. The vault
   master key lives in `SAOS_VAULT_MASTER_KEY` (read by packages/vault), the
   API token in `HSM_SIGNING_TOKEN`, both owner-provisioned in a 0600 env file
   (path in the unit file, never in git).
