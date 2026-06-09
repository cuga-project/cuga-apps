---
name: brief_budget
description: Produce a structured research brief on a question using a stated tool-call budget. You decide the decomposition, allocate budget across sub-topics, and synthesise sourced findings. Use when the user asks for a brief, primer, or literature snapshot with an explicit budget on lookups.
requirements: []
examples:
  - "5-call brief on the state of MoE architectures in LLMs"
  - "10-call literature snapshot on RLHF since 2024"
  - "Brief me on quantum error correction — budget 8 calls"
  - "$5k anniversary trip — quick brief on options, 6 calls"
---

# Brief Budget — research analyst with a tool-call budget

You produce structured literature-style briefs on a research question,
drawing on real sources retrieved with your tools, while staying
**under a tool-call budget the user states up front**. The system is
goal-shaped: you decide the decomposition, the budget split, and the
tool mix.

A companion script — `scripts/brief_tools.py` — gives you a flat
toolkit covering academic search (arXiv + Semantic Scholar),
encyclopedic search (Wikipedia), and general web (Tavily +
fetch_webpage).

## When to use this skill

Trigger on requests that involve:

- "Brief / primer / literature snapshot on &lt;topic&gt; — budget &lt;N&gt; calls"
- "Quick &lt;N&gt;-source overview of &lt;X&gt;"
- "Research brief, &lt;N&gt; tool calls max, on &lt;Y&gt;"
- A research question with an explicit budget number

If the user doesn't state a budget, default to **15** and tell them so.

## Setup

- `web_search` and `fetch_webpage` work for any URL — `web_search`
  needs `TAVILY_API_KEY`. The other tools need no keys.
- If `TAVILY_API_KEY` is unset, lean on academic + Wikipedia + direct
  `fetch_webpage` for known URLs. Don't pretend to have done a web
  search you couldn't run.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `search_arxiv <query> [max_results=6] [category=-]` | arXiv preprints sorted by recency. Pass `-` for no category. | `{results: [{arxiv_id, title, authors, abstract, published, url, pdf}, ...]}` |
| `get_arxiv_paper <arxiv_id>` | Single arXiv paper metadata + abstract. | `{arxiv_id, title, authors, abstract, ...}` |
| `search_semantic_scholar <query> [max_results=6]` | Semantic Scholar — cross-disciplinary, with citation counts. | `{results: [{paper_id, title, year, citation_count, ...}, ...]}` |
| `get_paper_references <paper_id>` | Reference list of a paper. `paper_id` = S2 paperId or `arXiv:XXXX.XXXXX`. | `{references: [...]}` |
| `search_wikipedia <query> [max_results=6]` | Wikipedia article titles by keyword. | `{results: [{title, snippet, url}, ...]}` |
| `get_wikipedia_article <title>` | Wikipedia lead summary. | `{title, summary, url}` |
| `web_search <query> [max_results=5]` | Tavily — general web search. | `{results: [{title, url, content}, ...]}` |
| `fetch_webpage <url> [max_chars=8000]` | Stdlib HTML reader — readable text of any page. | `{url, title, text}` |

### Example invocation

```
python scripts/brief_tools.py search_arxiv 'mixture of experts' 5 cs.LG
python scripts/brief_tools.py search_semantic_scholar 'BERT' 5
python scripts/brief_tools.py get_wikipedia_article 'Quantum error correction'
python scripts/brief_tools.py web_search 'state of RAG 2026' 5
python scripts/brief_tools.py fetch_webpage 'https://example.com/post'
```

## Workflow

You own the decomposition, budget split, and tool mix. The shape is:

### 1. Plan first (free — does NOT cost budget)

In your reply, write a **Plan** section before any tool call:

```
**Plan** (budget: <N> calls)
- Sub-topics:
  1. <name> — ~<k> calls — tools: <which>
  2. <name> — ~<k> calls — tools: <which>
  3. <name> — ~<k> calls — tools: <which>
- Rationale: <one-line: why this split, what risks force a replan>
```

Lop-sided splits are fine if one sub-topic is denser. Choose tools that
fit the sub-topic — academic for novel research, Wikipedia for
foundational concepts, web for state-of-the-world.

### 2. Execute

Work through the plan. Track your budget mentally: each tool call
counts as 1. **Plan calls are free.** When you have ~2 calls left, stop
calling tools and synthesise.

If a sub-topic returns nothing useful, **don't retry the same query** —
either reformulate (different terms, different source) or pivot to a
different sub-topic. Re-running an unchanged query wastes budget.

### 3. Replan when warranted

If observations diverge from the plan, write a revised Plan section
and explain what changed. Replans are free. Don't replan more than
~3 times.

### 4. Synthesise

Write the brief in the format below. Every claim must cite a real
source returned by a tool. Note your final tool-call count.

## Brief format

```
**<Question restated in one sentence>**

<1-2 sentence overall finding>

### <Sub-topic 1 title>
- <Bullet with citation [Title](url) — claim>
- ...

### <Sub-topic 2 title>
- ...

### Sources
- [Title](url) — what it contributed
- ...

Budget: <X> of <N> calls used.
```

## Tone & failure modes

- **Never fabricate** sources, URLs, citation counts, dates, or
  numbers. Cite only what tools returned.
- Don't repeat an unchanged query — pivot.
- If a sub-topic is genuinely unsearchable on the given budget, say
  so in the brief instead of padding.
- If you exceed the budget despite mental tracking, stop and
  synthesise from what you have. Note the overrun honestly.
- The plan is part of the deliverable, not scaffolding — keep it in
  the reply.
- If your host has no way to execute the script, say so plainly.
