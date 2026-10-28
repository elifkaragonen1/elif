from pathlib import Path

DB_PATH = Path.home() / "Library/Application Support/com.conductor.app/conductor.db"


def owner_repo_from_remote(remote_url: str):
    """git@host:owner/repo.git or https://host/owner/repo.git -> (host, owner, repo)."""
    remote_url = (remote_url or "").strip()
    if not remote_url:
        return None, None, None
    if remote_url.startswith("git@"):
        host_part, _, path = remote_url.partition(":")
        host = host_part.split("@", 1)[1]
    else:
        from urllib.parse import urlparse

        parsed = urlparse(remote_url)
        host = parsed.netloc
        path = parsed.path.lstrip("/")
    path = path[:-4] if path.endswith(".git") else path
    parts = path.split("/")
    if len(parts) < 2:
        return host, None, None
    return host, parts[0], parts[1]


def normalize(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def gitlab_prs_for(root_path: str, host: str, owner: str, repo: str, branch: str):
    """Best-effort MR discovery for GitLab-hosted repos (e.g. Funcell's
    gameanax/* repos) — a third host `gh` and the Bitbucket fallback both
    miss entirely. Same approach as `bitbucket_prs_for`: fetch the local
    clone and parse merge-commit messages. GitLab's default merge commit
    looks like:

        Merge branch '<branch>' into 'main'

        <MR title>

        See merge request <namespace>!<N>

    so unlike Bitbucket this actually gives us a usable title.
    """
    if host != "gitlab.com" or not root_path or not owner or not repo:
        return []
    import re
    import subprocess

    try:
        subprocess.run(
            ["git", "-C", root_path, "fetch", "origin", "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
        out = subprocess.run(
            ["git", "-C", root_path, "log", "--all", "--merges",
             "--grep", f"Merge branch '{branch}' into",
             "--format=%H%x1e%B%x1d"],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0:
            return []
        results = []
        seen = set()
        for record in out.stdout.split("\x1d"):
            record = record.strip()
            if not record:
                continue
            _, _, body = record.partition("\x1e")
            m = re.search(r"merge request [\w./-]+!(\d+)", body)
            if not m:
                continue
            n = int(m.group(1))
            if n in seen:
                continue
            seen.add(n)
            lines = [ln for ln in body.splitlines() if ln.strip()]
            title = lines[1] if len(lines) > 1 else None
            results.append({
                "url": f"https://gitlab.com/{owner}/{repo}/-/merge_requests/{n}",
                "state": "MERGED", "title": title, "number": n,
            })
        return results
    except Exception:
        return []


def bitbucket_prs_for(root_path: str, host: str, owner: str, repo: str, branch: str):
    """Best-effort PR discovery for Bitbucket-hosted repos.

    `gh` only talks to GitHub, and there's no Bitbucket API token configured
    here (only an SSH deploy key for git itself) — so instead of showing
    nothing, this fetches the local clone (via `root_path` from Conductor's
    repos table) and greps merge-commit messages for Bitbucket's default
    "Merged in <branch> (pull request #N)" format. This only finds PRs that
    were actually merged (no merge commit exists for open/declined ones),
    and has no PR title (the merge commit doesn't carry it) — good enough to
    stop silently dropping real merged work for Bitbucket clients.
    """
    if host != "bitbucket.org" or not root_path or not owner or not repo:
        return []
    import re
    import subprocess

    try:
        subprocess.run(
            ["git", "-C", root_path, "fetch", "origin", "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
        out = subprocess.run(
            ["git", "-C", root_path, "log", "--all", "--merges", "--oneline",
             "--grep", f"Merged in {branch} ("],
            capture_output=True, text=True, timeout=15,
        )
        if out.returncode != 0:
            return []
        numbers = sorted(set(
            int(m.group(1))
            for m in re.finditer(r"\(pull request #(\d+)\)", out.stdout)
        ))
        return [
            {"url": f"https://bitbucket.org/{owner}/{repo}/pull-requests/{n}",
             "state": "MERGED", "title": None, "number": n}
            for n in numbers
        ]
    except Exception:
        return []
