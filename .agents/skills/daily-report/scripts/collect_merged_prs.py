#!/usr/bin/env python3
"""Ground-truth "closed today" signal: merged/closed GitHub PRs authored by
me, across every GitHub repo Conductor knows about, filtered to the ones
whose merge/close date falls on the target local date.

Conductor's own `derived_status` on a workspace is NOT reliable for this —
it rarely flips to 'done' even when the PR was long since merged, and once
a workspace is reused or cleaned up the row may no longer reflect the merge
at all. This asks GitHub directly instead.

Usage: collect_merged_prs.py [YYYY-MM-DD]
"""
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, date

from _common import DB_PATH, owner_repo_from_remote


def local_date(iso_str: str) -> date:
    return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).astimezone().date()


def github_repos():
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = conn.execute("SELECT DISTINCT remote_url FROM repos").fetchall()
    seen = set()
    out = []
    for (remote_url,) in rows:
        host, owner, repo = owner_repo_from_remote(remote_url or "")
        if host == "github.com" and owner and repo and (owner, repo) not in seen:
            seen.add((owner, repo))
            out.append((owner, repo))
    return out


def main():
    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    results = []
    for owner, repo in github_repos():
        try:
            out = subprocess.run(
                [
                    "gh", "pr", "list",
                    "--repo", f"{owner}/{repo}",
                    "--state", "all",
                    "--author", "@me",
                    "--json", "number,title,url,state,mergedAt,closedAt,headRefName",
                    "--limit", "100",
                ],
                capture_output=True, text=True, timeout=30,
            )
            if out.returncode != 0:
                continue
            items = json.loads(out.stdout or "[]")
        except Exception:
            continue

        for pr in items:
            if pr["state"] == "MERGED" and pr.get("mergedAt"):
                when = local_date(pr["mergedAt"])
                outcome = "merged"
            elif pr["state"] == "CLOSED" and pr.get("closedAt"):
                when = local_date(pr["closedAt"])
                outcome = "closed_unmerged"
            else:
                continue
            if when != target:
                continue
            results.append({
                "company": owner,
                "repo": repo,
                "subject": pr["title"],
                "branch": pr["headRefName"],
                "pr_url": pr["url"],
                "pr_number": pr["number"],
                "outcome": outcome,
            })

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
