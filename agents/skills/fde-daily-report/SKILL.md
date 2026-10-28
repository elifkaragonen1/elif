---
name: daily-report
description: Generate today's daily status report (meeting notes + Linear/Conductor task activity) for reporting to the manager.
---

# Daily report

**Note (2026-10-28):** this used to live at `.claude/skills/daily-report/`
where Claude Code auto-discovers it as a `/daily-report` slash-command/Skill.
It was moved here, to `agents/skills/fde-daily-report/`, on request — that
means it's **no longer auto-invocable**. There's nothing left under
`.claude/skills/`. To run this, read this file directly and follow it by
hand (e.g. "agents/skills/fde-daily-report'taki talimatları takip et").

Produces a Markdown report combining that day's meeting notes with every
Linear issue and Conductor workspace touched that day, grouped by company,
with clickable PR links and open/closed status. Saved to `reports/<date>.md`
in this repo.

## 1. Determine the target date

Default to today's local date (`date +%F`). If the user passed a date in
`args` (e.g. `/daily-report 2026-09-15`), use that instead.

## 2. Get meeting notes

If the user's invocation already included meeting notes text, use it as-is.
Otherwise ask them to paste that day's meeting notes before continuing. Do
not fabricate notes — if the user says there were no meetings, write "Bugün
toplantı yoktu." in that section.

## 3. Collect Conductor workspace activity

Run the bundled collector script, which reads Conductor's local SQLite DB
(`~/Library/Application Support/com.conductor.app/conductor.db`), joins
workspace → repo to resolve the company, and looks up any matching GitHub PR
via `gh pr list`:

```
python3 agents/skills/fde-daily-report/collect_conductor.py <YYYY-MM-DD>
```

This prints a JSON array of `{company, subject, branch, repo, status_raw,
status_label, closed, prs, updated_at}` for every workspace whose
`updated_at` falls on that local date. `prs` is a list (possibly empty) of
`{url, state, title}` — **a branch can have more than one PR** (Conductor
workspaces get reused for follow-up work, so the same branch can rack up
several separate merged PRs over weeks). Per the user's explicit instruction
(2026-10-23): **list every PR in `prs`, not just one** — render the PR
column as all of them, e.g. `[#82](url82), [#85](url85)`, not just the
latest.

