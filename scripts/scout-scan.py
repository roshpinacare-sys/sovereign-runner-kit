#!/usr/bin/env python3
# scout-scan — the sovereign forage loop: discover -> enrich -> vet (fail-closed) -> ledger.
#
# Laws (docs/SCOUT-PROTOCOL.md):
#   1. NEVER execute external code — vetting is static, read-only, API reads only.
#   2. NEVER vendor external code verbatim — integration is original reimplementation.
#   3. Every verdict carries evidence (why). REJECT quarantines; it never integrates.
#   4. Git is truth — the ledger is committed every run; route outcomes recorded honestly.
#
# Source types (state/scout-sources.json):
#   github_user_repos — enumerate a curator's account (no CF, always available)
#   mcp_catalog       — MCP JSON-RPC tools/call against a catalog endpoint (route ladder:
#                       direct -> wayback snapshot of the human page -> honest cf_blocked)
#   web_page          — fetch a page, extract github.com/owner/repo (direct -> wayback)
#
# Exit: 0 = at least one source produced data; 1 = every source failed (CI red, honest);
#       2 = config/registry error. A scan records truth; it never "fixes" anything.
import json, re, os, sys, time, random, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES = os.environ.get('SCOUT_SOURCES', os.path.join(ROOT, 'state', 'scout-sources.json'))
OUT = os.environ.get('SCOUT_OUT', os.path.join(ROOT, 'state', 'scout-findings.json'))
RUNOUT = os.environ.get('SCOUT_RUN_OUT', os.path.join(ROOT, 'state', 'scout-last-run.json'))
SCAN_BUDGET = int(os.environ.get('SCOUT_BUDGET', '80'))   # repos enriched+vetted per run (new first)
MCP_BUDGET = int(os.environ.get('SCOUT_MCP_BUDGET', '24'))
UA = {'User-Agent': 'saos-scout/1.0 (read-only static vetting; never executes external code)'}

def now(): return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def token():
    for k in ('FLEET_TOKEN', 'GITHUB_TOKEN', 'SCOUT_TOKEN'):
        v = os.environ.get(k)
        if v: return v.strip()
    try:
        return open('/home/z/my-project/upload/pat.env').read().strip()
    except Exception:
        return None

TOKEN = token()
GH_HEADERS = dict(UA)
if TOKEN: GH_HEADERS['Authorization'] = f'Bearer {TOKEN}'

