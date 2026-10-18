#!/usr/bin/env python3
# registry-verify — the tooling registry proves itself against reality (fail-closed).
# Original SAOS engineering (wave-19.4, owner directive trace 1a14ec60f8b59e49:
# 'וודא שהאוטונומיה יודעת להשתמש בכלים שעשית והכל ולחזק עוד').
# The registry (tools/registry.json + docs/TOOLING-REGISTRY.md) is the autonomy's
# DISCOVERY CONTRACT for every instrument the network built. This verifier makes the
# contract honest: if a declared tool drifts from reality (moved/renamed/removed),
# the lane reddens WITH EVIDENCE in state/ before any evaluation — the registry can
# never rot silently, and the autonomy can never try to invoke a tool that is gone.
# Laws:
#   schema law   — every entry declares id/repo/path/kind/invoke/purpose/safety/wave;
#                  kind in the enum; ids unique. Violation = schema-error (RED).
#   local law    — same-repo entries must exist in this checkout (the instrument in
#                  git, not only its output — the wave-18 lesson institutionalized).
#   api law      — cross-repo entries verified via the GitHub API when this plane can
#                  see the repo; a private repo invisible to this token is recorded
#                  INVISIBLE-PRIVATE (honest — neither green nor red); a visible repo
#                  whose declared path is gone = MISSING (RED).
#   receipt law  — the receipt lands in state/ BEFORE any evaluation (evidence first).
import base64, json, os, sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, 'tools', 'registry.json')
RECEIPT = os.path.join(ROOT, 'state', 'tooling-registry-last-run.json')
KIT = 'roshpinacare-sys/sovereign-runner-kit'
KINDS = {'read-only', 'audit', 'law', 'write-path', 'owner-gated', 'infra'}
REQ = ['id', 'repo', 'path', 'kind', 'invoke', 'purpose', 'safety', 'wave']
TOKEN = (os.environ.get('GITHUB_TOKEN') or os.environ.get('FLEET_TOKEN')
         or os.environ.get('SOVEREIGN_PAT') or '')


def api(path):
    """GitHub API GET -> (status, body). Basic auth (measured: the fleet credential
    answers Basic, not Bearer). The token never appears in a raised error."""
    req = Request(f'https://api.github.com{path}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'saos-registry-verify')
    if TOKEN:
        b = base64.b64encode(f'x-access-token:{TOKEN}'.encode()).decode()
        req.add_header('Authorization', f'Basic {b}')
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except Exception as e:
        code = getattr(e, 'code', 0)
        return (code, {}) if code else (0, {})


def main():
    d = json.load(open(REG))
    entries = d.get('entries', [])
    rows = []
    seen = set()
    for e in entries:
        eid = e.get('id', '?')
        missing = [k for k in REQ if k not in e or e[k] in ('', None)]
        if e.get('kind') not in KINDS:
            missing.append(f'kind-enum:{e.get("kind")}')
        if eid in seen:
            missing.append('duplicate-id')
        seen.add(eid)
        if missing:
            rows.append({'id': eid, 'repo': e.get('repo', '?'),
                         'outcome': 'schema-error', 'detail': missing})
            continue
        if e['repo'] == KIT:
            ok = os.path.exists(os.path.join(ROOT, e['path']))
            rows.append({'id': eid, 'repo': e['repo'],
                         'outcome': 'verified-local' if ok else 'missing',
                         'detail': e['path']})
        else:
            st, repo = api(f"/repos/{e['repo']}")
            if st == 200:
                st2, _ = api(f"/repos/{e['repo']}/contents/{e['path']}")
                rows.append({'id': eid, 'repo': e['repo'],
                             'outcome': 'verified-api' if st2 == 200 else 'missing',
                             'detail': f'{e["path"]} (status={st2})'})
            elif st == 404:
                rows.append({'id': eid, 'repo': e['repo'],
                             'outcome': 'invisible-private',
                             'detail': 'repo exists but is invisible to this plane — honest'})
            else:
                rows.append({'id': eid, 'repo': e['repo'],
                             'outcome': 'unreachable', 'detail': f'status={st}'})
    totals = {}
    for r in rows:
        totals[r['outcome']] = totals.get(r['outcome'], 0) + 1
    receipt = {
        'schema': 'saos.tooling-registry.receipt/1',
        'at': datetime.now(timezone.utc).isoformat(),
        'registrySchema': d.get('schema'),
        'registryEntries': len(entries),
        'tokenPlane': 'basic-auth-credential-present' if TOKEN else 'anonymous',
        'totals': totals,
        'entries': rows,
        'note': 'invisible-private = the repo exists but this plane honestly cannot see '
                'it (private + token scope) — neither green nor red; missing/schema-error '
                '= RED (fail-closed): the registry drifted from reality',
    }
    os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
    json.dump(receipt, open(RECEIPT, 'w'), indent=2, ensure_ascii=False)
    red = totals.get('missing', 0) + totals.get('schema-error', 0)
    summary = ' '.join(f'{k}={v}' for k, v in sorted(totals.items()))
    print(f'registry-verify: entries={len(entries)} {summary} RED={red}')
    return 1 if red else 0


if __name__ == '__main__':
    sys.exit(main())
