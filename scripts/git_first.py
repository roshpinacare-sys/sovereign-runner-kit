#!/usr/bin/env python3
"""git-first — the 19.15 law as an executable tool (wave-19.16).

The owner's order, verbatim (trace 1a153c22d9e41d21):
  «תתעדכן מהגיט לא מהסנדבוקס אולי הוא מיושן»
Measured consequence: the sandbox went stale fleet-wide twice in a row
(19.15: executor +3 / beacon +4 / saos-dex +56 / saos-runtime +21, plus
Autonomy +460, Domain +646, FleetHQ +424 ...; 19.16: again 12/17 stale).
Local state is a cache. Origin is the truth. Every wave OPENS with this.

What it does (per repo with .git under ROOT):
  1. git fetch origin            (read-only to the remote)
  2. count behind:  BR..origin/BR
  3. behind > 0  ->  git pull --ff-only origin BR
What it NEVER does (anti-erasure law):
  - no force, no rebase, no stash, no reset, no checkout/restore
  - a dirty worktree blocking the ff-only merge is reported BLOCKED-DIRTY
    and counted as failure — the local file is left EXACTLY as found;
    discarding local state is a wipe-class action and needs a decision,
    never an automation default.
Fail-closed exit codes:
  0  every repo fresh or ff-only refreshed
  1  at least one repo FAILED/BLOCKED-DIRTY (truth is red, reported)
  2  ROOT missing or contains no git repos (fail-closed on empty scan)
No credentials are read, written, or logged by this script.
"""

import json
import subprocess
import sys
from pathlib import Path

FAILURES = []


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=120,
    )


def process_repo(repo: Path) -> dict:
    rec: dict = {"repo": repo.name, "branch": None, "behind": 0,
                 "action": "fresh", "detail": ""}
    br = git(repo, "symbolic-ref", "--short", "HEAD")
    if br.returncode != 0:
        rec["action"] = "FAILED"
        rec["detail"] = f"no-branch: {br.stderr.strip()[:120]}"
        FAILURES.append(rec["repo"])
        return rec
    rec["branch"] = br.stdout.strip()
    if git(repo, "fetch", "origin", "--quiet").returncode != 0:
        rec["action"] = "FAILED"
        rec["detail"] = "fetch-failed"
        FAILURES.append(rec["repo"])
        return rec
    behind = git(repo, "rev-list", "--count",
                 f"{rec['branch']}..origin/{rec['branch']}")
    if behind.returncode != 0:
        # [19.43 hardening] an empty repo (documented: sanbox) has an unborn
        # local branch and no remote counterpart — a tooling gap, not a fleet
        # wound. classify honestly as documented-empty instead of FAILED, so
        # the wave opener stays truthful (no manufactured red).
        unborn = git(repo, "rev-parse", "--verify", "--quiet", rec["branch"])
        remote = git(repo, "rev-parse", "--verify", "--quiet",
                     f"origin/{rec['branch']}")
        if unborn.returncode != 0 and remote.returncode != 0:
            rec["action"] = "documented-empty"
            rec["detail"] = ("no commits locally or on origin "
                             "(documented empty repo)")
            return rec
        rec["action"] = "FAILED"
        rec["detail"] = f"rev-list: {behind.stderr.strip()[:120]}"
        FAILURES.append(rec["repo"])
        return rec
    rec["behind"] = int(behind.stdout.strip() or 0)
    if rec["behind"] == 0:
        return rec
    pull = git(repo, "pull", "--ff-only", "origin", rec["branch"], "--quiet")
    if pull.returncode == 0:
        rec["action"] = "refreshed"
        return rec
    # fail-closed honesty: distinguish dirty-blocked from other failures,
    # and touch NOTHING either way (anti-erasure law).
    dirty = git(repo, "status", "--porcelain")
    if dirty.returncode == 0 and dirty.stdout.strip():
        rec["action"] = "BLOCKED-DIRTY"
        rec["detail"] = ("local changes block ff-only; left untouched "
                         f"(dirty files: {len(dirty.stdout.splitlines())})")
    else:
        rec["action"] = "FAILED"
        rec["detail"] = f"ff-only: {pull.stderr.strip()[:120]}"
    FAILURES.append(rec["repo"])
    return rec


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/home/z/audit")
    as_json = "--json" in sys.argv
    if not root.is_dir():
        print(f"git-first: ROOT missing: {root}", file=sys.stderr)
        return 2
    repos = sorted(p for p in root.iterdir() if (p / ".git").is_dir())
    if not repos:
        print(f"git-first: no git repos under {root} — failing closed",
              file=sys.stderr)
        return 2
    records = [process_repo(r) for r in repos]
    refreshed = sum(1 for x in records if x["action"] == "refreshed")
    blocked = sum(1 for x in records if x["action"] == "BLOCKED-DIRTY")
    failed = sum(1 for x in records if x["action"] == "FAILED")
    verdict = "ok" if not FAILURES else "RED"
    if as_json:
        # machine contract: stdout carries ONLY the JSON receipt (found in the
        # field, wave-19.17: human+JSON mixed on stdout broke direct parsing);
        # the human-readable lines move to stderr so terminals keep the view.
        for x in records:
            mark = {"fresh": "fresh",
                    "refreshed": f"REFRESHED (+{x['behind']})",
                    "BLOCKED-DIRTY": "BLOCKED-DIRTY (untouched)",
                    "FAILED": "FAILED"}.get(x["action"], x["action"])
            print(f"  {x['repo']}: {mark}" +
                  (f" — {x['detail']}" if x["detail"] else ""), file=sys.stderr)
        print(f"git-first: scanned={len(records)} refreshed={refreshed} "
              f"blocked-dirty={blocked} failed={failed} verdict={verdict}",
              file=sys.stderr)
        print(json.dumps({"schema": "saos.git-first/1",
                          "scanned": len(records),
                          "refreshed": refreshed,
                          "blockedDirty": blocked,
                          "failed": failed,
                          "verdict": verdict,
                          "records": records}, ensure_ascii=False, indent=1))
    else:
        for x in records:
            mark = {"fresh": "fresh",
                    "refreshed": f"REFRESHED (+{x['behind']})",
                    "BLOCKED-DIRTY": "BLOCKED-DIRTY (untouched)",
                    "FAILED": "FAILED"}.get(x["action"], x["action"])
            print(f"  {x['repo']}: {mark}" +
                  (f" — {x['detail']}" if x["detail"] else ""))
        print(f"git-first: scanned={len(records)} refreshed={refreshed} "
              f"fresh={len(records) - refreshed - blocked - failed} "
              f"blocked-dirty={blocked} failed={failed} verdict={verdict}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
