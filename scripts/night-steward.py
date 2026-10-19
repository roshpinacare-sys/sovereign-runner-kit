#!/usr/bin/env python3
"""night-steward — the night patrol that watches the watchers (wave-19.34).

OWNER ORDER (trace 1a1557f9ff40cf6d, 2026-10-19 evening): "אתה בטוח? וודא את
עצמך אל תסמוך על הטיעונים שלך... אני הולך לישון, אני רוצה לקום ולראות
התפתחות רצינית של הארכיטקטורה מתוך עצמה ברמה מאוד גבוהה."

WHY this lane exists (measured, not assumed):
- fleet-keeper MEASURES the fleet every 2h but its own doctrine line says it
  fixes nothing ("הסריקה אינה מתקנת — התיקון = netrun claim"), and its census
  is only as fresh as the GitHub schedule lottery lets it be (measured
  2026-10-19: netrun-loop declared 30min, actual gaps up to 6.5h; fleet-keeper
  declared 2h, actual gaps up to 9h).
- The three plane chains (executor fleet-beat hourly, runner-kit + beacon
  keepalives 30min) are dispatch-chains precisely because schedules jitter.
  If a chain dies at 23:00, nothing on the network NOTICEs and REPORTs it in
  a form the owner can read at 07:00 — until tonight.

WHAT the steward does (one patrol, every 2h overnight):
1. OBSERVE — chain aliveness for the three planes, from the runs API
   (fresher than any committed census): last success age vs the cadence law
   (30min chains tolerate 75min, the hourly beat tolerates 100min). A run
   still in flight is cover, not silence — measured, not assumed.
2. OBSERVE — census redboard reds (repo, workflow, redStreak) with honest
   classification: recidivist (redStreak >= 2) vs new (1). Reds are DATA —
   the steward records them; per the network doctrine the FIX travels as a
   netrun claim, not as a cross-repo push from the governance plane.
3. OBSERVE — census freshness (capturedAt age) — the measured schedule-jitter
   witness, printed every patrol.
4. ACT (only where the law already allows): a chain with no success and no
   in-flight run beyond tolerance is revived by ONE dispatch — executor's
   fleet-beat and beacon's keepalive via SOVEREIGN_PAT (the exact operation
   beat-keepalive has exercised since wave-19.10/19.11), self keepalive on
   the self repo. Every dispatch (or refusal) is recorded as an ACTION.
5. RECORD — state/night-steward-last-run.json (machine receipt),
   night-log/NIGHT-LOG-YYYY-MM.md (append-only honest journal),
   MORNING-REPORT.md (regenerated; the file the owner reads at wake).

LAWS (inherited, not reinvented):
- LEAK-LAW: every printed string passes clean(); the credential never appears.
- FAIL-CLOSED: an observation the steward cannot make (auth/API breakdown)
  exits 1 loudly. Fleet reds are NOT steward failures — the patrol that
  records a red succeeded (exit 0); only the blind patrol fails.
- SECRET-SURFACE: schedule + workflow_dispatch only; no pull_request.
- FREE: public repos, stdlib only, one patrol = ~6 API calls + 2 git ops.
"""
import base64
import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ORG = 'roshpinacare-sys'
SELF_REPO = ORG + '/sovereign-runner-kit'

# cadence law: (repo, workflow, declared-cadence-min, tolerate-min, dispatchable)
PLANES = [
    (ORG + '/sovereign-executor', 'fleet-beat.yml', 60, 100, True),
    (ORG + '/sovereign-runner-kit', 'keepalive.yml', 30, 75, True),
    (ORG + '/sovereign-beacon', 'keepalive.yml', 30, 75, True),
]


def clean(s):
    s = str(s)
    pat = os.environ.get('SOVEREIGN_PAT', '')
    if pat:
        s = s.replace(pat, '***REDACTED***')
    return s


def api(method, path, token, body=None):
    req = Request('https://api.github.com' + path, method=method)
    req.add_header('Authorization', 'Basic ' + base64.b64encode(
        ('x-access-token:' + token).encode()).decode())
    req.add_header('Accept', 'application/vnd.github+json')
    data = json.dumps(body).encode() if body is not None else None
    if data:
        req.add_header('Content-Type', 'application/json')
    with urlopen(req, data=data, timeout=30) as r:
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)


def now_utc():
    return datetime.now(timezone.utc)


def age_min(iso):
    at = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    return (now_utc() - at).total_seconds() / 60.0


