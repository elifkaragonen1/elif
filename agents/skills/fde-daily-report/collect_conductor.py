#!/usr/bin/env python3
"""Collect Conductor workspace activity for a given local date from the
Conductor app's local SQLite database, enriched with PR links from `gh`.

Usage: collect_conductor.py [YYYY-MM-DD]  (defaults to today, local time)

Outputs a JSON array to stdout, one object per workspace touched that day:
{company, subject, branch, repo, status_raw, status_label, closed, pr_url, updated_at}
"""
import json
import subprocess
import sys
from datetime import datetime, date

from _common import DB_PATH, owner_repo_from_remote, bitbucket_prs_for, gitlab_prs_for

# The git host's owner/org name doesn't always match the client's
# display/Linear name (e.g. Funcell's repos live under the "gameanax"
# GitLab group — confirmed via root_path: clients/funcell/*, and Linear's
# project is literally named "Funcell"). This had been done by hand in every
# report; codified here so it can't be silently missed again (2026-10-27).
COMPANY_OVERRIDES = {
    "gameanax": "Funcell",
    "racingkingdom": "Super Gears",
    "slash-games-dev": "Slash",
    "AgaveGames": "Agave",
    "M8-Games": "M8",
    "CraftG": "Craft Games",
    "3tio": "3T",
    "Stride-Games": "Stride",
    "Brew-Games": "Brew",
    "onururas-sg": "Surge",
    "digitalmoka": "Digital Moka",
    "HyperDev1": "Hyperlab",
    "flowgs": "Flow",
    "mobiva-tech": "Mobiva",
    "birch-games": "Birch Games",
}

STATUS_LABELS = {
    "in-progress": ("Devam ediyor", False),
    "in-review": ("Review'da", False),
    "done": ("Kapandı", True),
    "canceled": ("İptal edildi", True),
}


def local_date(iso_str: str) -> date:
    s = iso_str.strip()
    if "T" in s:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.astimezone().date()
    # naive "YYYY-MM-DD HH:MM:SS" is already stored in local time
    return datetime.fromisoformat(s).date()


def prs_for(host: str, owner: str, repo: str, branch: str):
    """Returns ALL PRs ever opened on this branch — a reused branch (common
    when Conductor workspaces get recycled for follow-up work) can rack up
    several separate PRs over time, and only showing the latest silently
    drops the earlier shipped work from the report.

    Checks --state all since `gh pr list` defaults to --state open, which
    would hide merged/closed PRs entirely."""
    if host != "github.com" or not owner or not repo:
        return []
    try:
        out = subprocess.run(
            [
                "gh", "pr", "list",
                "--repo", f"{owner}/{repo}",
                "--head", branch,
                "--state", "all",
                "--json", "url,state,title,number",
                "--limit", "20",
            ],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0:
            return []
        return json.loads(out.stdout or "[]")
    except Exception:
        return []


def subject_for(pr_title, branch: str) -> str:
    if pr_title:
        return pr_title
    b = branch.split("/", 1)[1] if "/" in branch else branch
    return b.replace("-", " ").replace("_", " ").strip()


def main():
    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()

    import sqlite3
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT w.branch, w.derived_status, w.pr_title, w.updated_at, w.state,
               r.name AS repo_name, r.remote_url, r.root_path
        FROM workspaces w
        JOIN repos r ON r.id = w.repository_id
        WHERE w.branch IS NOT NULL
        """
    ).fetchall()

    results = []
    for row in rows:
        if not row["updated_at"]:
            continue
        try:
            if local_date(row["updated_at"]) != target:
                continue
        except ValueError:
            continue

        host, owner, repo = owner_repo_from_remote(row["remote_url"] or "")
        status_raw = row["derived_status"] or "in-progress"
        status_label, closed = STATUS_LABELS.get(status_raw, (status_raw, False))
        prs = prs_for(host, owner, repo, row["branch"])
        prs += bitbucket_prs_for(row["root_path"], host, owner, repo, row["branch"])
        prs += gitlab_prs_for(row["root_path"], host, owner, repo, row["branch"])
        prs.sort(key=lambda p: p["number"])
        states = {p["state"] for p in prs}
        # The PR's actual state on GitHub overrides Conductor's own
        # derived_status, which rarely gets flipped to 'done' even long
        # after the PR merged. Failing that, the user archiving the
        # workspace in the Conductor app is itself a "done with this" signal
        # even when derived_status still says in-progress/in-review.
        if "MERGED" in states:
            status_label, closed = "Kapandı", True
        elif "CLOSED" in states and "OPEN" not in states:
            status_label, closed = "İptal edildi", True
        elif row["state"] == "archived":
            status_label, closed = "Kapandı", True

        # Prefer the most recent PR's title over the branch-slug fallback —
        # a real PR title written by the engineer is far more readable to
        # someone outside the work than a mechanically reformatted branch
        # name (e.g. "bruin yml location"). Bitbucket PRs have no title
        # (merge commits don't carry it), so fall back there too.
        last_titled = next((p["title"] for p in reversed(prs) if p["title"]), None)
        subject = last_titled or subject_for(row["pr_title"], row["branch"])

        company = COMPANY_OVERRIDES.get(owner, owner) if owner else None
        results.append({
            "company": company or row["repo_name"],
            "subject": subject,
            "branch": row["branch"],
            "repo": row["repo_name"],
            "status_raw": status_raw,
            "status_label": status_label,
            "closed": closed,
            "prs": [{"url": p["url"], "state": p["state"], "title": p["title"]} for p in prs],
            "updated_at": row["updated_at"],
        })

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
