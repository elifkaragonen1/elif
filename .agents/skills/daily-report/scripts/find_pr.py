#!/usr/bin/env python3
"""Best-effort PR lookup for a Linear issue.

Linear issues here don't reliably carry a synced GitHub PR attachment, so
this guesses the repo from the Linear project name (matched against the
Conductor app's known repos) and asks `gh` for an open/merged PR on the
issue's suggested git branch. Prints the PR URL if found, else nothing.

Usage: find_pr.py <linear-project-name> <git-branch-name>
"""
import json
import sqlite3
import subprocess
import sys

from _common import DB_PATH, normalize, owner_repo_from_remote


def main():
    project, branch = sys.argv[1], sys.argv[2]
    norm_project = normalize(project)
    if not norm_project:
        return

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = conn.execute("SELECT DISTINCT name, remote_url FROM repos").fetchall()

    seen = set()
    for name, remote_url in rows:
        host, owner, repo = owner_repo_from_remote(remote_url)
        if host != "github.com" or not owner or not repo or (owner, repo) in seen:
            continue
        haystack = normalize(f"{owner}{repo}{name}")
        if norm_project not in haystack:
            continue
        seen.add((owner, repo))
        try:
            out = subprocess.run(
                [
                    "gh", "pr", "list",
                    "--repo", f"{owner}/{repo}",
                    "--head", branch,
                    "--state", "all",
                    "--json", "url",
                    "--limit", "1",
                ],
                capture_output=True, text=True, timeout=15,
            )
            items = json.loads(out.stdout or "[]")
            if items:
                print(items[0]["url"])
                return
        except Exception:
            continue


if __name__ == "__main__":
    main()
