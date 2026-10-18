#!/usr/bin/env python3
# deploy-gate — the fleet pre-publish gate (original SAOS engineering, owner-approved).
#
# Lineage: STUDY-001 (PinoyFreeCoder/deployment-checklist) proposed the tier-grammar
# audit lane; owner approved 2026-10-18 («מאשר תמשיך ודחוף», IM zai-web session
# web-16cb7ad8). This is OUR design: BLOCKER/SHOULD/NICE as gate red/yellow/green,
# every finding carrying file:line evidence (docs/SCOUT-PROTOCOL.md — Lanes).
#
# Laws:
#   - Static and read-only. This script never executes, installs, or builds anything
#     it inspects — ours or anyone's (SCOUT law 1 applies to the whole fleet).
#   - Fail-closed: any BLOCKER -> gate red -> lane red (eval step exits 1 AFTER the
#     receipt is published, so the evidence lands in git).
#   - Git is truth: the receipt (state/deploy-gate-last-run.json) is committed each run.
#   - Adding a target is a data edit (state/deploy-gate-targets.json), never a code edit.
#
# What it audits:
#   local_tree — this checkout: package.json + .github/workflows/*.yml
#   org_repos  — every public org repo via API: root package.json + workflow files
#
# Signal classes:
#   BLOCKER (red):   install-script network/exec primitives (consumer-side kill chain);
#                    untrusted event data interpolated into run:/script: bodies;
#                    pull_request_target + PR-head checkout (+ secrets in that shape)
#   SHOULD (yellow): workflow remote-shell (maintainer-runner, v1.1 calibration);
#                    third-party actions not pinned to a full 40-hex SHA
#   NICE (green):    advisory counts only
import json, os, re, sys, glob, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.environ.get('GATE_TARGETS', os.path.join(ROOT, 'state', 'deploy-gate-targets.json'))
OUT = os.environ.get('GATE_OUT', os.path.join(ROOT, 'state', 'deploy-gate-last-run.json'))
UA = {'User-Agent': 'saos-deploy-gate/1.0 (static read-only audit; never executes what it inspects)'}

def now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def token():
    for k in ('FLEET_TOKEN', 'GITHUB_TOKEN'):
        v = os.environ.get(k)
        if v: return v.strip()
    try:
        return open('/home/z/my-project/upload/pat.env').read().strip()
    except Exception:
        return None

TOKEN = token()
GH = dict(UA)
if TOKEN: GH['Authorization'] = f'Bearer {TOKEN}'

def gh(url):
    req = urllib.request.Request(url, headers=GH)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)

def raw(url):
    req = urllib.request.Request(url, headers=GH)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode('utf-8', 'replace'), r.status

# ---------------------------------------------------------------- signal classes
INSTALL_KEYS = ('preinstall', 'postinstall', 'prepare')
HARD_RX = [re.compile(p, re.I) for p in (
    r'\bcurl\b', r'\bwget\b', r'base64\s+(-d|--decode)', r'\batob\s*\(', r'node\s+-e\b',
    r'\beval\s*\(', r'child_process', r'\|\s*sh\b', r'\|\s*bash\b', r'powershell',
    r'invoke-(webrequest|expression)', r'\bnc\s+-e\b', r'webhook\.site', r'\bdnslog\.')]

RUN_OPEN = re.compile(r'^(\s*)(?:-\s+)?(run|script):\s*(.*)$')
UNTRUSTED = [re.compile(p) for p in (
    r'\$\{\{\s*github\.event\.pull_request\.(title|body|number|head\.(ref|label|sha))\b',
    r'\$\{\{\s*github\.event\.(comment|issue|review|review_comment)\.(title|body|head)\b',
    r'\$\{\{\s*github\.event\.head_commit\.(message|ref)\b',
    r'\$\{\{\s*github\.event\.discussion\.(title|body)\b',
    r'\$\{\{\s*github\.event\.commits\[',
    r'\$\{\{\s*github\.event\.pages\[\d+\]\.page_name\b')]
REMOTE_SHELL = [re.compile(p, re.I) for p in (r'curl[^|]{0,120}\|\s*(ba)?sh', r'wget[^|]{0,120}\|\s*(ba)?sh')]
USES = re.compile(r'^(\s*)(?:-\s+)?uses:\s*(\S+)', re.M)
ALLOWED_ACTORS = ('actions/', 'github/', 'roshpinacare-sys/', 'docker/', 'oven-sh/', 'pnpm/')
SHA_PIN = re.compile(r'@([0-9a-f]{40})$')

