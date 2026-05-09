---
name: webpage_summarizer
description: Fetch any webpage and produce a structured summary — title, overview, key topics, important facts, and a one-line takeaway. Use whenever a user pastes a URL and asks "summarize", "what's on this page", or "what does this say".
requirements: []
examples:
  - "Summarize https://anthropic.com"
  - "What's on https://example.com/blog/post"
  - "TL;DR of this page: https://news.site/article"
  - "What does this say? https://docs.example.com/api"
---

# Webpage Summarizer

You help users get the gist of any webpage. A companion script —
`scripts/web_tools.py` — exposes one CLI subcommand, `fetch_url`, which
downloads a page and returns its readable text content.

## When to use this skill

Trigger on any request that involves:

- "Summarize / TL;DR / give me the gist of &lt;url&gt;"
- "What does &lt;url&gt; say / cover / argue?"
- "Read this page for me: &lt;url&gt;"
- A URL pasted with no other context — assume a summary is wanted

## Tools provided

The skill ships one Python script with one subcommand. Run it as a
subprocess (using whatever shell-execution primitive your host provides)
and parse the JSON it prints to stdout. Reference the script by its
relative path inside this skill folder — `scripts/web_tools.py`.

| Subcommand | Purpose | Returns |
| --- | --- | --- |
| `fetch_url <url> [max_chars]` | Fetch a webpage and return its readable text content. Strips scripts, styles, nav, header, footer. | `{"url", "title", "text"}` or `{"error": "..."}` |

`max_chars` defaults to 10000.

### Example invocation

```
python scripts/web_tools.py fetch_url 'https://example.com'
# → {"url": "https://example.com", "title": "Example Domain", "text": "..."}
```

## Workflow

When the user provides a URL:

1. Run `fetch_url(url)`. If the result has `error`, surface it plainly
   and ask for a different URL — do not fabricate page content.
2. Read the returned `text`. Note the page type (article, product page,
   docs page, news story, landing page).
3. Produce the summary in the format below. Keep it tight — one screen.

If the page is paywalled, very short, or returned only boilerplate, say
so plainly. Don't pad the summary with filler.

## Tone & failure modes

- Concise: 2–3 sentence overview, then 3–6 bulleted topics.
- Article → focus on argument and evidence.
- Product page → highlight features and pricing.
- News story → who / what / when / where / why.
- Docs page → what API/feature this is, plus the most important rules.
- **Never invent content not in the returned text.** If the text is empty
  or malformed, say so and ask for a different URL.
- If your host has no way to execute the script (no shell or subprocess
  primitive), say so plainly. Do not guess at the page content.

## Output format

```
**<Page title>** — <url>

<2-3 sentence overview of the page's main purpose>

**Key topics**
- <topic 1>
- <topic 2>
- ...

**Notable facts**
- <fact / data / quote / pricing>
- ...

**Bottom line:** <one-sentence takeaway for the reader>
```
