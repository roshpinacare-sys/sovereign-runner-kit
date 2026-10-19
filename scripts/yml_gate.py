#!/usr/bin/env python3
"""yml_gate — parse every .github/workflows/*.yml before pushing (wave-19.14).

The wave-19.11 lesson generalized into a fleet tool: keepalive runs #6 AND #7
died with ZERO jobs because an UNQUOTED COLON-SPACE inside a step name
('dwell-chain: check') is a YAML 'mapping values are not allowed here'
rejection — GitHub refuses the whole file, drops every trigger (a later
dispatch even reports 'no workflow_dispatch trigger'), yet git accepts the
push without a whisper. A workflow file is code too: this gate parses every
workflow yml with a real parser and exits 1 on the first failure, naming the
file and the parser's error — so the death happens LOCALLY, before the push,
not as a zero-jobs CI corpse.

Laws:
- fail-closed: a missing parser (pyyaml) is a RED, not a silent pass.
- zero-network: pure local file reads — no credentials, no API, no PAT.
- scope: the repo this runs in (default: <cwd>/.github/workflows), or any
  repo root passed as argv[1] — the same gate covers every fleet repo.
- honest output: one line per file (PASS/FAIL), then a total line.
"""
import glob
import os
import sys

try:
    import yaml
except ImportError:
    print('yml_gate: FAIL-CLOSED — pyyaml missing; refusing to pass blind')
    sys.exit(1)


def gate(root):
    wf_dir = os.path.join(root, '.github', 'workflows')
    files = sorted(glob.glob(os.path.join(wf_dir, '*.yml'))
                   + glob.glob(os.path.join(wf_dir, '*.yaml')))
    if not files:
        print('yml_gate: FAIL-CLOSED — no workflow files under %s; refusing to pass blind' % wf_dir)
        return 1
    bad = 0
    for f in files:
        rel = os.path.relpath(f, root)
        try:
            yaml.safe_load(open(f, encoding='utf-8'))
            print('yml_gate: PASS %s' % rel)
        except Exception as e:
            bad += 1
            first = str(e).split('\n')[0]
            print('yml_gate: FAIL %s -> %s' % (rel, first))
    print('yml_gate: %d files, %d failed' % (len(files), bad))
    return 1 if bad else 0


if __name__ == '__main__':
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    sys.exit(gate(root))