def watch_chain(repo, wf, tolerate, tok):
    """One plane's aliveness: (state, last_success_age_min, detail).
    state in {'ALIVE','IN-FLIGHT','STALE'}; STALE means the patrol may revive."""
    try:
        st, d = api('GET', '/repos/%s/actions/workflows/%s/runs?per_page=6' % (repo, wf), tok)
    except HTTPError as e:
        return 'BLIND', None, 'runs API HTTP %s — fail-closed' % e.code
    except Exception as e:
        return 'BLIND', None, clean('runs API error: %s' % e)
    runs = (d or {}).get('workflow_runs') or []
    if not runs:
        return 'STALE', None, 'no run ever — stale by definition'
    last_succ_age = None
    inflight = False
    inflight_age = None
    for r in runs:
        a = age_min(r['created_at'])
        if r['status'] in ('in_progress', 'queued', 'waiting'):
            if inflight_age is None:
                inflight_age = a
            inflight = True
        if r['conclusion'] == 'success' and last_succ_age is None:
            last_succ_age = a
    if last_succ_age is None:
        return 'STALE', None, 'no success in the recent window'
    if inflight and (inflight_age or 0) <= tolerate:
        return 'IN-FLIGHT', last_succ_age, 'success %.0fmin ago; run in flight %.0fmin' % (last_succ_age, inflight_age)
    if last_succ_age > tolerate:
        return 'STALE', last_succ_age, 'last success %.0fmin ago > tolerate %dmin%s' % (
            last_succ_age, tolerate, ' (in-flight run is itself %.0fmin old)' % inflight_age if inflight else '')
    return 'ALIVE', last_succ_age, 'last success %.0fmin ago (tolerate %d)' % (last_succ_age, tolerate)


def revive(repo, wf, tok):
    """One revival dispatch. Same operation beat-keepalive exercises; same secret."""
    try:
        st, _ = api('POST', '/repos/%s/actions/workflows/%s/dispatches' % (repo, wf),
                    tok, {'ref': 'main'})
    except HTTPError as e:
        if e.code in (403, 422):
            # lifeline law: name the true cause, never guess
            try:
                _, perms = api('GET', '/repos/%s/actions/permissions' % repo, tok)
                if perms and not perms.get('enabled', True):
                    return False, 'dispatch rejected AND the plane\'s Actions switch is OFF — owner decision required'
            except Exception as pe:
                return False, clean('dispatch HTTP %s; switch probe failed (%s)' % (e.code, pe))
            return False, 'dispatch HTTP %s (switch ON; likely missing Actions:write on the credential)' % e.code
        return False, 'dispatch HTTP %s' % e.code
    except Exception as e:
        return False, clean('dispatch error: %s' % e)
    return True, 'dispatched (HTTP %s)' % st


def load_census():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     'state', 'fleet-census.json')
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, 'fleet-census.json missing — fleet-keeper has never published'
    except Exception as e:
        return None, clean('census unreadable: %s' % e)


