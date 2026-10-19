#!/usr/bin/env python3
"""fleet-survey — "what are all the agents doing, and where do we stand"
as an executable instrument (wave-19.28).

Owner order, verbatim (trace 1a15516332542d89):
  «תראה מה עוד כל הסוכנים עושים ואיפה אנחנו עומדים ביחס למטרות
   ושהכל פעיל אוטונומית ועוד ושפר ודחוף»
Until this wave the answer required a manual API crawl per wave. This tool
makes the answer one command: a read-only fleet-wide snapshot of what every
lane in every sandbox repo has been doing over the last 24 hours, plus the
head commit each repo sits on (the agent work itself).

What it does (per repo with .git under ROOT, read-only, zero writes):
  1. local: git log -1  ->  head sha / timestamp / subject (git-first opener
     guarantees the local head IS origin's truth before this reads it)
  2. GET /repos/roshpinacare-sys/<repo>/actions/runs?per_page=20
     -> lanes = workflow_name grouped, latest in-window run per lane
  3. red lane = its LATEST in-window run concluded failure / timed_out /
     startup_failure. cancelled is NOT red (the 19.21 audit classified the
     dispatch+schedule double-trigger cancel as an honest casualty; the
     detector must tell the truth, not cry wolf).
Fail-closed exit codes:
  0  no red lane, no probe failure
  1  any red lane or any probe FAILED (truth is red, reported)
  2  ROOT missing or contains no git repos (fail-closed on empty scan)
No credentials are read from files, written, or logged by this script;
the token comes from the environment only (same chain as registry-verify).
"""

import base64
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ORG = "roshpinacare-sys"
WINDOW_HOURS = 24
REDS = []
PROBE_FAILURES = []
TOKEN = (subprocess.run(["printenv", "GITHUB_TOKEN"], capture_output=True,
                        text=True).stdout.strip()
         or subprocess.run(["printenv", "FLEET_TOKEN"], capture_output=True,
                           text=True).stdout.strip()
         or subprocess.run(["printenv", "SOVEREIGN_PAT"], capture_output=True,
                           text=True).stdout.strip()
         or "")


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=120)


def api(path: str) -> tuple:
    """GitHub API GET -> (status, body). Basic auth (measured in wave-19.4:
    the fleet credential answers Basic). The token never appears in a
    raised error."""
    req = Request(f"https://api.github.com{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "saos-fleet-survey")
    if TOKEN:
        req.add_header("Authorization", "Basic "
                       + base64.b64encode(TOKEN.encode()).decode())
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except Exception as e:  # honest failure, no token material ever
        msg = str(e).split(TOKEN)[0] if TOKEN else str(e)
        return 0, {"error": msg[:120]}


def survey_repo(repo: Path, cutoff: datetime) -> dict:
    rec = {"repo": repo.name, "head": None, "headAt": None,
           "subject": "", "lanes": [], "redLanes": [], "probe": "ok"}
    head = git(repo, "log", "-1", "--format=%H%n%cI%n%s")
    if head.returncode == 0:
        lines = head.stdout.strip().split("\n")
        rec["head"], rec["headAt"], rec["subject"] = \
            lines[0][:10], lines[1] if len(lines) > 1 else "", \
            (lines[2][:70] if len(lines) > 2 else "")
    else:
        rec["probe"] = "FAILED: git-log"
        PROBE_FAILURES.append(repo.name)

    status, body = api(
        f"/repos/{ORG}/{repo.name}/actions/runs?per_page=20")
    if status == 0 or status >= 400:
        rec["probe"] = f"FAILED: api-{status or 'conn'}"
        PROBE_FAILURES.append(repo.name)
        return rec
    by_lane = {}
    for run in body.get("workflow_runs", []):
        created = datetime.fromisoformat(
            run["created_at"].replace("Z", "+00:00"))
        if created < cutoff:
            continue
        lane = by_lane.setdefault(run["name"], [])
        lane.append(run)
    for name, runs in sorted(by_lane.items()):
        latest = max(runs, key=lambda r: r["created_at"])
        red = latest.get("conclusion") in (
            "failure", "timed_out", "startup_failure")
        rec["lanes"].append({
            "name": name, "runsInWindow": len(runs),
            "latestRunId": latest["id"], "status": latest["status"],
            "conclusion": latest.get("conclusion"),
            "createdAt": latest["created_at"]})
        if red:
            rec["redLanes"].append(name)
            REDS.append(f"{repo.name}/{name}")
    rec["lanes"].sort(key=lambda l: l["createdAt"], reverse=True)
    return rec


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/z/audit")
    as_json = "--json" in sys.argv
    if not root.is_dir():
        print(f"fleet-survey: ROOT missing: {root}", file=sys.stderr)
        return 2
    repos = sorted(p for p in root.iterdir() if (p / ".git").is_dir())
    if not repos:
        print(f"fleet-survey: no git repos under {root} — failing closed",
              file=sys.stderr)
        return 2
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    records = [survey_repo(r, cutoff) for r in repos]
    lanes_total = sum(len(x["lanes"]) for x in records)
    active = sum(1 for x in records if x["lanes"])
    verdict = "ok" if not REDS and not PROBE_FAILURES else "RED"
    if as_json:
        for x in records:
            print(f"  {x['repo']}: head {x['head'] or 'unknown'} "
                  f"lanes={len(x['lanes'])} red={x['redLanes'] or 'none'}"
                  + (f" PROBE={x['probe']}" if x["probe"] != "ok" else ""),
                  file=sys.stderr)
        print(f"fleet-survey: scanned={len(records)} active24h={active} "
              f"lanes={lanes_total} red={len(REDS)} probes-failed="
              f"{len(PROBE_FAILURES)} verdict={verdict}", file=sys.stderr)
        print(json.dumps(
            {"schema": "saos.fleet-survey/1",
             "at": datetime.now(timezone.utc).isoformat(),
             "org": ORG, "windowHours": WINDOW_HOURS,
             "scanned": len(records), "reposWithRuns24h": active,
             "lanesObserved": lanes_total,
             "redLaneCount": len(REDS),
             "probeFailures": len(PROBE_FAILURES),
             "verdict": verdict,
             "records": records}, ensure_ascii=False, indent=1))
    else:
        for x in records:
            print(f"== {x['repo']} ==")
            print(f"   head {x['head']} @ {x['headAt']}")
            print(f"   last: {x['subject']}")
            for lane in x["lanes"]:
                flag = "  RED" if lane["name"] in x["redLanes"] else ""
                print(f"   lane {lane['name']}: {lane['status']}/"
                      f"{lane['conclusion']} @ {lane['createdAt']}"
                      f" (runs={lane['runsInWindow']}){flag}")
            if x["probe"] != "ok":
                print(f"   PROBE {x['probe']}")
        print(f"fleet-survey: scanned={len(records)} active24h={active} "
              f"lanes={lanes_total} red={len(REDS)} "
              f"probes-failed={len(PROBE_FAILURES)} verdict={verdict}")
    return 1 if REDS or PROBE_FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