def line_of(text, idx):
    return text[:idx].count('\n') + 1 if idx >= 0 else 0

def run_bodies(text):
    """Yield (line_no, body) for every run:/script: scalar (indentation-based, stdlib)."""
    lines = text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        m = RUN_OPEN.match(lines[i])
        if not m:
            i += 1; continue
        indent = len(m.group(1))
        content = (m.group(3) or '').strip()
        is_scalar = not content or content in ('|', '>', '|-', '|+', '>-', '|2')
        body = [] if is_scalar else [content]
        j = i + 1
        while j < n:
            l = lines[j]
            if not l.strip():
                body.append(''); j += 1; continue
            li = len(l) - len(l.lstrip())
            if li > indent:
                body.append(l); j += 1
            else:
                break
        yield i + 1, '\n'.join(body)
        i = j

def audit_workflow(rel, text, out):
    """Append findings for one workflow file. rel = display path."""
    def add(rule, tier, line, match):
        out.append({'rule': rule, 'tier': tier, 'file': rel, 'line': line,
                    'match': re.sub(r'\s+', ' ', match)[:120]})
    for start, body in run_bodies(text):
        for ln, line in enumerate(body.splitlines(), start=start):
            if any(rx.search(line) for rx in UNTRUSTED):
                add('untrusted_event_interpolation', 'BLOCKER', ln, line.strip())
            elif any(rx.search(line) for rx in REMOTE_SHELL):
                add('workflow_remote_shell', 'SHOULD', ln, line.strip())
    for m in USES.finditer(text):
        ref = m.group(2)
        if not SHA_PIN.search(ref) and not any(ref.startswith(a) for a in ALLOWED_ACTORS):
            add('third_party_action_not_sha_pinned', 'SHOULD', line_of(text, m.start()), ref)
    idx = text.find('pull_request_target')
    if idx >= 0:
        head_checkout = ('refs/pull' in text) or ('github.event.pull_request.head' in text)
        if head_checkout:
            add('prt_head_checkout', 'BLOCKER', line_of(text, idx), 'pull_request_target + PR-head checkout')
            sidx = text.find('secrets.')
            if sidx >= 0:
                add('secrets_in_prt_head_checkout', 'BLOCKER', line_of(text, sidx), 'secrets in pull_request_target workflow')
        else:
            add('pull_request_target_present', 'SHOULD', line_of(text, idx), 'pull_request_target')

def audit_manifest(rel, text, out):
    try:
        pj = json.loads(text)
    except Exception:
        out.append({'rule': 'manifest_unreadable', 'tier': 'SHOULD', 'file': rel, 'line': 0, 'match': ''})
        return
    scripts = pj.get('scripts') or {}
    for k in INSTALL_KEYS:
        v = scripts.get(k)
        if v and any(rx.search(v) for rx in HARD_RX):
            out.append({'rule': 'install_script_network_exec', 'tier': 'BLOCKER',
                        'file': rel, 'line': 0, 'match': f'{k}: {v[:120]}'})

# ---------------------------------------------------------------- targets
def scan_local_tree(out, rec):
    n = 0
    pkg = os.path.join(ROOT, 'package.json')
    if os.path.exists(pkg):
        audit_manifest('package.json', open(pkg, encoding='utf-8', errors='replace').read(), out); n += 1
    for p in sorted(glob.glob(os.path.join(ROOT, '.github', 'workflows', '*.y*ml'))):
        audit_workflow(os.path.relpath(p, ROOT), open(p, encoding='utf-8', errors='replace').read(), out); n += 1
    rec['repos'] = 1; rec['files'] = n