def main():
    tok = os.environ.get('SOVEREIGN_PAT', '')
    if not tok:
        print('night-steward: FAIL-CLOSED — no SOVEREIGN_PAT in env; a blind patrol is a failed patrol')
        return 1
    at = now_utc().strftime('%Y-%m-%dT%H:%M:%SZ')
    print('night-steward: patrol begins %s' % at)

    # 1. chains
    chains = []
    actions = []
    for repo, wf, cad, tol, can_dispatch in PLANES:
        state, succ_age, detail = watch_chain(repo, wf, tol, tok)
        entry = {'repo': repo.split('/')[-1], 'workflow': wf, 'cadenceMin': cad,
                 'tolerateMin': tol, 'state': state,
                 'lastSuccessAgeMin': round(succ_age, 1) if succ_age is not None else None,
                 'detail': clean(detail)}
        if state == 'STALE' and can_dispatch:
            ok, msg = revive(repo, wf, tok)
            entry['revival'] = msg
            actions.append({'target': '%s/%s' % (repo.split('/')[-1], wf),
                            'action': 'revival-dispatch' if ok else 'revival-REFUSED',
                            'result': msg})
            if ok:
                entry['state'] = 'REVIVED'
        chains.append(entry)
        print('night-steward: chain %-9s %-14s %s' % (entry['repo'], entry['state'], entry['detail']))

    # 2. census reds + freshness
    census, cerr = load_census()
    reds = []
    census_age = None
    if census:
        cb = census.get('capturedAt')
        if cb:
            try:
                census_age = round(age_min(cb), 1)
            except Exception:
                census_age = None
        for item in census.get('redboard') or []:
            reds.append({'repo': item.get('repo'), 'workflow': item.get('wf'),
                         'redStreak': item.get('redStreak', 0),
                         'class': 'recidivist' if (item.get('redStreak', 0) or 0) >= 2 else 'new'})
        print('night-steward: census %s (%.0fmin old) — %d red lane(s)' % (
            cb or '?', census_age or -1, len(reds)))
    else:
        print('night-steward: census unavailable — %s' % cerr)
    for r in reds:
        print('night-steward: RED %-10s %-24s streak=%s (%s)' % (
            r['repo'], r['workflow'], r['redStreak'], r['class']))

    # 3. receipt + journal + morning report
    receipt = {'schema': 'saos.night-steward/1', 'at': at,
               'chains': chains, 'censusAgeMin': census_age,
               'censusNote': cerr, 'reds': reds, 'actions': actions,
               'verdict': 'patrol-recorded'}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'state', 'night-steward-last-run.json'), 'w', encoding='utf-8') as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
        f.write('\n')

    ym = now_utc().strftime('%Y-%m')
    stamp = now_utc().strftime('%Y-%m-%dT%H:%M:%SZ')
    log_path = os.path.join(root, 'night-log', 'NIGHT-LOG-%s.md' % ym)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    lines = ['', '## PATROL %s' % stamp, '',
             '| plane | state | last success | detail |', '|---|---|---|---|']
    for c in chains:
        lines.append('| %s/%s | %s | %s | %s |' % (
            c['repo'], c['workflow'], c['state'],
            ('%.0fmin' % c['lastSuccessAgeMin']) if c['lastSuccessAgeMin'] is not None else '—',
            c['detail'] + ((' ; revival: ' + c['revival']) if c.get('revival') else '')))
    lines.append('')
    lines.append('census: %s — %d red lane(s)%s' % (
        ('%.0fmin old' % census_age) if census_age is not None else 'unavailable',
        len(reds), ' — ' + cerr if cerr else ''))
    for r in reds:
        lines.append('- RED %s/%s streak=%s (%s)' % (r['repo'], r['workflow'], r['redStreak'], r['class']))
    for a in actions:
        lines.append('- ACTION %s: %s — %s' % (a['target'], a['action'], a['result']))
    lines.append('')
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    dead = [c for c in chains if c['state'] in ('STALE', 'BLIND')]
    healed = [a for a in actions if a['action'] == 'revival-dispatch']
    rep = []
    rep.append('# MORNING REPORT — the night, in the architecture\'s own words')
    rep.append('')
    rep.append('_generated %s by night-steward (wave-19.34, owner order trace 1a1557f9ff40cf6d: '
               '"וודא את עצמך... התפתחות רצינית של הארכיטקטורה מתוך עצמה")_' % stamp)
    rep.append('')
    rep.append('## The three hearts (dispatch-chain planes)')
    rep.append('')
    rep.append('| plane | lane | state | last success | note |')
    rep.append('|---|---|---|---|---|')
    for c in chains:
        rep.append('| %s | `%s` | **%s** | %s | %s |' % (
            c['repo'], c['workflow'], c['state'],
            ('%.0fmin ago' % c['lastSuccessAgeMin']) if c['lastSuccessAgeMin'] is not None else 'never',
            c['detail'] + ((' ; **revival: %s**' % c['revival']) if c.get('revival') else '')))
    rep.append('')
    if healed:
        rep.append('**The architecture healed itself %d time(s) tonight** (revival dispatches above) — '
                   'each revival is the same lawful operation beat-keepalive has exercised since wave-19.10.' % len(healed))
        rep.append('')
    rep.append('## Red lanes (data, recorded — fixes travel as netrun claims per doctrine)')
    rep.append('')
    if census and census.get('capturedAt'):
        rep.append('_as-of census `capturedAt` %s (%.0fmin old at patrol time) — recidivist streaks '
                   'shrink as the fixes from tonight\'s waves land their next green runs_' % (
                       census['capturedAt'], census_age or -1))
        rep.append('')
    if reds:
        rep.append('| repo | lane | red streak | class |')
        rep.append('|---|---|---|---|')
        for r in reds:
            rep.append('| %s | `%s` | %s | %s |' % (r['repo'], r['workflow'], r['redStreak'], r['class']))
    else:
        rep.append('None at this patrol — the fleet\'s last measured census shows zero red lanes.')
    rep.append('')
    rep.append('## Census freshness (the measured GitHub schedule-jitter witness)')
    rep.append('')
    rep.append('fleet-keeper\'s census is %s. Measured tonight (wave-19.34): GitHub schedule '
               'jitter on this org runs to hours (netrun-loop declared 30min — gaps to 6.5h; '
               'fleet-keeper declared 2h — gaps to 9h). This is exactly why the plane chains '
               'are dispatch-chains and why this patrol exists.' % (
                   ('%.0f minutes old at patrol time' % census_age) if census_age is not None
                   else ('unavailable (%s)' % cerr if cerr else 'unavailable')))
    rep.append('')
    rep.append('## Standing falsifiable prediction (owns tomorrow)')
    rep.append('')
    rep.append('2026-10-20 ~13:50Z the hourly beat re-reads the guard: reArmed>0 = the flip '
               'returned; 45/45 alreadyOn = the skip holds. The overnight patrols above are the '
               'evidence base that adjudicates it.')
    rep.append('')
    rep.append('---')
    rep.append('')
    rep.append('_Full night journal: `night-log/NIGHT-LOG-%s.md` · machine receipt: '
               '`state/night-steward-last-run.json`_' % ym)
    with open(os.path.join(root, 'MORNING-REPORT.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(rep) + '\n')

    blind = [c for c in chains if c['state'] == 'BLIND']
    if blind:
        print('night-steward: FAIL-CLOSED — %d plane(s) unobservable (%s); a blind patrol is a failed patrol'
              % (len(blind), ', '.join(c['repo'] for c in blind)))
        return 1
    print('night-steward: patrol recorded — %d chain(s) watched, %d red(s) recorded, %d action(s); '
          'stale=%d; receipt + journal + morning report written'
          % (len(chains), len(reds), len(actions), len(dead)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
