#!/usr/bin/env python3
# scout-digest — human/step-summary digest of the scout state (reads, never scans).
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load(name):
    p = os.path.join(ROOT, 'state', name)
    try:
        return json.load(open(p))
    except Exception as e:
        return {'_error': str(e)}

run = load('scout-last-run.json')
ledger = load('scout-findings.json')

print('## scout-loop digest')
print('```')
print('run:', run.get('at'))
for s in run.get('sources', []):
    print(f"  {s.get('id')}: route={s.get('route')} discovered={s.get('discovered')}")
for k in ('vetted', 'new', 'changed', 'gone', 'mcp_calls'):
    if run.get(k) is not None:
        print(f'  {k}={run[k]}')
finds = ledger.get('findings', {})
print('ledger:', len(finds), 'counts:', json.dumps(ledger.get('counts', {})))
for v in ('REJECT', 'CAUTION'):
    names = [r for r, f in finds.items() if f.get('verdict') == v]
    if names:
        print(f'  {v}: ' + ', '.join(sorted(names)[:12]) + (' ...' if len(names) > 12 else ''))
recent = []
for f in finds.values():
    for h in f.get('history', []):
        recent.append((h.get('at', ''), f['repo'], h.get('was'), h.get('now')))
for at, repo, was, now in sorted(recent)[-8:]:
    print(f'  transition {at}: {repo} {was} -> {now}')
print('```')
