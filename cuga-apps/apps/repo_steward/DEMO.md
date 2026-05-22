# Repo Steward — Live Demo

Two-minute live arc for showing what CUGA gives you that a plain LangChain
agent doesn't: **skills** as discoverable playbooks and **policies** as
configurable governance rails, both visible in real time.

## Prerequisites

Checkout the skills branch of cuga-agent once:

```
git clone -b feat/skills-support https://github.com/cuga-project/cuga-agent
pip install -e ./cuga-agent
```

Any standard CUGA LLM provider works — any modern chat model with tool use
is fine.

## Start

```
cd cuga-apps/apps/repo_steward
pip install -r requirements.txt
python main.py --provider anthropic    # or openai / ollama / litellm
```

Then open **http://127.0.0.1:28822**.

## The demo (≈ 2 minutes)

### Frame

*"A maintainer copilot. Every other agent framework would wire this as one
system prompt. CUGA lets me express the 'how to do the work' part as **skills**
— discoverable markdown playbooks — and the 'what the agent must and must not
say' part as **policies** — separate, toggleable, and visible to the user.
Watch what happens on three different issues."*

### Step 1 — Normal triage (30s)

Click chip: **"Triage sample issue #101"** (a plain bug report).

What judges see:

- Right panel — **Skills card** lights up: `issue_triage` highlighted
  (the agent loaded it on demand).
- Right panel — **Policies card**: all four policies green; none fired.
- Left answer: clean `### Labels / ### Priority / ### Summary / ### Next step`
  markdown — the exact format declared in `issue_triage/SKILL.md`.

Talking point:
*"The agent fetched the issue, then called `load_skill("issue_triage")` —
nothing in its system prompt told it the output format. That's in the skill
file. Policies all passed."*

### Step 2 — Security disclosure (30s)

