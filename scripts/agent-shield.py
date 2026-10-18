#!/usr/bin/env python3
# agent-shield — the injection-shape scanner for OUR agent-facing files.
# (original SAOS engineering, owner-approved 2026-10-18 «מאשר תמשיך ודחוף»,
#  IM zai-web session web-16cb7ad8)
#
# Lineage: STUDY-002 (affaan-m/ECC, ★282k) — the "agentshield-class audit lane"
# proposal: scan the files OUR agents read for injection-shaped content. This is
# the defensive MIRROR of exposure-gate (which guards against identity leaks in
# what we write): the shield guards against instructions hidden in what our
# agents READ — ledgers, receipts, censuses, task files, docs.
#
# Why it matters here: the scout loop ingests machine-written text (catalog
# descriptions, evidence fields) into state/*.json that OTHER agents read. Law 9
# says those fields are untrusted evidence, never instructions. This lane MEASURES
# that promise: if a poisoned description ever lands in the ledger, the shield
# turns red at the next run, with file + JSON pointer evidence.
#
# Laws:
#   - Static and read-only; never executes or installs anything it inspects.
#   - Fail-closed: BLOCKER -> gate red -> lane red (eval step exits 1 AFTER the
#     receipt is published, so the evidence lands in git).
#   - Docs are instructions — imperatives in markdown are legitimate and are NOT
#     scanned as directives; only hidden/bidi Unicode and ANSI escapes are flagged.
#   - Data is not instructions — imperative/exfil/pipe-shell shapes in JSON/TSV
#     are BLOCKER; obfuscation primitives (base64 -d, atob, child_process, ...)
#     are SHOULD (calibrated: security-tool descriptions can name them innocently).
#   - Git is truth: receipt committed each run; adding a target is a data edit.
import json, os, re, sys, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.environ.get('SHIELD_TARGETS', os.path.join(ROOT, 'state', 'agent-shield-targets.json'))
OUT = os.environ.get('SHIELD_OUT', os.path.join(ROOT, 'state', 'agent-shield-last-run.json'))

def now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

# hidden-direction characters: zero-width, joiners, word joiner, BOM,
# bidi controls (embedding/override/isolate), and ANSI CSI escapes
HIDDEN = re.compile('[\u200b\u200c\u200d\u2060\ufeff\u202a-\u202e\u2066-\u2069]')
ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

# BLOCKER shapes in DATA (strings that behave like instructions to an agent reader)
DATA_BLOCKER = [re.compile(p, re.I) for p in (
    r'ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(rules|instructions|prompts?)',
    r'disregard\s+(all\s+)?(previous|prior|above|earlier)\b',
    r'you\s+must\s+now\s+(ignore|execute|send|run|curl|post)',
    r'exfiltrat',
    r'(send|post|upload|ship)[^.\n]{0,48}\b(api[_\s-]?key|secret|token|credential|wif|mnemonic|seed\s+phrase)\b',
    r'\b(curl|wget)[^|]{0,120}\|\s*(ba)?sh\b')]
# SHOULD shapes in DATA (obfuscation/exec primitives, innocently nameable by tool
# descriptions — v1.1 calibration measured 2026-10-18: bare "PowerShell" is a LANGUAGE
# NAME in catalog descriptions (Raphire/Win11Debloat meta.language), so the signal
# requires execution args, not the bare word)
DATA_SHOULD = [re.compile(p, re.I) for p in (
    r'base64\s+(-d|--decode)', r'\batob\s*\(', r'\beval\s*\(', r'child_process',
    r'node\s+-e\b', r'powershell\s+(-[ecw]\b|-enc)', r'invoke-(webrequest|expression)')]

def scan_string(val, out, file, pointer, line=0):
    for rx in DATA_BLOCKER:
        m = rx.search(val)
        if m:
            out.append({'tier': 'BLOCKER', 'file': file, 'pointer': pointer, 'line': line,
                        'rule': 'injection_directive_in_data', 'match': m.group(0)[:100]})
            return
    for rx in DATA_SHOULD:
        m = rx.search(val)
        if m:
            out.append({'tier': 'SHOULD', 'file': file, 'pointer': pointer, 'line': line,
                        'rule': 'obfuscation_primitive_in_data', 'match': m.group(0)[:100]})
            return
    m = HIDDEN.search(val) or ANSI.search(val)
    if m:
        out.append({'tier': 'SHOULD', 'file': file, 'pointer': pointer, 'line': line,
                    'rule': 'hidden_control_chars', 'match': repr(m.group(0))[:40]})

def walk_json(node, out, file, path):
    if isinstance(node, str):
        scan_string(node, out, file, path)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            walk_json(v, out, file, f'{path}[{i}]')
    elif isinstance(node, dict):
        for k, v in node.items():
            walk_json(k, out, file, path + '.<key>')      # keys are strings too
            walk_json(v, out, file, f'{path}.{k[:48]}')