Non-GitHub hosts are covered too, via fallbacks in `_common.py` (both use
the local clone at `repos.root_path` from Conductor's DB, since there's no
API token configured for either host):
- **Bitbucket** (Super Gears/racingkingdom, 3T, Birch Games' analytics-bruin)
  via `bitbucket_prs_for()` — greps merge-commit messages for Bitbucket's
  default "Merged in `<branch>` (pull request #N)" format. Only finds
  **merged** PRs (no merge commit exists for open/declined ones), and has
  no PR title (the merge commit doesn't carry one — `title` will be `null`,
  falls back to branch-slug/pr_title).
- **GitLab** (Funcell's repos, under the `gameanax` GitLab group) via
  `gitlab_prs_for()` — parses GitLab's default merge-commit format
  ("Merge branch '`<branch>`' into 'main'" + blank line + MR title + blank
  line + "See merge request `<ns>`!`<N>`"). Unlike Bitbucket, this **does**
  give a real title, so GitLab-found PRs read as well as GitHub ones.

Found a 3rd host missing here mid-report (2026-10-27: Funcell's repos
turned out to be GitLab, invisible to both the GitHub and Bitbucket paths
for over a month before this was caught) — if a client's "Kapanan" PR
column is suspiciously always "—", check `repos.remote_url` for that repo
before assuming no PR exists; it may be a host this script doesn't handle
yet. Still link every PR number found regardless of host, e.g.
`[#60](https://bitbucket.org/<workspace>/<repo>/pull-requests/60)` or
`[#2](https://gitlab.com/<group>/<repo>/-/merge_requests/2)` — don't render
"—" just because `gh` specifically can't see it.

**Company name ≠ git host owner, always.** `collect_conductor.py` applies a
`COMPANY_OVERRIDES` map (e.g. `gameanax` → `Funcell`, `racingkingdom` →
`Super Gears`) so the script's `company` field is already the client-facing
name — use it as-is, don't re-derive company from the raw git owner/org by
hand. If a brand-new company/repo shows up with an owner name that doesn't
look like the client's real name, add it to `COMPANY_OVERRIDES` rather than
silently mislabeling it in the table (this is exactly how Funcell's work
went unlabeled as "Gameanax" for a month).

`status_label`/`closed` here already account for the actual PR state on
GitHub (closed if ANY PR in `prs` is merged) AND for the workspace being
archived in the Conductor app (a workspace the user archived counts as
closed even with no matching PR — they archive it once they're done with
it, whether or not a PR/derived_status agrees). Trust these fields as-is,
don't recompute from `status_raw`.

**Caveat (2026-10-28):** an archived-with-no-PR row isn't always real work
from the report's date — the user can archive a batch of old stale
workspaces in one sitting, which bumps `updated_at` into today's window
without any actual work happening that day (this reads a lot like the
2026-09-28 bulk-Linear-update incident, just smaller and without identical
timestamps, so it's harder to catch mechanically). If a day's Kapanan list
has several no-PR archived rows with no other signal of real activity,
flag it to the user before including them rather than assuming every
archived row is a same-day close — ask, the way you would for a suspicious
bulk timestamp pattern.

**On "Konu" (subject) clarity** — per the user's explicit instruction
(2026-10-23): this report is read by people who did not do the work and
have no context on the original request. The script's `subject` field
prefers the latest PR's title over a branch-slug fallback (a real PR title
an engineer wrote, e.g. "Add the hidden_object forecast model", reads far
better than a mechanically reformatted branch name like "bruin yml
location") — but even that isn't always good enough. When composing the
table, don't paste `subject` verbatim if it's still cryptic, internal
shorthand, or phrased as however the original question/prompt was worded
(e.g. "check user id", "fix custom check", "v2") — rewrite it as a short
plain-language description of what actually got done, the way you'd explain
it to someone outside the work. Use the PR title(s)/description and your
own understanding of the task to write that description; don't just relay
the raw field.

**This list alone under-reports closed work.** It only includes workspaces
Conductor itself touched (`updated_at`) on that exact date — a PR that got
merged that day but whose Conductor workspace was last touched on a
different day (or was reused afterwards for follow-up work) won't show up
here as closed, or won't show up at all. Always also run step 3b.

## 3b. Collect merged/closed PRs (the authoritative "closed today" source)

```
python3 agents/skills/fde-daily-report/collect_merged_prs.py <YYYY-MM-DD>
```

This asks GitHub directly — `gh pr list --state all --author @me` across
every GitHub repo Conductor knows about — for PRs merged or closed on that
local date, regardless of what Conductor's own DB says. Use this as the
**"Kapanan" table**, and treat it as more trustworthy than
`collect_conductor.py`'s `closed` flag for the historical record: Conductor's
`derived_status` rarely flips to "done" even long after the underlying PR
merged, so relying on it alone makes days look emptier of closed work than
they actually were.

When building the "Devam eden" (still open) table from
`collect_conductor.py`, drop any row whose `branch` also appears in this
day's merged-PR list — it's actually closed, just tracked under a stale
Conductor status.

`collect_merged_prs.py` and `find_pr.py` are still GitHub/`gh`-only and
don't cover Bitbucket or GitLab clients (Super Gears, 3T, Birch Games,
Funcell) — only `collect_conductor.py` has those fallbacks (see step 3). So
a Bitbucket/GitLab PR merged on a day its Conductor workspace wasn't itself
touched won't surface anywhere. If one of those clients' "Kapanan" row has
no PR from `collect_conductor.py` either, note it plainly ("PR bulunamadı
ama workspace arşivlenmiş") rather than implying no PR exists — it might,
just outside what these scripts can currently see.

## 4. Collect Linear activity

Call `list_issues` with:
- `assignee: "me"`
- `updatedAt: "<target-date>T00:00:00"` (local)
- `fields: ["title","url","project","status","statusType","gitBranchName","updatedAt"]`

Then locally filter results to only those whose `updatedAt` falls on the
target date (the tool filter is "updated after", not "updated on").

For each remaining issue, determine company from the `project` field (NOT
`team` — every issue's `team` is just "Data" regardless of client, but
`project` holds the actual client name, e.g. "Agave", "Slash", "M8"). Issues
with no `project` still go in the table — label the company "Genel" rather
than dropping them.

Closed vs open: `completed` → closed, `canceled` → İptal edildi, AND — per
the user's explicit instruction (2026-10-15) — **`In Review` also counts as
closed/🟢 Kapandı, not 🔵 Review'da.** Her reasoning: once her side of the
work is in review, she considers it done; only `In Progress`/`Todo` are
still actually open. This only applies to Linear issue status, not to
Conductor/GitHub PR review state in the "Devam eden" table — a PR still
open for review on GitHub is still 🔵 Review'da there, since that reflects
objectively unmerged code.

For the PR link: Linear issues here rarely have a synced PR attachment (the
GitHub integration doesn't reliably link them), so use the bundled
best-effort matcher instead — it maps the Linear `project` name to a known
repo (via Conductor's repo list) and checks `gh` for a PR on the issue's
`gitBranchName`:

```
python3 agents/skills/fde-daily-report/find_pr.py "<project>" "<gitBranchName>"
```

Prints a PR URL if found, nothing otherwise. This only catches PRs pushed
under the exact branch Linear suggested — if the engineer worked on a
differently-named branch (common when the work started from a Conductor
workspace), it will find nothing. In that case, before giving up, eyeball
whether a title in the same day's merged-PR list (step 3b) plausibly matches
the same company + topic (e.g. Linear "Adding dashboards to Number Path" for
Slash vs. a merged PR literally about the Number Path pipeline for Slash
that same day) — if so, link it but mark it with a footnote that it's an
inferred match, not a Linear-confirmed one. Otherwise the PR column is "—".
Don't silently guess without flagging it as inferred.

## 4b. Collect open Follow-Ups (always, regardless of date)

The user has a custom Linear status called **"Follow-Ups"** (statusType
`started`, exact name matters — Linear will silently return zero results if
you pass `Follow-ups` with the wrong casing) for questions asked to someone
else (e.g. Sabri) that are waiting on a reply. She moves an issue into this
status when she asks the question, and out to `Done` once it's resolved.

Call `list_issues` with `assignee: "me"`, `state: "Follow-Ups"`, no
`updatedAt` filter — every issue sitting in this status must show up in the
report every single day until it's moved out, not just the day it was
created or last touched. A question with no reply for a week is exactly what
this section exists to surface.

Put these in their own **"Takip Edilecekler"** section, unconditionally —
even if the section would otherwise be empty on a quiet day, check it, and
if there's nothing there write "Bekleyen takip yok." Exclude any issue
that's currently in `Follow-Ups` status from the regular step-4 Linear table
(it belongs only in this section, not duplicated in both).

The intended pattern: when the actual work is done but leaves a side
question for someone else (e.g. Sabri), the parent issue keeps its real
status (Review/Done) and the question becomes a **sub-issue** of it, sitting
in `Follow-Ups` on its own. So a Follow-Ups issue can have a `parentId` — if
it does, call `get_issue` on the parent and show its title alongside the
question in the report ("Ana task: <parent title>") so it's clear which
finished piece of work the question hangs off of. A Follow-Ups issue with no
parent is just a standalone question and needs no extra lookup (e.g. DAT-249
"A/B test PR review" — a question in its own right, not spun off a finished
task).

If asked to open a new Follow-Ups sub-issue for a question (e.g. "şu task'a
follow-up açtım" or "bu soruyu takibe al"), use `save_issue` to create a
child issue (`parentId` = the task being asked about) with `state:
"Follow-Ups"` and a title describing the question — don't move the parent
issue's own status.

## 4c. Rank To Do's (always, regardless of date)

Linear issues with `statusType: "unstarted"` (Todo) are NOT started work, so
they never go in the regular Linear table — but instead of dropping them,
build a prioritized **"To Do's"** list so the user knows what to pick up
next. Call `list_issues` with `assignee: "me"`, `state: "Todo"`, fields
`["title","project","priority","dueDate","createdAt"]`, no date filter.

Ranking rule (apply in order):
1. **Drop any issue with no `project`** — an unassigned-to-a-company Todo
   doesn't belong on this list at all, regardless of anything else.
2. Among what's left, sort by `priority.value` first — Linear's scale is
   1=Urgent, 2=High, 3=Medium, 4=Low, treat 0 ("No priority") as the lowest
   tier, sorted after 1-4, not before (0 is a numeric trap — don't sort it
   as if it outranks 1).
3. Within the same priority tier, sort by `dueDate` ascending (soonest/most
   overdue first); issues with no `dueDate` sort last within their tier.

In practice `priority` is often unset across the board (verified: every
Todo issue had "No priority" as of 2026-10-13) — when that's the case the
whole list collapses to step 3 (project required, then due date). Don't
silently skip the priority check just because it's usually empty; a future
issue might actually have one set.

Put this in its own **"To Do's (önerilen sıra)"** section, ranked order,
each row showing company + title + due date (or "—" if none). This list is
informational/suggestive, not a status report — no PR or Durum column
needed.

## 5. Compose the report

Write `reports/<date>.md` with this structure:

```markdown
# Günlük Rapor — <date>

## Toplantı Notları
<meeting notes>

## Görevler

### Kapanan (merge edilen PR'lar)
| Şirket | Konu | PR | Durum |
|---|---|---|---|
| <company> | <plain-language description> | [#<n>](<url>)[, #<n2>](<url2>)... | 🟢 Kapandı |

### Devam eden
| Şirket | Konu | PR | Durum |
|---|---|---|---|
| <company> | <plain-language description> | [#<n>](<url>)[, #<n2>](<url2>)... or — | 🔵 Review'da / 🟡 Devam ediyor |

### Linear
| Şirket | Konu | PR | Durum |
|---|---|---|---|
| <project> | <title> | [#<n>](<pr_url>) or — | 🟢 Kapandı / 🔵 Review'da / 🟡 Devam ediyor / ⚪ İptal |

### Takip Edilecekler
| Şirket | Konu | Sorulma Tarihi | Link |
|---|---|---|---|
| <project> | <title> | <createdAt or updatedAt, local date> | [Linear](<url>) |

### To Do's (önerilen sıra)
| Şirket | Konu | Due date |
|---|---|---|
| <project> | <title> | <dueDate or —> |
```

Status emoji: 🟢 Kapandı (merged, Linear `completed`, OR Linear status
`In Review` — see 4. above), 🔵 Review'da (Conductor workspace with an open
GitHub PR under review — Linear-side review doesn't use this anymore),
🟡 Devam ediyor (Conductor `in-progress`, or Linear `In Progress`), ⚪ İptal
edildi (`canceled`/closed-unmerged).

Linear issues with `statusType: "unstarted"` (Todo) never go in the regular
Linear table (filter them out before building it) — they're handled
separately by step 4c's ranked "To Do's" section instead.

If a section has no rows, write "Bugün bu kaynakta işlenen task yok." instead
of an empty table.

## 6. Save and show

Write the file to `reports/<date>.md` (create the `reports/` directory if
missing), then also print the full report in the chat reply so the user can
review and request revisions before anything gets sent anywhere.

## 7. Send to Slack (only when asked)

Once the user confirms the report is ready (e.g. "gönder"), post it as a
Slack Canvas and drop a link to it in **#elif-onboarding**
(channel ID `C07QXSJQ8RG`, updated 2026-10-23 — previously this went to a
DM with Sabri, that's no longer where it goes):

1. `slack_create_canvas` with the full report content (title: "Günlük
   Rapor — `<date>`"), using `#` for the date, `##`/`###` for subsections —
   same Markdown as the `.md` file.
2. `slack_send_message` to channel `C07QXSJQ8RG` with a short line plus the
   canvas link, e.g. "Merhaba, `<date>` günlük rapor: `<canvas_url>`".

Always show the full report text in chat first and wait for explicit
confirmation before this step — never send to Slack unprompted.
