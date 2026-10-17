# SECURITY-INCIDENT — historical secret-material exposure & rotation runbook

Author: [phase0-zai] | Date: 2026-10-17 | Scope: roshpinacare-sys fleet (40 repos)
Method: paths and counts only — no secret material is quoted anywhere in this document.

## 1. Confirmed exposures (evidence-backed)

E1. Saosmartwallet — db/custom.db (the LIVE vault database: encrypted VaultEntry rows plus a sealed
    GateSession master key) was git-tracked on main until 2026-10-17. Removed from HEAD by [phase0-zai].
    Every historical version remains in git history. Anyone with repo read access (org members, leaked
    tokens, CI logs) could fetch encrypted blobs plus their historical seal material.
    RISK: medium-high (defense-in-depth breached; not plaintext).

E2. vault-home — pre-hardening trust design: ANY GitHub credential present on a machine could unwrap the
    master passphrase (vaultlib.sh credential discovery, lines 46-110; unwrap path ~183-217) and was then
    self-registered as a PERMANENT wrap (boot-sovereign.sh step 5, ~177-189; vault_register_credential).
    One leaked org token anywhere in history = standing vault access. Hardened by [phase0-zai] on 2026-10-17:
    discovery and self-registration are now fail-closed opt-ins (VAULT_ALLOW_DISCOVERY=1 /
    VAULT_ALLOW_WRAP_SELFREGISTER=1).
    ACTION FOR OWNER: inspect vault-home wraps/ directory for entries registered from unexpected machines;
    rotate the vault master passphrase and re-wrap (vault_new_pass flow) if any doubt exists.

E3. vault-home — boot merges the whole keyring to PLAINTEXT .env.local and agent-hq/.env
    (boot-sovereign.sh ~:154-156). Machine-local plaintext exposure by design.
    OWNER DECISION: acceptable only on single-tenant machines; recommend tmpfs or a secrets service later.

E4. vault-home — SSH deploy keys are installed "never-expiring" (boot-sovereign.sh step 4).
    ACTION: rotate deploy keys on a schedule; never-expiring keys contradict the rotation doctrine.

E5. Project-files — 10 zips in repo root; 6 contain .env files. Prior org triage counted 0 WIF / 0 PEM /
    0 credential-shaped lines. Independent re-triage deferred to the history-rewrite phase (no new evidence).

## 2. Investigated and CLEARED (false alarms — do not re-chase)

C1. saos-dex docs/archive/WORKLOG_PHASE6.md line 46 — WIF-shaped string VERIFIED NOT A KEY by offline
    base58check: decodes to 38 bytes, version byte 0x1c (not 0x80), checksum INVALID. Whole-file scan:
    0 candidates with valid WIF checksums. It is anchor/seal evidence — leave intact.

C2. "Corrupted CI triggers (a branch literally named a-i-n-close-bracket)" — ARTIFACT of a sandbox text
    mangler that eats open-bracket-plus-m sequences. TruthRail/FleetHQ workflows were healthy (they produced
    real receipts). A few content-neutral noise commits exist from that chase (a93845af, 94340a11, aad70d25).

C3. sandbox-private vault-backup.enc — VERIFIED NOT git-tracked and not present in the working tree.

## 3. Rotation runbook (owner hands, in priority order)

R1. vault master passphrase rotation + full re-wrap of keys.env.enc / fleet-rot2.keys.enc / rails.env.enc /
    ssh-keys.tar.enc, then prune wraps/ to exactly the credentials the operator approves.
R2. Rotate every GitHub PAT with repo scope (org-wide audit: Settings > Developer settings; check audit log
    for unknown token usage). Re-register only what is needed, with expiry dates.
R3. Rotate the never-expiring SSH deploy keys (fleet-vault tier) and add expiry.
R4. Saosmartwallet: revoke/rotate gate sessions and the sealed master key (custom.db lineage is exposed in
    history until the rewrite below).
R5. Soldier/agent keys (steem repo rot pipeline): rotate any key whose material ever passed through exposed
    paths; verify steem signer service health (it was observed dead since 2026-10-16 with nobody noticing —
    add a liveness probe while you are there).

## 4. Coordinated history rewrite (needs owner approval + all-agents window)

Targets (minimum): Saosmartwallet db/custom.db lineage; Project-files zips IF re-triage finds anything;
optional: saos-dex anchor doc (evidence value vs. risk — operator call).
Preconditions: (a) this file records the approved window; (b) all 9 agents idle; (c) post-rewrite force-push
is the ONLY permitted force-push; (d) every consumer re-clones; (e) vault bundles re-sealed afterwards.