Click chip: **"Triage sample issue #103"** (body mentions CVE, XSS, "working
exploit payload").

What judges see:

- Same skill loads (`issue_triage`).
- **Policies card**: `security_disclosure_escalation` flips to **fired**.
- Turn card: new expandable section **"What the security_disclosure_escalation
  policy rewrote"** — click it to reveal a side-by-side diff:
  - **Left (blocked)**: the P0-critical triage draft, echoing "XSS" and
    confirming the vulnerability exists.
  - **Right (final)**: `"Route the reporter to SECURITY.md… do not confirm,
    deny, or speculate publicly…"` — no vulnerability details, no severity
    claim.

Talking point:
*"Same skill, same prompt, same model — but a response-shaped policy fired on
the agent's draft output. The left column is what the agent was going to say;
the right column is what actually shipped. The policy is a markdown file I
can hand to security or legal to review independently of the agent code."*

### Step 3 — The toggle (45s) ← **the "aha" moment**

In the **Policies card**, click the checkbox next to
`security_disclosure_escalation` to disable it.

Click the **"Triage sample issue #103"** chip again.

What judges see:

- Same skill, same tools, same prompt.
- This time **no policy fires** — the agent's raw draft ships, calling out
  the XSS openly.
- The disabled policy has a strikethrough / dimmed row in the Policies card.

Re-enable the policy (one click), re-run — the rewrite returns.

Talking point:
*"That was a single flag flip — no code change, no redeploy, no prompt edit.
The policy markdown file is the contract; the enforcement is configuration.
That's what changes when you ship a governance layer instead of coding every
guardrail into a prompt."*

### Step 4 — Release notes + version-prediction policy (30s)

Click chip: **"Draft release notes for PRs 55, 56, and 57, targeting version
2.0 shipping next week"**.

What judges see:

- Different skill loads: `release_notes` (not `changelog_entry` — the agent
  chose it because the task spans multiple PRs).
- Tools: `list_sample_prs` / `get_sample_pr` called three times as the agent
  walks the PR list.
- **Policies card**: `no_version_predictions` flips to **fired**.
- Turn card: expandable **"What the no_version_predictions policy rewrote"**
  section shows the diff:
  - **Left (blocked)**: `## 2.0 (shipping next week)` — optimistic release
    heading with a date the agent had no business committing to.
  - **Right (final)**: `## Unreleased` with a one-line note
    `_[no_version_predictions] Removed forward-looking version/ship-date
    commitments._`. Actual PR entries survive intact.

Talking point:
*"The user literally told the agent to ship 2.0 next week. A prompt-only
defense would require me to convince the agent not to comply — fragile. A
policy layer doesn't care what the user asked for: the formatter sees `next
week` / `shipping` in the output and strips it. This is one of the failure
modes every engineering org has hit — someone drafts release notes during
planning and the dates escape."*

### (Optional) Step 5 — First-time contributor (15s)

Click chip: **"Write a welcome comment for the author of PR #55"**.

What judges see:

- The agent loads a different skill: `contributor_welcome`.
- The tone in the answer matches the skill's rules exactly: no exclamation
  marks, no merge promise, neutral sign-off, under 120 words.

Talking point:
*"Skills compose. The same agent picks a different one based on the task. The
`no_merge_promises` formatter is always active — any answer that drifted into
'we'll merge this next week' would have been rewritten."*

### Step 6 — Author a policy live, on stage (45s) ← **the second "aha"**

Keep the app running. In a terminal, drop a new policy file into
`.cuga/output_formatters/` while the demo is live. Example:

```
cat > .cuga/output_formatters/no_ai_attribution.md <<'EOF'
---
name: no_ai_attribution
description: Strip "generated by", "AI-assisted", and similar attributions from any output — maintainers want to read the substance, not the provenance.
triggers:
  always: true
format_type: markdown
priority: 60
---

Scan the response for phrases like:
- "generated with AI"
- "AI-assisted"
- "drafted by an assistant"
- "[automatically generated]"

Remove them. Do not replace with anything. Leave the remaining content
otherwise identical. If the entire response was an attribution, replace
with a single sentence summary drawn from the user's original request.
EOF
```

Within ~2 seconds:

- **Policies card** repaints: `no_ai_attribution` appears in the list with
  its new pill. Count goes from 5 to **6**.
- **"reloaded Ns ago"** badge next to the Policies header flips green for
  a moment and shows a fresh timestamp.

Click any chip that produces attribution-laden output (e.g. re-run the
release-notes chip) and watch the new policy fire on its very first turn —
no restart, no redeploy.

Talking point:
*"I just authored and deployed a new governance rule by writing a markdown
file. No build step, no migration, no code change in the agent. The
watcher picked it up, CUGA loaded it, and it started enforcing on the next
turn. Compare that to baking the rule into a system prompt — you'd be
rebuilding an image and redeploying the agent for what amounts to a paragraph
of English."*

### Step 7 — Switch to a live repo (45s)

Two ways to trigger:

- **UI:** click the `sample repo` chip in the header → form opens → paste
  `cuga-project/cuga-agent` (or any GitHub URL) → **Switch**.
- **Chat:** click the chip **"Switch to cuga-project/cuga-agent and list the
  5 most recent open issues"**, and the agent will call `set_repo` itself.

What judges see:

- Header chip flips from a gray dot to an **orange pulsing dot** labelled
  `cuga-project/cuga-agent` — the background `git clone` is in flight.
- Within a few seconds the dot turns **green**; the repo is ready.
- Chat response lists 5 real open issues from the actual cuga-agent repo,
  pulled via the public GitHub REST API.

Now click any chip like **"Triage issue #N"** (using a real number from the
list). The agent runs the same `issue_triage` skill, against the new issue,
with the same policies active. Policies fire exactly as before if the body
contains CVE keywords, email addresses, etc.

Talking point:
*"Same agent, same skills, same policies — swapped in a real OSS project at
runtime. The clone is shallow and cached in `/tmp`, so `get_repo_file
CONTRIBUTING.md` works instantly on the second call. And because the
governance layer is decoupled from the data source, a private repo (via
GitHub Enterprise or any other source) would plug in the same way — just
swap the fetch tools. The policy markdown files don't care."*

Hit the **Sample** button in the header to restore the offline repo.

## Panel state at each step

| Step | Skill loaded         | Policies fired                      | Output shape                              |
|------|----------------------|-------------------------------------|-------------------------------------------|
| 1    | `issue_triage`       | — (all pass)                        | Triage markdown (skill)                   |
| 2    | `issue_triage`       | `security_disclosure_escalation`    | Private-disclosure note                   |
| 3    | `issue_triage`       | — (policy disabled)                 | Raw triage, vuln echoed                   |
| 4    | `release_notes`      | `no_version_predictions`            | Release notes w/ version heading stripped |
| 5    | `contributor_welcome`| — (all pass)                        | Welcome comment                           |
| 6    | —                    | `no_ai_attribution` loaded at runtime | New policy appears in panel in ~2s      |
| 7    | `issue_triage`       | varies                              | Live-repo triage (post-`set_repo`)        |

## What's under the hood

| Capability           | Location                                               |
|----------------------|--------------------------------------------------------|
| Skills               | `.agents/skills/<name>/SKILL.md`                       |
| Intent guards        | `.cuga/intent_guards/*.md` (fire on user prompts)      |
| Output formatters    | `.cuga/output_formatters/*.md` (fire on agent output)  |
| Policy enforcement   | `agent.policies` + automatic match-and-rewrite on turn |
| Skill discovery      | auto — loader scans `.agents/skills/` on startup       |
| Toggle API           | `POST /policies/toggle {policy_id, enabled}`           |
| Live reload          | background watcher polls `.cuga/` mtimes every 2s      |
| Reload API           | `POST /policies/reload` (manual trigger)               |
| Repo switch API      | `POST /repo {owner, repo, ref?}` / `POST /repo/reset`  |
| Live repo clone      | shallow `git clone --depth 1` into `/tmp/repo_steward/`|
| Why-this-turn        | mined from graph `state.chat_messages` per turn        |

## Closing line

*"Skills capture **how** the agent does work. Policies capture **what it is
and isn't allowed to say**. Both live as markdown next to the code, both can
be changed without redeploying, and both are visible to the user in this
panel. That's what CUGA adds."*

## Troubleshooting

- **Skill doesn't load (`NameError: load_skill`)** — `DYNACONF_SKILLS__ENABLED`
  not reaching settings. Ensure env var is set **before** process start (the
  app sets a default via `os.environ.setdefault`).
- **Policy toggle has no effect on next turn** — auto-load of policies from
  disk is overwriting the flag. The app disables `auto_load_policies` after
  the first load; confirm `agent._auto_load_policies = False` after startup.
- **Multiple policies fire on one turn but only one rewrites** — by design.
  CUGA's policy engine picks the highest-priority match; lower-priority
  formatters aren't composed onto the already-rewritten response.
- **Live-authored policy doesn't show up** — the watcher polls every 2s;
  give it ~3s after writing. If still missing, the frontmatter is likely
  malformed (missing `name`, or `triggers` section not set). Run
  `curl -X POST http://127.0.0.1:28822/policies/reload` for a manual
  trigger; errors are returned in the response body.
- **A disabled policy gets re-enabled after editing its file** — shouldn't
  happen; the reload path snapshots current `enabled` states before
  reloading and restores them for policies you'd disabled in the UI. If
  it does, that's a bug — file an issue.