def scan_org_repos(org, out, rec):
    try:
        repos = [r['name'] for r in gh(f'https://api.github.com/users/{org}/repos?per_page=100')]
    except Exception as e:
        rec['degraded'].append(f'org_enumeration_{type(e).__name__}')
        return
    rec['repos'] = len(repos); rec['files'] = 0
    for name in repos:
        try:
            meta = gh(f'https://api.github.com/repos/{org}/{name}')
            br = meta.get('default_branch') or 'main'
            tree = gh(f'https://api.github.com/repos/{org}/{name}/git/trees/{br}?recursive=1')
            paths = [t['path'] for t in tree.get('tree', []) if t.get('type') == 'blob']
        except Exception as e:
            rec['degraded'].append(f'{name}:{type(e).__name__}')
            continue
        picks = [p for p in paths if p == 'package.json']
        picks += [p for p in paths if p.startswith('.github/workflows/') and p.endswith(('.yml', '.yaml'))][:8]
        for p in picks:
            try:
                txt, st = raw(f'https://raw.githubusercontent.com/{org}/{name}/{br}/{p}')
            except Exception as e:
                rec['degraded'].append(f'{name}/{p}:{type(e).__name__}')
                continue
            if st != 200: continue
            (audit_manifest if p.endswith('package.json') else audit_workflow)(f'{name}/{p}', txt, out)
            rec['files'] += 1

# ---------------------------------------------------------------- modes
def scan():
    if not os.path.exists(REG):
        print(f'deploy-gate: registry missing: {REG}'); sys.exit(2)
    reg = json.load(open(REG))
    findings, targets = [], []
    for tgt in reg.get('targets', []):
        before = len(findings)
        rec = {'id': tgt.get('id'), 'type': tgt.get('type'), 'degraded': []}
        if tgt['type'] == 'local_tree':
            scan_local_tree(findings, rec)
        elif tgt['type'] == 'org_repos':
            scan_org_repos(tgt['org'], findings, rec)
        else:
            rec['degraded'].append('unknown_type')
        rec['blockers'] = sum(1 for f in findings[before:] if f['tier'] == 'BLOCKER')
        rec['shoulds'] = sum(1 for f in findings[before:] if f['tier'] == 'SHOULD')
        targets.append(rec)
    doc = {'at': now(), 'gate': None,
           'totals': {'blockers': sum(1 for f in findings if f['tier'] == 'BLOCKER'),
                      'shoulds': sum(1 for f in findings if f['tier'] == 'SHOULD'),
                      'files': sum(r.get('files', 0) for r in targets),
                      'repos': sum(r.get('repos', 0) for r in targets)},
           'targets': targets, 'findings': findings}
    doc['gate'] = 'red' if doc['totals']['blockers'] else ('yellow' if doc['totals']['shoulds'] else 'green')
    tmp = OUT + '.tmp'
    with open(tmp, 'w') as fh: json.dump(doc, fh, indent=1); fh.write('\n')
    os.replace(tmp, OUT)
    print(f"DEPLOY-GATE {doc['gate'].upper()} — files={doc['totals']['files']} "
          f"BLOCKER={doc['totals']['blockers']} SHOULD={doc['totals']['shoulds']}")
    for f in findings:
        print(f"  [{f['tier']}] {f['rule']} {f['file']}:{f['line']} — {f['match'][:90]}")
    for r in targets:
        if r['degraded']: print(f"  degraded {r['id']}: {', '.join(r['degraded'][:6])}")
    sys.exit(0)

def eval_gate():
    try:
        doc = json.load(open(OUT))
    except Exception as e:
        print(f'deploy-gate eval: receipt unreadable ({e}) — fail-closed red'); sys.exit(1)
    g = doc.get('gate')
    print(f"DEPLOY-GATE EVAL: {g}")
    for f in doc.get('findings', []):
        if f.get('tier') == 'BLOCKER':
            print(f"  BLOCKER {f['rule']} {f['file']}:{f['line']} — {f['match'][:90]}")
    sys.exit(1 if g == 'red' else 0)

def digest():
    try:
        doc = json.load(open(OUT))
    except Exception as e:
        print(f'receipt unreadable: {e}'); return
    print('## deploy-gate digest')
    print('```')
    print(f"at: {doc.get('at')}  gate: {doc.get('gate')}")
    print('totals:', json.dumps(doc.get('totals', {})))
    by_rule = {}
    for f in doc.get('findings', []):
        by_rule.setdefault((f['tier'], f['rule']), 0)
        by_rule[(f['tier'], f['rule'])] += 1
    for (tier, rule), n in sorted(by_rule.items()):
        print(f'  [{tier}] {rule}: {n}')
    for f in doc.get('findings', [])[:10]:
        print(f"  {f['tier']} {f['rule']} {f['file']}:{f['line']}")
    print('```')

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'scan'
    {'scan': scan, '--eval': eval_gate, '--digest': digest}.get(mode, scan)()
