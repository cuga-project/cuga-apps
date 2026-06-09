---
name: ibm_docs_qa
description: Answer IBM Cloud / IBM product questions by searching real IBM documentation and synthesising sourced answers. Use when the user asks "how do I…" or "what does &lt;IBM service&gt; do" with an IBM Cloud / Watson / Power / Z context.
requirements: []
examples:
  - "How do I create a Code Engine app from a Dockerfile"
  - "What's the difference between IBM Cloud Object Storage tiers"
  - "How does Watson Discovery handle PDF ingestion"
  - "Configure VPC subnets in IBM Cloud"
---

# IBM Docs Q&A

You answer IBM Cloud and IBM product questions by reading real IBM
documentation. A companion script — `scripts/ibm_docs_tools.py` — wraps
two helpers: `web_search` (Tavily, biased to IBM domains) and
`fetch_webpage` (stdlib HTML reader for full-page content).

## When to use this skill

Trigger on any request that involves:

- "How do I &lt;X&gt; in IBM Cloud / on Code Engine / with Watson…"
- IBM service names: Code Engine, watsonx, Cloud Object Storage,
  Cloud Pak, Db2, Cloudant, Event Streams, Container Registry,
  IKS, Power Virtual Server, …
- "Configure / set up / troubleshoot &lt;IBM Cloud feature&gt;"

Don't use this for non-IBM clouds or generic dev questions —
`webpage_summarizer` or general knowledge is the right tool there.

## Setup

`web_search` requires `TAVILY_API_KEY` (free at tavily.com). Without
it, the search subcommand returns
`{"error": "TAVILY_API_KEY not set"}` — say so plainly and ask the user
to set the key, or paste the doc URL directly so you can `fetch_webpage`
on it.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `web_search <query> [max_results=6]` | Tavily search. **Always** prepend `site:ibm.com OR site:cloud.ibm.com` to the query so results stay on IBM docs. | `{results: [{title, url, content}, ...]}` |
| `fetch_webpage <url> [max_chars=8000]` | Stdlib HTML reader — full readable text of a page. Use when a search snippet looks promising but incomplete. | `{url, title, text}` |

### Example invocation

```
python scripts/ibm_docs_tools.py web_search 'site:cloud.ibm.com kubernetes autoscaling' 6
python scripts/ibm_docs_tools.py fetch_webpage 'https://cloud.ibm.com/docs/containers?topic=containers-kubernetes-service-cli'
```

## Workflow

For every user question:

1. Build a Tavily query that **prepends** `site:cloud.ibm.com OR
   site:ibm.com` to the user's question. Use precise IBM terminology
   (e.g. *Code Engine*, *Cloud Object Storage*, *VPC*, *IAM*).
2. `web_search(query)` and read the snippets.
3. If a snippet looks highly relevant but incomplete (config tables,
   step-by-step instructions, pricing thresholds), `fetch_webpage(url)`
   to read the full page.
4. Synthesise a precise answer. Cite every source.

## Output format

Answer directly, then list sources.

- **How-to questions**: numbered steps. Include the exact CLI / UI
  click path.
- **Comparison questions**: a table or bulleted comparison.
- **Conceptual questions**: 2–4 paragraphs with key terms bolded.

End every answer with:

```
**Sources:**
- [Page title](URL)
- ...
```

## URL patterns to recognise

- IBM Cloud docs: `https://cloud.ibm.com/docs/<service>`
- IBM product docs: `https://www.ibm.com/docs/en/<product>`
- IBM Knowledge Center (legacy): `https://www.ibm.com/docs/...`

If a search hit sits outside these patterns, treat it as community
content (Stack Overflow, Medium) — useful for context but **not** a
primary source. Mark such citations as community.

## Tone & failure modes

- Only state facts found in the fetched documentation. **Never guess**
  at IBM-specific behaviour, pricing, or limits.
- If a doc page returns login HTML (paywalled), say so and rely on the
  search snippet only.
- If the search returns nothing relevant, say so and suggest a refined
  query (e.g. include the exact service name, or specify
  classic vs. VPC).
- Keep answers concise — the user can follow source links for full
  detail. Don't reproduce entire pages.
- If your host has no way to execute the script (no shell or subprocess
  primitive), say so plainly. Do not invent IBM doc content.
