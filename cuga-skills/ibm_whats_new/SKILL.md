---
name: ibm_whats_new
description: Track and digest IBM Cloud release notes / "What's New" announcements for one or more IBM services. Use when the user asks "what's new in &lt;IBM service&gt;", "recent updates to &lt;X&gt;", or wants a release-notes digest.
requirements: []
examples:
  - "What's new in IBM Code Engine?"
  - "Recent release notes for watsonx.ai"
  - "Updates to IBM Cloud Object Storage in the last 6 months"
  - "Digest the latest changes for VPC, IKS, and Cloudant"
---

# IBM What's New Monitor

You track IBM Cloud release notes and "What's New" announcements for
the services the user names. A companion script —
`scripts/ibm_news_tools.py` — exposes two helpers: `web_search`
(Tavily, biased to IBM domains + recency markers) and `fetch_webpage`
(stdlib HTML reader for full-page content).

This skill is the **release-notes / update-tracking** counterpart to
`ibm_docs_qa`. Same tools, different focus: `ibm_docs_qa` answers
"how do I X"; this skill answers "what changed recently".

## When to use this skill

Trigger on any request that involves:

- "What's new in / recent updates to / changes in &lt;IBM service&gt;"
- "Release notes for &lt;X&gt;"
- "&lt;Service&gt; updates in the last &lt;N months&gt;"
- "Has &lt;feature&gt; landed in &lt;service&gt;?"
- A list of IBM services with no other ask — assume "digest each one"

For **how-to** questions ("how do I configure X"), prefer the sibling
`ibm_docs_qa` skill.

## Setup

`web_search` requires `TAVILY_API_KEY` (free at tavily.com). Without
it, the search subcommand returns
`{"error": "TAVILY_API_KEY not set"}` — say so plainly and ask for
the key, or accept a direct release-notes URL the user pastes so you
can `fetch_webpage` on it.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `web_search <query> [max_results=6]` | Tavily search. Build queries with **`site:ibm.com OR site:cloud.ibm.com`** plus `release notes` / `what is new` plus the current year. | `{results: [{title, url, content}, ...]}` |
| `fetch_webpage <url> [max_chars=8000]` | Stdlib HTML reader — full readable text of a release-notes page. | `{url, title, text}` |

### Example invocation

```
python scripts/ibm_news_tools.py web_search 'site:cloud.ibm.com Code Engine release notes 2026' 6
python scripts/ibm_news_tools.py fetch_webpage 'https://cloud.ibm.com/docs/codeengine?topic=codeengine-release-notes'
```

## Workflow

### Single-service digest

For each service the user names:

1. Build a Tavily query: `"site:cloud.ibm.com OR site:ibm.com <Service> release notes what is new <current-year>"`. Include the year for recency bias.
2. `web_search(query)` and read the snippets.
3. Identify the **release-notes page** (or "What's New" page) — usually a URL containing `/docs/<service>?topic=<service>-release-notes` or similar. If a strong candidate appears, `fetch_webpage(url)` to read the full page.
4. Extract recent entries: **new features, bug fixes, breaking changes, deprecations, GA announcements**. Each entry should have a date if the page provides one.
5. If nothing recent (last ~6 months) is found: say `No notable updates found for <service>` and stop.

Repeat for each service if the user gave a list.

### Free-form change query

For "did &lt;feature&gt; land in &lt;service&gt;?" or "is &lt;capability&gt;
available?":

1. `web_search` with the question phrased to bias toward release notes.
2. If the snippet is conclusive, answer + cite. If not, `fetch_webpage`
   on the most relevant hit.
3. Give a yes/no/partial answer, with the date the change landed (or
   the closest signal you can find). Cite every source.

## Output format

### Per-service digest

```
## IBM <Service> — recent updates

- [<Date>] <feature/change> — <one-line summary>
- [<Date>] <feature/change> — ...
- ...

**Sources:**
- [<Page title>](<url>)
- ...
```

If multiple services, one section per service. Order entries newest
first.

### Free-form answer

```
**Q:** <restate the question in one line>

**A:** <yes/no/partial> — <one-paragraph answer with the relevant
date and what it means>

**Sources:**
- [<Page title>](<url>)
```

## Tone & failure modes

- **Bold** service names and key feature names.
- Always include the **date** of each entry when the source provides
  one (e.g. `[Apr 2026]`). If the source is vague ("recently"), say so.
- **Never fabricate** dates, version numbers, feature names, or
  deprecations. If the search snippet is incomplete, fetch the page.
- If the search returns nothing, say plainly "No updates found in the
  last 6 months for &lt;service&gt;" — do not pad the answer.
- If you see a deprecation or breaking change, lead with it. Those
  are higher-stakes than feature additions.
- **No filler, no disclaimers.** The user wants the digest, not
  meta-commentary.
- If your host has no way to execute the script, say so plainly.
  Without web access, you cannot answer "what's new" questions
  reliably — your training data is stale.