def http(url, method='GET', headers=None, data=None, timeout=25):
    h = dict(UA); h.update(headers or {})
    req = urllib.request.Request(url, method=method, headers=h,
                                 data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        return r.status, dict(r.headers), body

def gh(url):
    st, _, body = http(url, headers=GH_HEADERS)
    if st == 404: return None
    if st != 200: raise RuntimeError(f'gh {st} {url}')
    return json.loads(body)

# ---------------------------------------------------------------- extraction
REPO_RX = re.compile(r'github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)')
REPO_SHORTHAND = re.compile(r'^([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)$')
NON_REPO = {'topics', 'features', 'explore', 'settings', 'security', 'orgs', 'apps',
            'marketplace', 'sponsors', 'collections', 'trending', 'about', 'pricing',
            'customer-stories', 'readme', 'site', 'new', 'codespaces', 'notifications'}

def norm_repo(tok):
    """github.com/owner/name | owner/name -> owner/name, or None."""
    t = (tok or '').strip()
    m = REPO_RX.search(t)
    if m:
        return f'{m.group(1)}/{m.group(2)}'
    m = REPO_SHORTHAND.match(t)
    if m and m.group(1).lower() not in NON_REPO:
        return f'{m.group(1)}/{m.group(2)}'
    return None

def extract_repos(text):
    out = []
    for m in REPO_RX.finditer(text or ''):
        owner, name = m.group(1), m.group(2)
        name = re.split(r'(\.git|[/#?])', name)[0]
        if not owner or not name or owner.lower() in NON_REPO or name.lower() in NON_REPO: continue
        if name in ('.github',): continue
        out.append(f'{owner}/{name}')
    return sorted(set(out))

# ---------------------------------------------------------------- route ladder
def wayback_snapshot(url):
    try:
        st, _, body = http('https://archive.org/wayback/available?url=' + urllib.parse.quote(url, safe=''), timeout=20)
        if st != 200: return None
        j = json.loads(body)
        snap = (j.get('archived_snapshots') or {}).get('closest') or {}
        return snap.get('url') if snap.get('available') else None
    except Exception:
        return None

def fetch_text(url):
    """Route ladder for HTML/data pages. Returns (text, route) or (None, failure_route)."""
    try:
        st, hd, body = http(url, timeout=25)
        txt = body.decode('utf-8', 'replace')
        if st == 200 and 'Just a moment...' not in txt[:400]:
            return txt, 'direct'
        route = 'cf_blocked'
    except urllib.error.HTTPError as e:
        route = f'http_{e.code}'
    except Exception as e:
        route = f'error_{type(e).__name__}'
    snap = wayback_snapshot(url)
    if snap:
        try:
            st, _, body = http(snap, timeout=30)
            if st == 200: return body.decode('utf-8', 'replace'), 'wayback'
        except Exception:
            pass
    return None, route

# ---------------------------------------------------------------- MCP route
def mcp_call(endpoint, name, arguments, session, rid):
    payload = {'jsonrpc': '2.0', 'id': rid, 'method': 'tools/call',
               'params': {'name': name, 'arguments': arguments}}
    hdrs = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
    if session: hdrs['Mcp-Session-Id'] = session
    st, hd, body = http(endpoint, method='POST', headers=hdrs, data=payload, timeout=30)
    txt = body.decode('utf-8', 'replace')
    if st != 200 or 'Just a moment...' in txt[:400]:
        raise RuntimeError(f'mcp_http_{st or "cf"}')
    # streamable responses may be SSE-framed; take the first data: line with JSON
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith('data:'):
            txt = line[5:].strip(); break
    j = json.loads(txt)
    if 'error' in j: raise RuntimeError('mcp_error: ' + json.dumps(j['error'])[:120])
    res = j.get('result') or {}
    sc = res.get('structuredContent')
    if sc: return sc
    for c in res.get('content', []):
        if c.get('type') == 'text':
            try: return json.loads(c['text'])
            except Exception: return {'text': c['text']}
    return {}

def mcp_enumerate(src, run):
    """MCP handshake + rotating-grid tools/call sweep (politeness: a slice per day, the
    full grid covered over runs; budget = SCOUT_MCP_BUDGET). Returns (repos, route)."""
    ep = src['endpoint']
    try:
        st, hd, body = http(ep, method='POST', timeout=30,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'},
            data={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                  'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                             'clientInfo': {'name': 'saos-scout', 'version': '1.0.0'}}})
        txt = body.decode('utf-8', 'replace')
        if st != 200 or 'Just a moment...' in txt[:400]:
            raise RuntimeError(f'mcp_http_{st or "cf"}')
        session = hd.get('Mcp-Session-Id') or hd.get('mcp-session-id')
    except Exception as e:
        route = str(e).replace(' ', '_')[:40]
        txt, wb = fetch_text(src.get('human_page', ''))
        if txt:
            urls = extract_repos(txt)
            if urls: return urls, 'wayback_page'
        return [], route
    # rotating grid: words x categories, deterministic per-day slice (citizen cadence)
    words = src.get('words', ['ai', 'api', 'web', 'data'])
    cats = src.get('categories', [None]) or [None]
    combos = [(w, c) for w in words for c in cats]
    random.Random(date.today().strftime('%Y%j') + src.get('id', '')).shuffle(combos)
    budget = min(MCP_BUDGET, len(combos))
    urls, calls, empty = set(), 0, 0
    tool = src['tool']
    filters = src.get('filters', {})
    for w, c in combos[:budget]:
        args = {'query': w, 'limit': src.get('limit', 50)}
        if c: args['category'] = c
        args.update(filters)
        try:
            sc = mcp_call(ep, tool, args, session, 100 + calls)
            calls += 1
            got = 0
            # structured repos first (owner/name shorthand), then whole-blob github URLs
            for r in (sc.get('repos') or []) + (sc.get('apis') or []):
                tok = r.get('repo') or r.get('url') or ''
                n = norm_repo(tok)
                if n: urls.add(n); got += 1
            for u in extract_repos(json.dumps(sc)):
                urls.add(u); got += 1
            if not got: empty += 1
        except Exception:
            calls += 1; empty += 1
        time.sleep(0.4)
    run['mcp_calls'] = run.get('mcp_calls', 0) + calls
    run.setdefault('mcp_empty_calls', 0)
    run['mcp_empty_calls'] += empty
    if urls: return sorted(urls), 'mcp'
    return [], 'mcp_empty'

# ---------------------------------------------------------------- vetting (static, fail-closed)
INSTALL_KEYS = ('preinstall', 'postinstall', 'prepare')
HARD_RX = [re.compile(p, re.I) for p in (
    r'\bcurl\b', r'\bwget\b', r'base64\s+(-d|--decode)', r'atob\s*\(', r'node\s+-e\b',
    r'\beval\s*\(', r'child_process', r'\|\s*sh\b', r'\|\s*bash\b', r'powershell',
    r'invoke-(webrequest|expression)', r'\bnc\s+-e\b', r'webhook\.site', r'\bdnslog\.')]
WF_HARD_RX = [re.compile(p, re.I) for p in (r'curl[^|]{0,120}\|\s*(ba)?sh', r'wget[^|]{0,120}\|\s*(ba)?sh')]
WF_CAUTION_RX = re.compile(r'pull_request_target', re.I)

def vet_repo(full):
    """Static vetting. Returns finding dict. Read-only: meta + tree + at most 4 file fetches."""
    ev, reasons, hard, caution = {}, [], [], []
    meta = gh(f'https://api.github.com/repos/{full}')
    if not meta:
        return {'repo': full, 'verdict': 'GONE', 'reasons': ['repo_not_found_404'], 'evidence': {}}
    m = {'stars': meta.get('stargazers_count', 0), 'forks': meta.get('forks_count', 0),
         'license': (meta.get('license') or {}).get('spdx_id'), 'archived': meta.get('archived', False),
         'language': meta.get('language'), 'created': (meta.get('created_at') or '')[:10],
         'pushed': (meta.get('pushed_at') or '')[:10], 'owner_type': (meta.get('owner') or {}).get('type'),
         'description': (meta.get('description') or '')[:160]}
    push_days = 9999
    created_days = 9999
    try:
        from datetime import datetime as dt
        nowdt = dt.now(timezone.utc).replace(tzinfo=None)
        push_days = (nowdt - dt.strptime(m['pushed'], '%Y-%m-%d')).days
        created_days = (nowdt - dt.strptime(m['created'], '%Y-%m-%d')).days
    except Exception:
        pass
    if not m['license'] or m['license'] in ('NOASSERTION', 'Other'):
        caution.append('no_spdx_license')
    if m['archived']: caution.append('archived')
    if push_days > 730: caution.append('stale_push_gt_2y')
    if m['stars'] == 0 and created_days < 14: caution.append('unproven_new_0star')
    tree = None
    try:
        if m['pushed'] and meta.get('default_branch'):
            tree = gh(f"https://api.github.com/repos/{full}/git/trees/{meta['default_branch']}?recursive=1")
    except Exception:
        pass
    paths = []
    if tree and not tree.get('truncated'):
        paths = [t['path'] for t in tree.get('tree', []) if t.get('type') == 'blob']
    elif tree and tree.get('truncated'):
        caution.append('tree_truncated_deep_vet_skipped')
    # package.json install scripts — the classic supply-chain exfil gate
    if 'package.json' in paths:
        try:
            st, _, body = http(f'https://raw.githubusercontent.com/{full}/{meta["default_branch"]}/package.json', timeout=20)
            if st == 200:
                pj = json.loads(body.decode('utf-8', 'replace'))
                scripts = pj.get('scripts') or {}
                flagged = {k: v[:200] for k, v in scripts.items()
                           if k in INSTALL_KEYS and any(rx.search(v or '') for rx in HARD_RX)}
                ev['install_scripts'] = flagged
                if flagged:
                    hard.append('install_script_network_exec')
                    for k, v in flagged.items(): reasons.append(f'install:{k}')
        except Exception:
            caution.append('package_json_unreadable')
    # workflows — CI files execute on the MAINTAINER's runner, never on consumers;
    # our posture: flag for human eyes (CAUTION), do not quarantine (v1.1 calibration:
    # curl|sh is industry-standard build bootstrap, e.g. sh.rustup.rs — evidence stays).
    wf_paths = [p for p in paths if p.startswith('.github/workflows/') and p.endswith(('.yml', '.yaml'))][:3]
    flagged_wf = []
    for p in wf_paths:
        try:
            st, _, body = http(f'https://raw.githubusercontent.com/{full}/{meta["default_branch"]}/{p}', timeout=20)
            if st != 200: continue
            txt = body.decode('utf-8', 'replace')
            if any(rx.search(txt) for rx in WF_HARD_RX):
                flagged_wf.append(p); caution.append('workflow_curl_pipe_sh')
            elif WF_CAUTION_RX.search(txt):
                flagged_wf.append(p); caution.append('workflow_pull_request_target')
        except Exception:
            pass
    if flagged_wf: ev['workflows_flagged'] = flagged_wf
    verdict = 'REJECT' if hard else ('CAUTION' if caution else 'STUDY')
    reasons = hard + caution if verdict == 'REJECT' else (caution if verdict == 'CAUTION' else ['baseline_static_vet_clean'])
    return {'repo': full, 'verdict': verdict, 'reasons': reasons, 'evidence': ev, 'meta': m}

# ---------------------------------------------------------------- ledger
SEV = {'REJECT': 0, 'CAUTION': 1, 'STUDY': 2, 'GONE': 3}

def merge(ledger, found, source_id):
    """Returns (is_new, verdict_changed)."""
    key = found['repo']
    f = ledger['findings'].get(key)
    stamp = now()
    is_new = f is None
    if not f:
        f = {'repo': key, 'first_seen': stamp, 'sources': [], 'history': []}
        ledger['findings'][key] = f
    if source_id not in f['sources']: f['sources'].append(source_id)
    prev = f.get('verdict')
    f.update({'last_seen': stamp, 'verdict': found['verdict'],
              'reasons': found['reasons'], 'evidence': found.get('evidence', {})})
    if found.get('meta'): f['meta'] = found['meta']
    if prev != found['verdict']:
        f['history'].append({'at': stamp, 'was': prev, 'now': found['verdict'], 'reasons': found['reasons']})
    return is_new, (prev is not None and prev != found['verdict'])

def _flush(out_path, run_path, ledger, run):
    tmp = out_path + '.tmp'
    with open(tmp, 'w') as fh: json.dump(ledger, fh, indent=1); fh.write('\n')
    os.replace(tmp, out_path)
    tmp = run_path + '.tmp'
    with open(tmp, 'w') as fh: json.dump(run, fh, indent=1); fh.write('\n')
    os.replace(tmp, run_path)

def main():
    if not os.path.exists(SOURCES):
        print(f'scout: registry missing: {SOURCES}'); sys.exit(2)
    reg = json.load(open(SOURCES))
    ledger = {'updated': None, 'counts': {}, 'findings': {}}
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT))
            ledger['findings'] = old.get('findings', {})
        except Exception:
            pass
    run = {'at': now(), 'sources': [], 'new': 0, 'changed': 0, 'seen': 0, 'vetted': 0,
           'mcp_calls': 0, 'budget': SCAN_BUDGET}
    queue = {}   # full -> [source_ids]
    for src in reg.get('sources', []):
        if not src.get('enabled', True): continue
        sid, typ = src.get('id'), src.get('type')
        rec = {'id': sid, 'type': typ, 'discovered': 0, 'route': None}
        try:
            if typ == 'github_user_repos':
                data = gh(f"https://api.github.com/users/{src['user']}/repos?per_page=100") or []
                rec['route'] = 'api'
                for r in data:
                    queue.setdefault(r['full_name'], []).append(sid)
            elif typ == 'mcp_catalog':
                urls, route = mcp_enumerate(src, run)
                rec['route'] = route
                for u in urls: queue.setdefault(u, []).append(sid)
            elif typ == 'web_page':
                txt, route = fetch_text(src['url'])
                rec['route'] = route
                for u in extract_repos(txt or ''): queue.setdefault(u, []).append(sid)
            else:
                rec['route'] = 'unknown_type'
        except Exception as e:
            rec['route'] = f'error_{type(e).__name__}'
            rec['error'] = str(e)[:160]
        rec['discovered'] = sum(1 for v in queue.values() if sid in v)
        run['sources'].append(rec)
    # the ledger joins the queue — re-vetting survives budget-cut discovery days
    # (verdict updates, e.g. calibrations, propagate on the next run that reaches them)
    for full, f in ledger['findings'].items():
        queue.setdefault(full, (f.get('sources') or ['ledger'])[:1])
    # enrichment priority: findings with no verdict yet, then everything else (stable)
    ranked = sorted(queue.keys(), key=lambda k: (ledger['findings'].get(k, {}).get('verdict') is not None, k))
    for full in ranked[:SCAN_BUDGET]:
        try:
            found = vet_repo(full)
        except Exception as e:
            run['sources'].append({'id': 'vet_error', 'route': str(type(e).__name__), 'repo': full})
            continue
        run['vetted'] += 1
        if found['verdict'] == 'GONE':
            run['gone'] = run.get('gone', 0) + 1
            f = ledger['findings'].get(full)
            if f:
                f['last_seen'] = now(); f['verdict'] = 'GONE'; f['reasons'] = found['reasons']
            continue
        is_new, changed = merge(ledger, found, (queue.get(full) or ['?'])[0])
        run['seen'] += 1
        if is_new: run['new'] += 1
        if changed: run['changed'] += 1
        if run['vetted'] % 25 == 0:  # incremental flush — a killed run keeps its work
            _flush(OUT, RUNOUT, ledger, run)
    # counts + publish
    ledger['updated'] = now()
    ledger['counts'] = {}
    for f in ledger['findings'].values():
        ledger['counts'][f.get('verdict', '?')] = ledger['counts'].get(f.get('verdict', '?'), 0) + 1
    ledger['findings'] = dict(sorted(ledger['findings'].items(), key=lambda kv: (SEV.get(kv[1].get('verdict'), 9), kv[0])))
    for path, obj in ((OUT, ledger), (RUNOUT, run)):
        tmp = path + '.tmp'
        with open(tmp, 'w') as fh: json.dump(obj, fh, indent=1, sort_keys=False); fh.write('\n')
        os.replace(tmp, path)
    # digest
    print(f"SCOUT DIGEST {run['at']}")
    for s in run['sources']:
        print(f"  source {s.get('id')}: route={s.get('route')} discovered={s.get('discovered')}")
    print(f"  vetted={run['vetted']} ledger={len(ledger['findings'])} counts={json.dumps(ledger['counts'])}")
    rej = [f['repo'] for f in ledger['findings'].values() if f.get('verdict') == 'REJECT']
    ctn = [f['repo'] for f in ledger['findings'].values() if f.get('verdict') == 'CAUTION']
    if rej: print(f"  REJECT (quarantined): {', '.join(rej)}")
    if ctn: print(f"  CAUTION: {', '.join(ctn[:12])}{' ...' if len(ctn) > 12 else ''}")
    produced = any(s.get('discovered', 0) > 0 for s in run['sources'])
    sys.exit(0 if produced else 1)

if __name__ == '__main__':
    main()