def scan_data(rel, text, out):
    if rel.endswith('.json'):
        try:
            doc = json.loads(text)
        except Exception as e:
            out.append({'tier': 'SHOULD', 'file': rel, 'pointer': '', 'line': 0,
                        'rule': 'json_unreadable', 'match': str(e)[:80]})
            return
        walk_json(doc, out, rel, '$')
    else:  # tsv / csv-ish: line:cell pointers
        for ln, line in enumerate(text.splitlines(), start=1):
            for ci, cell in enumerate(line.split('\t')):
                if cell:
                    scan_string(cell, out, rel, f'line{ln}.cell{ci}', ln)

def scan_doc(rel, text, out):
    for ln, line in enumerate(text.splitlines(), start=1):
        m = HIDDEN.search(line) or ANSI.search(line)
        if m:
            out.append({'tier': 'SHOULD', 'file': rel, 'pointer': f'line{ln}', 'line': ln,
                        'rule': 'hidden_control_chars_in_doc', 'match': repr(m.group(0))[:40]})

def scan():
    if not os.path.exists(REG):
        print(f'agent-shield: registry missing: {REG}'); sys.exit(2)
    reg = json.load(open(REG))
    findings, targets = [], []
    for tgt in reg.get('targets', []):
        before = len(findings)
        rec = {'id': tgt.get('id'), 'degraded': [], 'files': 0}
        for g in tgt.get('globs', {}).get('data', []):
            for p in glob.glob(os.path.join(ROOT, g)):
                rel = os.path.relpath(p, ROOT)
                scan_data(rel, open(p, encoding='utf-8', errors='replace').read(), findings)
                rec['files'] += 1
        for g in tgt.get('globs', {}).get('docs', []):
            for p in glob.glob(os.path.join(ROOT, g), recursive=True):
                if os.path.isdir(p): continue
                rel = os.path.relpath(p, ROOT)
                scan_doc(rel, open(p, encoding='utf-8', errors='replace').read(), findings)
                rec['files'] += 1
        rec['blockers'] = sum(1 for f in findings[before:] if f['tier'] == 'BLOCKER')
        rec['shoulds'] = sum(1 for f in findings[before:] if f['tier'] == 'SHOULD')
        targets.append(rec)
    doc = {'at': now(), 'gate': None,
           'totals': {'blockers': sum(1 for f in findings if f['tier'] == 'BLOCKER'),
                      'shoulds': sum(1 for f in findings if f['tier'] == 'SHOULD'),
                      'files': sum(r.get('files', 0) for r in targets)},
           'targets': targets, 'findings': findings}
    doc['gate'] = 'red' if doc['totals']['blockers'] else ('yellow' if doc['totals']['shoulds'] else 'green')
    tmp = OUT + '.tmp'
    with open(tmp, 'w') as fh: json.dump(doc, fh, indent=1); fh.write('\n')
    os.replace(tmp, OUT)
    print(f"AGENT-SHIELD {doc['gate'].upper()} — files={doc['totals']['files']} "
          f"BLOCKER={doc['totals']['blockers']} SHOULD={doc['totals']['shoulds']}")
    for f in findings[:40]:
        print(f"  [{f['tier']}] {f['rule']} {f['file']}:{f.get('line',0)} {f.get('pointer','')} — {f['match'][:70]}")
    if len(findings) > 40: print(f'  ... +{len(findings)-40} more')
    sys.exit(0)

def eval_gate():
    try:
        doc = json.load(open(OUT))
    except Exception as e:
        print(f'agent-shield eval: receipt unreadable ({e}) — fail-closed red'); sys.exit(1)
    print(f"AGENT-SHIELD EVAL: {doc.get('gate')}")
    for f in doc.get('findings', []):
        if f.get('tier') == 'BLOCKER':
            print(f"  BLOCKER {f['rule']} {f['file']} {f.get('pointer','')} — {f['match'][:70]}")
    sys.exit(1 if doc.get('gate') == 'red' else 0)

def digest():
    try:
        doc = json.load(open(OUT))
    except Exception as e:
        print(f'receipt unreadable: {e}'); return
    print('## agent-shield digest')
    print('```')
    print(f"at: {doc.get('at')}  gate: {doc.get('gate')}")
    print('totals:', json.dumps(doc.get('totals', {})))
    by_rule = {}
    for f in doc.get('findings', []):
        by_rule.setdefault((f['tier'], f['rule']), 0)
        by_rule[(f['tier'], f['rule'])] += 1
    for (tier, rule), n in sorted(by_rule.items()):
        print(f'  [{tier}] {rule}: {n}')
    print('```')

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'scan'
    {'scan': scan, '--eval': eval_gate, '--digest': digest}.get(mode, scan)()
