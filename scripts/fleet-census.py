#!/usr/bin/env python3
# fleet-census — measured state of every workflow in the fleet (truth law: numbers with source).
# Dynamic repo enumeration (no hardcoded rosters — /users/ primary, honest error on failure).
# CI mode: FLEET_TOKEN (or GITHUB_TOKEN) env. Local mode: /home/z/my-project/upload/pat.env fallback.
import json, re, urllib.request, os

def token():
    for k in ('FLEET_TOKEN', 'GITHUB_TOKEN'):
        v = os.environ.get(k)
        if v: return v.strip()
    try:
        return open('/home/z/my-project/upload/pat.env').read().strip()
    except Exception:
        return None

TOKEN = token()
ORG = 'roshpinacare-sys'
OUT = os.environ.get('CENSUS_OUT', 'state/fleet-census.json')
BLOCK = __import__('re').compile(r'pay|escrow|treasur|custod|rotat|claim|anchor|wallet|defi|arb-|arb_|-arb|mm-|estate|key|decid|vault|soldier|desk|voice|blurt|execut|wif|sign|seal|heal', re.I)

def api(url):
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {TOKEN}', 'User-Agent': 'fleet-keeper'})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

repos = [r['name'] for r in api(f'https://api.github.com/users/{ORG}/repos?per_page=100')]
census = {}
tot_a = tot_d = tot_m = 0
redboard = []
for repo in repos:
    try:
        wfs = api(f'https://api.github.com/repos/{ORG}/{repo}/actions/workflows?per_page=100').get('workflows', [])
        runs = api(f'https://api.github.com/repos/{ORG}/{repo}/actions/runs?per_page=100').get('workflow_runs', [])
    except Exception as e:
        census[repo] = {'error': str(e)[:120]}
        continue
    latest = {}
    for run in runs:
        k = run['path']
        if k not in latest:
            latest[k] = {'conclusion': run['conclusion'] or 'running', 'at': run['created_at']}
    rows = []
    for w in wfs:
        path = w['path']; last = latest.get(path)
        streak = 0
        for run in runs:
            if run['path'] != path: continue
            if (run['conclusion'] or 'running') == 'failure': streak += 1
            else: break
        rows.append({'wf': path.split('/')[-1], 'state': w['state'],
                     'moneyLane': bool(BLOCK.search(path)), 'last': last,
                     'redStreak': streak if last and last['conclusion'] == 'failure' else 0})
    a = sum(1 for r in rows if r['state'] == 'active'); d = len(rows) - a
    m = sum(1 for r in rows if r['moneyLane'])
    tot_a += a; tot_d += d; tot_m += m
    reds = [{'wf': r['wf'], 'redStreak': r['redStreak']} for r in rows
            if r['state'] == 'active' and r['last'] and r['last']['conclusion'] == 'failure']
    for r in reds: redboard.append({'repo': repo, **r})
    census[repo] = {'total': len(rows), 'active': a, 'disabled': d, 'moneyLanes': m, 'workflows': rows}

from datetime import datetime, timezone
doc = {'capturedAt': datetime.now(timezone.utc).isoformat(),
       'totals': {'repos': len(repos), 'workflows': tot_a + tot_d, 'active': tot_a,
                  'disabled': tot_d, 'moneyLanes': tot_m, 'activeRed': len(redboard)},
       'redboard': redboard, 'repos': census}
os.makedirs(os.path.dirname(OUT) or '.', exist_ok=True)
with open(OUT, 'w') as f:
    json.dump(doc, f, indent=1)
print(json.dumps(doc['totals']))
print('REDBOARD:', json.dumps(redboard)[:400])
