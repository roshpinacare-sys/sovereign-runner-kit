#!/usr/bin/env python3
"""pat-usage-xref.py — wave-19.41 census advance: usage cross-reference.

Evidence-only (19.40-i doctrine): no rotation without failing-lane evidence.
This tool measures WHICH repo-level secrets are referenced by that repo's
workflows (live usage surface) and cross-references the ANCIENT flag.

Output: state/pat-census-usage-<UTC date>.json + stdout summary.
Read-only. Never prints secret values (only names/flags — GitHub API metadata).
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

AUDIT = sys.argv[1] if len(sys.argv) > 1 else "/home/z/audit"
KIT = os.path.join(AUDIT, "sovereign-runner-kit")
CENSUS = os.path.join(KIT, "state", "pat-census-2026-10-20.json")

SEC_RE = re.compile(r"secrets\.([A-Za-z0-9_]+)")


def main() -> int:
    with open(CENSUS, encoding="utf-8") as f:
        census = json.load(f)
    repos = census["repos"]
    out = {
        "schema": "pat-usage-xref/v1",
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sourceCensus": "state/pat-census-2026-10-20.json",
        "classification": {
            "ancient_used": [],      # ANCIENT + referenced by a workflow -> live dependency, rotation needs cure-then-rotate
            "ancient_unused": [],    # ANCIENT + zero workflow references -> dead weight candidate (evidence stored, no action)
            "fresh_used": [],
            "fresh_unused": [],
        },
        "repos": {},
    }
    for repo, secrets in sorted(repos.items()):
        wdir = os.path.join(AUDIT, repo, ".github", "workflows")
        wf_text = ""
        if os.path.isdir(wdir):
            for fn in sorted(os.listdir(wdir)):
                if fn.endswith((".yml", ".yaml")):
                    try:
                        with open(os.path.join(wdir, fn), encoding="utf-8", errors="replace") as f:
                            wf_text += f.read() + "\n"
                    except OSError:
                        pass
        used_names = set(SEC_RE.findall(wf_text))
        per_repo = []
        for s in secrets:
            name = s["name"]
            used = name in used_names
            bucket = ("ancient_" if s.get("ancient") else "fresh_") + ("used" if used else "unused")
            out["classification"][bucket].append(f"{repo}/{name}")
            per_repo.append({"name": name, "updatedAt": s.get("updatedAt"),
                             "ancient": bool(s.get("ancient")), "used": used})
        if per_repo:
            out["repos"][repo] = per_repo
    os.makedirs(os.path.join(KIT, "state"), exist_ok=True)
    dst = os.path.join(KIT, "state", f"pat-census-usage-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    c = out["classification"]
    print(f"receipt: {dst}")
    print(f"ancient_used={len(c['ancient_used'])} ancient_unused={len(c['ancient_unused'])} "
          f"fresh_used={len(c['fresh_used'])} fresh_unused={len(c['fresh_unused'])}")
    print("--- ancient_used (live dependencies on pre-rotation secrets) ---")
    for x in c["ancient_used"]:
        print(" ", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
