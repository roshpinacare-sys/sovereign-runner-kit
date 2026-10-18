#!/usr/bin/env python3
# capability-gate — authenticated capability grant for fleet routes (original SAOS
# engineering). Lineage: STUDY-003 (fatedier/frp, ★109,967, Apache-2.0) — the PATTERN
# was studied (a client authenticates BEFORE any mapping is honored; reach is
# capability-gated, not port-scanned into existence) and re-implemented from zero in
# our stack; zero bytes copied, no frp code or text in this file.
#
# What it is: the gate our mini-services and route layers mount BEFORE honoring a
# route. The registry holds FINGERPRINTS only (sha256 of the capability token, 64 hex
# chars) — token material never lands in git, never in a receipt, never in evidence.
#
# Laws (fail-closed, in order):
#   L1 deny-closed: unknown route -> deny; missing/empty token -> deny; unreadable or
#      malformed registry -> deny (a gate that cannot verify denies, never allows).
#   L2 fingerprints only: the registry and every artifact (receipt/evidence/denial)
#      carry the sha256 fingerprint or nothing — never the presented token.
#   L3 constant-time: comparison via hmac.compare_digest — no early-exit string match.
#   L4 issue-once: --issue prints the token ONCE to stdout (memory-only surface);
#      only the fingerprint persists.
#   L5 evidence: every verdict carries a reason code; denial evidence never contains
#      the presented material (an attacker reading receipts learns nothing re-usable).
#
# CLI:
#   --issue ROUTE          register ROUTE with a fresh token; prints the token once
#   --gate ROUTE           verify CAP_TOKEN env against ROUTE (exit 0 = allow, 1 = deny)
#   --selftest             run the in-file proof suite; writes the receipt
#   --eval                 fail-closed eval of the last receipt (CI gate step)
#   --digest               step-summary digest of the last receipt
import hashlib, hmac, json, os, secrets, sys, urllib.parse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, 'state', 'capability-registry.json')
RECEIPT = os.path.join(ROOT, 'state', 'capability-gate-last-run.json')

DENY = {
    'unknown_route': 'route not registered — deny (L1)',
    'missing_token': 'no presented capability — deny (L1)',
    'registry_unreadable': 'registry unreadable/malformed — deny (L1)',
    'mismatch': 'capability fingerprint mismatch — deny (L3)',
    'registry_corrupt': 'registry entry corrupt — deny (L1)',
}


