# Repo Steward

An OSS-maintainer copilot built on CUGA. Triages issues, reviews PRs, drafts
changelog entries, and welcomes first-time contributors.

What makes this a **CUGA** app (not a generic LangChain wrapper) is visible in
the right-hand panel:

- **Skills** — `.agents/skills/**/SKILL.md` files the agent can load on demand:
  `issue_triage`, `pr_review`, `changelog_entry` (one PR), `release_notes`
  (multiple PRs), `contributor_welcome`.
- **Policies** — `.cuga/` markdown policies that fire for every turn. One
  intent guard (`no_exploit_code`) and four output formatters
  (`security_disclosure_escalation`, `pii_redaction`, `no_merge_promises`,
  `no_version_predictions`).

Toggle a policy off in the panel and re-run the same prompt — the output
visibly changes.

## Run

```
pip install -r requirements.txt && pip install cuga
python main.py                    # http://127.0.0.1:28822
python main.py --provider anthropic
```

## Demo arc (~2 minutes)

1. **"Triage sample issue #101"** — normal path. Agent loads the
   `issue_triage` skill, returns labels/priority/next-step. All policies pass.
2. **"Triage sample issue #102"** — body asks for a release date and includes
   an email. The `no_merge_promises` formatter rewrites any timeline
   commitment, and `pii_redaction` strips the email. Visible in the output.
3. **"Triage sample issue #103"** — body mentions CVE + exploit. The
   `security_disclosure_escalation` intent guard blocks the public-style
   response and instead routes the maintainer to the private disclosure
   process.
4. **Toggle `security_disclosure_escalation` off, re-run step 3.** The agent
   now produces a regular triage comment. Flip it back on — policy enforcement
   is live.

## Bundled sample repo

`sample_repo/` contains three issues (`101`, `102`, `103`) and two PRs (`55`,
`56`) plus a `CONTRIBUTING.md` the agent grounds in. All data is fictional.

## Using a real repo

Two ways to switch the active repo at runtime:

- **UI:** click the `sample repo` chip in the header, paste `owner/repo` or a
  `https://github.com/...` URL, hit **Switch**. The dot turns orange while a
  shallow `git clone` runs in the background, then green when ready.
- **Chat:** say *"switch to cuga-project/cuga-agent"* or *"use
  `https://github.com/foo/bar`"*. The agent calls `set_repo` itself.

Once live, the agent can:

- `list_issues` / `list_prs` — browse the repo.
- `get_issue(N)` / `get_pr(N)` — fetch a specific artifact.
- `get_repo_file("CONTRIBUTING.md")` — read any file from the local clone.

Unauthenticated GitHub API is rate-limited to ~60 req/hr. Set `GITHUB_TOKEN`
in your env for 5000 req/hr.

For a one-off lookup without switching repos, use
`fetch_github_issue(owner, repo, number)`.
