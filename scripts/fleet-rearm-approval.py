#!/usr/bin/env python3
# fleet-rearm-approval — enable the keptOff lanes upon explicit owner approval.
# Truth law: every lane verified via API *after* the enable PUT; receipt written to state/.
# Owner approval record: blanket "מאשר הכל" (approve everything) via IM zai-web session web-16cb7ad8.
# Idempotent: already-active lanes are verified and recorded, not re-toggled.
import json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

ORG = 'roshpinacare-sys'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # runner-kit root
LEDGER = os.path.join(ROOT, 'state', 'rearm-ledger.json')
RECEIPT = os.path.join(ROOT, 'state', 'rearm-approval-wave14.json')
LOCAL_AUDIT = '/home/z/audit'

def token():
    for k in ('FLEET_TOKEN', 'GITHUB_TOKEN'):
        v = os.environ.get(k)
        if v: return v.strip()
    return open('/home/z/my-project/upload/pat.env').read().strip()

TOKEN = token()

def api(url, method='GET', expect=None):
    req = urllib.request.Request(url, method=method, headers={
        'Authorization': f'Bearer {TOKEN}',
        'User-Agent': 'fleet-rearm-approval',
        'Accept': 'application/vnd.github+json',
    })
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        return e.code, {'error': body}
    except Exception as e:
        return 0, {'error': str(e)[:200]}

def triggers(local_path):
    """Classify the workflow trigger from the YAML in the local clone (informational only)."""
    try:
        txt = open(local_path).read()
    except Exception:
        return 'unknown'
    kinds = []
    if re.search(r'^\s*schedule:', txt, re.M): kinds.append('schedule')
    if re.search(r'^\s*workflow_dispatch:', txt, re.M): kinds.append('dispatch')
    if re.search(r'^\s*push:', txt, re.M): kinds.append('push')
    return '+'.join(kinds) if kinds else 'manual-only'

def main():
    ledger = json.load(open(LEDGER))
    kept = ledger.get('keptOff', [])
    if not kept:
        print('keptOff empty — nothing to approve.'); return
    results, moved = [], []
    for e in kept:
        repo, wf = e['repo'], e['wf']
        path = f'.github/workflows/{wf}'
        st, data = api(f'https://api.github.com/repos/{ORG}/{repo}/actions/workflows?per_page=100')
        if st != 200:
            results.append({**e, 'result': f'LIST_FAIL({st})', 'detail': str(data.get('error',''))[:120]}); continue
        match = next((w for w in data.get('workflows', []) if w['path'] == path), None)
        if match is None:
            results.append({**e, 'result': 'NOT_FOUND', 'detail': f'{path} not in workflows list'}); continue
        wid, before = match['id'], match['state']
        if before == 'active':
            results.append({**e, 'result': 'ALREADY_ACTIVE', 'id': wid, 'trigger': triggers(f'{LOCAL_AUDIT}/{repo}/{path}')})
            moved.append({**e, 'id': wid}); continue
        st2, _ = api(f'https://api.github.com/repos/{ORG}/{repo}/actions/workflows/{wid}/enable', method='PUT')
        if st2 not in (200, 204):
            results.append({**e, 'result': f'ENABLE_FAIL({st2})', 'id': wid, 'detail': str(_)}); continue
        time.sleep(0.4)
        st3, w3 = api(f'https://api.github.com/repos/{ORG}/{repo}/actions/workflows/{wid}')
        after = w3.get('state', '?') if st3 == 200 else f'VERIFY_FAIL({st3})'
        results.append({**e, 'result': 'ENABLED_VERIFIED' if after == 'active' else 'ENABLED_UNVERIFIED',
                        'id': wid, 'before': before, 'after': after,
                        'trigger': triggers(f'{LOCAL_AUDIT}/{repo}/{path}')})
        if after == 'active': moved.append({**e, 'id': wid})
        time.sleep(0.2)

    ok = [r for r in results if r['result'] in ('ENABLED_VERIFIED', 'ALREADY_ACTIVE')]
    bad = [r for r in results if r['result'] not in ('ENABLED_VERIFIED', 'ALREADY_ACTIVE')]
    receipt = {
        'approval': {
            'by': 'owner (roshpinacare-sys)',
            'scope': 'blanket — all 42 keptOff money/key/execution lanes',
            'verbatim': 'כן תעשה מאשר הכל תמשיך',
            'via': 'IM gateway zai-web, session web-16cb7ad8-b07d-40c0-bff6-116022a3f2c1',
            'at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'standingProhibitionsUnchanged': ['PAT/WIF rotation', 'vault contents', 'vault-home decoupling'],
        },
        'summary': {'requested': len(kept), 'verified_active': len(ok), 'failed': len(bad)},
        'results': results,
    }
    os.makedirs(os.path.dirname(RECEIPT), exist_ok=True)
    json.dump(receipt, open(RECEIPT, 'w'), ensure_ascii=False, indent=2)
    if moved:
        ledger['keptOff'] = [e for e in kept if e not in moved]
        ledger['enabledWave14'] = ledger.get('enabledWave14', []) + moved
        ledger['approval'] = receipt['approval']
        json.dump(ledger, open(LEDGER, 'w'), ensure_ascii=False, indent=2)
    print(f"REQUESTED {len(kept)} · VERIFIED_ACTIVE {len(ok)} · FAILED {len(bad)}")
    for r in bad: print('  FAIL', r['repo'], r['wf'], r['result'])
    trig = {}
    for r in ok: trig.setdefault(r.get('trigger','?'), []).append(f"{r['repo']}/{r['wf']}")
    for t, lanes in sorted(trig.items()): print(f"  trigger[{t}]: {len(lanes)}")

if __name__ == '__main__':
    main()
