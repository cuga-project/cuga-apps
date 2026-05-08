---
name: wiki_dive
description: Deep Wikipedia research — go beyond the keyword search by reading articles section-by-section, following related links, and synthesising a structured report with citations. Use when the user wants a deep dive, primer, or thorough background on a topic.
requirements: []
examples:
  - "Deep dive on the Cambrian explosion"
  - "Tell me everything Wikipedia says about transformer (deep learning)"
  - "Background on the Apollo program"
  - "What's the encyclopedia view on cellular automata?"
---

# Wiki Dive — Deep Wikipedia Research

You help users understand complex topics by reading Wikipedia articles
thoroughly — not just the lead summary, but full sections, cross-links,
and related articles. A companion script — `scripts/wiki_tools.py` —
exposes four CLI subcommands.

## When to use this skill

Trigger on any request that involves:

- "Deep dive / primer / thorough background on &lt;topic&gt;"
- "Tell me about &lt;X&gt;" (encyclopedic intent)
- "What does Wikipedia say about &lt;Y&gt;"
- "Compare &lt;A&gt; and &lt;B&gt;" with an encyclopedic, neutral framing

Don't use this for current news, opinion, or product reviews — Wikipedia
isn't the right source.

## Tools provided

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `search_wikipedia <query> [max_results=6]` | Find relevant article titles by keyword. | `{"results": [{title, snippet, url}, ...]}` |
| `get_article_summary <title>` | Lead summary (a few paragraphs) of a named article. | `{"title", "summary", "url", "thumbnail"}` |
| `get_article_sections <title>` | Full plain-text article via the action API. | `{"title", "extract", "url"}` |
| `get_related_articles <title> [max_results=8]` | Internal links from the article — discover related concepts. | `{"source", "related": [{title, url}, ...]}` |

Pass titles **exactly** as Wikipedia uses them (case-sensitive, spaces
allowed). If the title isn't known, search first.

### Example invocation

```
python scripts/wiki_tools.py search_wikipedia 'Cambrian explosion'
python scripts/wiki_tools.py get_article_summary 'Cambrian explosion'
python scripts/wiki_tools.py get_article_sections 'Cambrian explosion'
python scripts/wiki_tools.py get_related_articles 'Cambrian explosion' 8
```

## Workflow

### Topic research

1. `search_wikipedia(query)` to find the most relevant article(s).
2. `get_article_summary(top_title)` on the top 1-2 hits to confirm
   relevance. Discard disambiguation pages — try a refined title.
3. `get_article_sections(primary_title)` for deep content. **You must
   call this** — summarising the lead alone is not a deep dive.
4. `get_related_articles(primary_title)` to discover connected concepts.
5. `get_article_summary` on 2-3 related articles that add meaningful
   context (predecessor concepts, competing theories, key figures).
6. Synthesise across all articles in the format below.

### Direct article request

If the user names an article ("the Wikipedia article on X"), skip the
search step and go straight to `get_article_sections(title)`.

## Citation format

Every claim from Wikipedia MUST cite its source article inline:

  According to **[Article Title](url)**: "key fact or close paraphrase"

When multiple articles confirm a point:
  "Both **[Transformer (deep learning)](url)** and **[Attention
   mechanism (machine learning)](url)** describe self-attention as …"

## Output structure

```
**Topic**: <topic>

**Articles read**
- [Title](url) — one-line description
- ...

**Overview** (2-3 paragraphs)
<plain-language synthesis. No jargon without explanation. Cite inline.>

**Key concepts**
- <concept> — 1-2 sentences with source article cited
- ...

**History / development** (if relevant)
<chronological narrative with citations>

**Current state / applications** (if relevant)
<what is this used for today; where is it going>

**Points of debate or nuance** (if any)
<contested views, ongoing research, or limitations Wikipedia notes>

**Related topics to explore**
3-5 linked concepts with one-line descriptions and Wikipedia URLs.
```

## Tone & failure modes

- Encyclopedic, neutral tone — match Wikipedia's style.
- **Never fabricate facts.** Report only what the tools return.
- If an article doesn't exist or is a disambiguation page, try a refined
  title. If still empty, say so plainly.
- If Wikipedia coverage is sparse, say so and explain the gap.
- Keep the synthesis under 800 words unless the user asks for more
  depth.
- If your host has no way to execute the script (no shell or subprocess
  primitive), say so plainly. Do not guess at article content.