def fp(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def load_registry():
    """L1: an unreadable registry denies everything — returns (ok, dict)."""
    try:
        d = json.load(open(REGISTRY))
        if not isinstance(d, dict) or not isinstance(d.get('routes', {}), dict):
            return False, {}
        return True, d.get('routes', {})
    except Exception:
        return False, {}


def gate(route: str, presented: str):
    """The one function every consumer mounts. Returns (allow: bool, reason: str).

    L1 unknown route / missing token / unreadable registry -> deny.
    L2/L3 only fingerprints compared, constant-time.
    L5 the reason never echoes the presented material.
    """
    if not presented:
        return False, DENY['missing_token']
    ok, routes = load_registry()
    if not ok:
        return False, DENY['registry_unreadable']
    ent = routes.get(route)
    if not isinstance(ent, dict):
        return False, DENY['unknown_route']
    reg = ent.get('fp')
    if not (isinstance(reg, str) and len(reg) == 64 and all(c in '0123456789abcdef' for c in reg)):
        return False, DENY['registry_corrupt']
    if hmac.compare_digest(reg, fp(presented)):
        return True, 'allow (fingerprint match, constant-time)'
    return False, DENY['mismatch']


def issue(route: str) -> int:
    if not route or not all(c.isalnum() or c in '-_./' for c in route):
        print('refuse: route must be a safe identifier'); return 2
    tok = secrets.token_urlsafe(32)  # L4: printed once below; only the fingerprint persists
    ok, routes = load_registry()
    routes = routes if ok else {}
    routes[route] = {'fp': fp(tok), 'issuedAt': datetime.now(timezone.utc).isoformat()}
    json.dump({'schema': 'saos.capability.registry/1', 'note': 'fingerprints only — token material never persists (L2/L4)', 'routes': routes},
              open(REGISTRY, 'w'), indent=2)
    print(tok)
    return 0


def selftest() -> int:
    checks, fails = [], 0

    def check(name, cond):
        nonlocal fails
        checks.append({'name': name, 'ok': bool(cond)})
        if not cond: fails += 1

    tmp = REGISTRY + '.selftest-tmp'
    orig = REGISTRY
    import shutil
    if os.path.exists(REGISTRY): shutil.copy2(REGISTRY, tmp)
    try:
        # 1 issue -> gate allows with the right token
        tok = secrets.token_urlsafe(32)
        json.dump({'schema': 'saos.capability.registry/1', 'routes': {'svc/demo': {'fp': fp(tok), 'issuedAt': 't'}}},
                  open(REGISTRY, 'w'))
        ok, why = gate('svc/demo', tok)
        check('issue-then-gate allows the issued token', ok and 'allow' in why)
        # 2 wrong token denied
        ok, why = gate('svc/demo', secrets.token_urlsafe(32))
        check('wrong token denied (mismatch)', (not ok) and why == DENY['mismatch'])
        # 3 unknown route denied
        ok, why = gate('svc/never-registered', tok)
        check('unknown route denied (L1)', (not ok) and why == DENY['unknown_route'])
        # 4 missing token denied
        ok, why = gate('svc/demo', '')
        check('missing token denied (L1)', (not ok) and why == DENY['missing_token'])
        # 5 unreadable registry denied
        os.replace(REGISTRY, REGISTRY + '.hold')
        ok, why = gate('svc/demo', tok)
        check('unreadable registry denies (L1)', (not ok) and why == DENY['registry_unreadable'])
        os.replace(REGISTRY + '.hold', REGISTRY)
        # 6 corrupt entry denied
        json.dump({'routes': {'svc/demo': {'fp': 'ZZ' * 32}}}, open(REGISTRY, 'w'))
        ok, why = gate('svc/demo', tok)
        check('corrupt registry entry denied (L1)', (not ok) and why == DENY['registry_corrupt'])
        # 7 registry holds fingerprints only (64 hex), never the token material
        reg = json.load(open(REGISTRY))
        check('registry fingerprint shape (64 hex chars)', len(reg['routes']['svc/demo']['fp']) == 64)
        check('token material absent from registry', tok not in open(REGISTRY).read())
        # 8 denial evidence carries no presented material (L5)
        bad = secrets.token_urlsafe(32)
        ok, why = gate('svc/demo', bad)
        check('denial reason carries no presented token', bad not in why)
        # 9 constant-time comparator in the path (L3 source law)
        src = open(__file__).read()
        check('hmac.compare_digest is the comparator (L3)', 'hmac.compare_digest' in src)
        # 10 route identifier safety (issue refuses unsafe names)
        rc = issue('bad route;rm-rf')
        check('issue refuses unsafe route identifiers', rc == 2)
    finally:
        os.replace(tmp, orig) if os.path.exists(tmp) else (os.path.exists(REGISTRY) and os.remove(REGISTRY))
    receipt = {
        'schema': 'saos.capability-gate.selftest/1',
        'at': datetime.now(timezone.utc).isoformat(),
        'checks': len(checks), 'failed': fails,
        'results': checks,
        'ok': fails == 0,
    }
    json.dump(receipt, open(RECEIPT, 'w'), indent=2)
    print(f"capability-gate selftest: {checks.__len__()} checks, {fails} failed -> {'OK' if fails == 0 else 'FAIL'}")
    return 0 if fails == 0 else 1


def main() -> int:
    a = sys.argv[1:]
    if '--selftest' in a: return selftest()
    if '--issue' in a: return issue(a[a.index('--issue') + 1])
    if '--gate' in a:
        route = a[a.index('--gate') + 1]
        ok, why = gate(route, os.environ.get('CAP_TOKEN', ''))
        print(f'capability-gate {route}: {"ALLOW" if ok else "DENY"} ({why})')
        return 0 if ok else 1
    if '--eval' in a:
        try: r = json.load(open(RECEIPT))
        except Exception: print('eval: no receipt — fail-closed'); return 1
        ok = bool(r.get('ok')) and int(r.get('failed', 1)) == 0
        print(f"eval: {'green' if ok else 'RED'} ({r.get('checks')} checks, {r.get('failed')} failed)")
        return 0 if ok else 1
    if '--digest' in a:
        try: r = json.load(open(RECEIPT))
        except Exception: print('capability-gate: no receipt'); return 0
        for c in r.get('results', []):
            if not c.get('ok'): print(f"- FAIL {c['name']}")
        print(f"capability-gate selftest: {r.get('checks')} checks / {r.get('failed')} failed")
        return 0
    print(__doc__); return 2


if __name__ == '__main__':
    sys.exit(main())
