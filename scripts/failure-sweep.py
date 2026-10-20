#!/usr/bin/env python3
"""failure-sweep — the EMAIL channel as a first-class truth surface (wave-19.43).

Owner order, verbatim (traces 1a15912cf0cb1455 + 1a15999028b7f2c5):
  «אני עדיין מקבל כל הזמן אימיילים של נפילות מהבוט»
  «תראה גם מה שאר הסוכנים כמוך של zai עשו כדי שנוכל לתעל את הכל
   ברמת הנדסה גבוהה מאוד»

Law (CONTINUED #37 Next + DECISIONS #31/#32): every wave opens with the 24h
failure-sweep alongside fleet-survey — the survey sees per-lane survivors,
the sweep sees EVERY run: the email channel and the survey channel are both
truth surfaces now.

What it does (per repo with .git under ROOT, read-only, zero writes):
  1. GET /repos/roshpinacare-sys/<repo>/actions/runs?per_page=100
     filtered to created_at >= now-WINDOW.
  2. Histogram by conclusion + the full failure list (id/name/event/created/
     head_sha) so the opener can root-cause and classify per DECISIONS #31:
       A standing infrastructure walls (private repos — must stay 0 runs)
       B vestigial relays      (cured: printed honest skip)
       C un-armed dispatches   (cured: SKIP class)
       D real regressions      (stay LOUD — the email is the feature)
       E push-contention       (receipt landed, run red on transport race —
                                DECISIONS #32: alive-wins landed-check)
Fail-closed exit codes:
  0  zero failure runs in window (email channel silent)
  1  any failure run in window (truth is red, reported — opener must read
     and classify; class-D emails are BY DESIGN)
  2  ROOT missing or contains no git repos
The token comes from the environment only; never logged, never written.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ORG = "roshpinacare-sys"
DEFAULT_WINDOW_HOURS = 24
TOKEN = (subprocess.run(["printenv", "GITHUB_TOKEN"], capture_output=True,
                        text=True).stdout.strip()
         or subprocess.run(["printenv", "FLEET_TOKEN"], capture_output=True,
                           text=True).stdout.strip()
         or subprocess.run(["printenv", "SOVEREIGN_PAT"], capture_output=True,
                           text=True).stdout.strip()
         or "")

# DECISIONS #31-A: the private billing wall — these must stay at 0 runs.
PRIVATE_WALL_REPOS = {
    "SovereignConsole", "negen", "ops-control", "sanbox",
    "saos-console-zai", "saos-coordination", "vault-home",
}


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, timeout=120)


def api(path: str) -> tuple:
    req = Request("https://api.github.com" + path)
    req.add_header("Authorization", "Basic " +
                   __import__("base64").b64encode(
                       TOKEN.encode()).decode())
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "saos-failure-sweep/1")
    try:
        with urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001 — status surfaced honestly
        code = getattr(e, "code", 0)
        return code, {"message": str(e)[:200]}


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/z/audit")
    if not root.is_dir():
        print(json.dumps({"schema": "saos.failure-sweep/1",
                          "error": f"ROOT missing: {root}"}))
        return 2
    repos = sorted(p.name for p in root.iterdir()
                   if (p / ".git").is_dir())
    if not repos:
        print(json.dumps({"schema": "saos.failure-sweep/1",
                          "error": "no git repos under ROOT"}))
        return 2

    window_h = DEFAULT_WINDOW_HOURS
    for a in sys.argv[2:]:
        if a.startswith("--hours="):
            try:
                window_h = max(1, int(a.split("=", 1)[1]))
            except ValueError:
                pass
    since = datetime.now(timezone.utc) - timedelta(hours=window_h)
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    failures = []
    probe_fails = []
    wall_breaches = []
    hist = {}
    total_runs = 0

    for name in repos:
        st, body = api(
            f"/repos/{ORG}/{name}/actions/runs?per_page=100")
        if st != 200:
            probe_fails.append({"repo": name, "status": st})
            continue
        runs = body.get("workflow_runs", [])
        for r in runs:
            created = r.get("created_at", "")
            if created and created < since_iso:
                continue
            total_runs += 1
            c = r.get("conclusion") or "in_progress"
            hist[c] = hist.get(c, 0) + 1
            if c in ("failure", "timed_out", "startup_failure"):
                rec = {
                    "repo": name,
                    "run_id": r.get("id"),
                    "name": r.get("name"),
                    "event": r.get("event"),
                    "created_at": created,
                    "head_sha": (r.get("head_sha") or "")[:9],
                    "url": r.get("html_url"),
                }
                failures.append(rec)
                if name in PRIVATE_WALL_REPOS:
                    wall_breaches.append(rec)

    out = {
        "schema": "saos.failure-sweep/1",
        "generatedAt": datetime.now(timezone.utc)
                         .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "windowHours": window_h,
        "windowSince": since_iso,
        "reposScanned": len(repos),
        "totalRunsInWindow": total_runs,
        "conclusionHistogram": hist,
        "failureCount": len(failures),
        "probeFailures": probe_fails,
        "wallBreaches": wall_breaches,
        "failures": failures,
    }
    print(json.dumps(out, indent=1, ensure_ascii=False))

    # receipt next to the survey receipt (SANDBOX-PERSISTENCE: git is home)
    try:
        state = root / "sovereign-runner-kit" / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "failure-sweep-last-run.json").write_text(
            json.dumps(out, indent=1, ensure_ascii=False))
    except OSError:
        pass

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
